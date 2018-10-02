import logging
import requests
import pandas as pd
import time

from .sqlite import Orders
from .sqlite import Balances

class BitMex():
  def pull_bitmex_orderbooks(symbol, limit, mode='live'):

    # Tracking execution time
    start_ts = time.time() * 1000

    # Get request
    request = requests.get('https://www.bitmex.com/api/v1/orderBook/L2?symbol={}&depth={}'.format(symbol, limit))

    bitmex = request.json()
    # Check to make sure data is pulled properly
    if request.status_code == 200:
      # Track latency
      req_ts = int(time.time())

      sell_arr = []
      buy_arr = []
      for item in bitmex:
        # ['Price','Amount','Value']
        row = [item['price'], item['size'], item['price'] * item['size']]
        if item['side'] == "Sell":
          sell_arr.append(row)
        if item['side'] == "Buy":
          buy_arr.append(row)

      # Extract Bids and Asks to DFs
      df_buy = pd.DataFrame(buy_arr)
      df_sell = pd.DataFrame(sell_arr)

      #Ensure that DFs are not empty
      if len(df_buy) == 0:
        df_buy = pd.DataFrame([[0,0,0]])

      if len(df_sell) == 0:
        df_sell = pd.DataFrame([[0,0,0]])

      df_buy.columns = df_sell.columns = ['Price','Amount','Value']

      # # Write order book data to databae
      for row in buy_arr:
        Orders.create(
        ts=req_ts,
        price=row[0],
        amount=row[1],
        value=row[2],
        b_a='b'
        )

      for row in sell_arr:
        Orders.create(
        ts=req_ts,
        price=row[0],
        amount=row[1],
        value=row[2],
        b_a='a'
        )


      final_ts = time.time() * 1000

      # Log request
      req_log = [start_ts, req_ts, final_ts, request.status_code, symbol, 'orders']
      logging.info(req_log)
      return (df_buy, df_sell)
    else:
      logging.warning("Orderbook request failure.")
      logging.warning(request.json())
      return(None, None)

  ## check_pending_orders will check if there are pending orders.
  ## It makes decision based on whether there are pending orders and whether we have
  ## an appropriate balance and will return a decision of 'BUY' or 'SELL'
  ## default: 'SELL'
  def check_pending_orders(symbol, client, c_maj, c_min, current_balance, thresh, trade_alloc):
    # Get pending orders
    logging.info("Checking pending orders...")

    # TODO: get this dynamically
    symbol = "BTC/USD"
    bitmex = client.fetch_open_orders(symbol)

    ## this is some data munging that we have to do because bitmex doesn't
    ## return a nice object
    sell_arr = []
    buy_arr = []
    for item in bitmex:
      # ['orderID','Price','Amount','Value']
      row = [item['info']['orderID'], item['info']['price'], item['info']['orderQty'], item['info']['price'] * item['info']['orderQty']]
      if item['info']['side'] == "Sell":
        sell_arr.append(row)
      if item['info']['side'] == "Buy":
        buy_arr.append(row)
    pending_orders = {'BUY': buy_arr, 'SELL': sell_arr}

    if pending_orders != []:
      if(len(pending_orders['BUY']) + len(pending_orders['SELL']) == 0):
        for c in (c_maj, c_min):
          coin = Balances.select().where(Balances.coin == c).order_by(Balances.id.desc()).get()
          current_balance[c] = coin.balance

        logging.info("Checking balances....")
        # do a balance check to see whether we can trade with current balance
        # based on threshold
        decision = BitMex.balance_check(current_balance[c_maj], current_balance[c_min], thresh, trade_alloc)

        if decision:
          return('BUY', pending_orders)
        else:
          return('SELL', pending_orders)
      else:
        if(len(pending_orders['BUY']) > 0):
          return('BUY', pending_orders)
        else:
          return('SELL', pending_orders)

    # TODO: what should we do if no pending orders?
    # return('SELL', pending_orders)

  ## DONE
  def balance_check(balance_maj, balance_min, thresh, trade_alloc):
    # major = the one you're quoting.
    # minor = the one you're quoting in.
    # balance_maj is major coin balance
    # balance_min is minor coin balance
    # thresh is threshold under which you buy the major pair
    # trade_alloc is the allocated amount to trade
    return((balance_maj <= thresh) and (balance_min >= trade_alloc))

  ## eliminate_excess_orders will _ all but the best order
  def eliminate_excess_orders(df, decision):
    # checks for all excess orders and returns list of non-optimal oID to cancel
    logging.info("Eliminating excess orders...")
    print(o_df)
    o_df = pd.DataFrame(df)
    o_df.columns = ['ts','bs','p','a','deal','oid']

    if(decision == 'BUY'):
      o_optimal = o_df.p.max()
    else:
      o_optimal = o_df.p.min()

    oid_keep = o_df[o_df.p == o_optimal].oid
    orders_to_cancel = [i for i in o_df[o_df.oid != oid_keep[0]].oid]

    return orders_to_cancel

  def update_order(pending_orders, o_optimal, decision, trade_alloc, client, symbol):
    pair = symbol.replace('-','')

    # cancel all orders
    resp = self.cancel_all_orders(client, pending_orders, decision)
    logging.info("Canceling All Orders for {}: {} Side: {}".format(pair, resp, decision))
    log_request(conn, time.time(), resp, pair, 'cancel_order - {}'.format(decision))

    # issue order
    resp = issue_order(decision, symbol, o_optimal, trade_alloc/o_optimal, conn)
    logging.info("Issuing Orders for {}: {} Side: {}".format(pair, resp, decision))

    return('Order Updated')

  def cancel_all_orders(self, client, orders, decision):
    # order[0] = orderID
    for order in orders[decision]:
      logging.info("Cancelling order: {}".format(order[0]))
      try:
        client.cancelOrder(order[0])
      except OrderNotFound as e:
        logging.info("Cancelling Excess Orders {} [Fail]:".format(order[0], e))

  ## TODO: update with better logging
  def issue_order(decision, symbol, price, amount, client, precision=0):
    try:
      # initialize temporary client to avoid UNAUTH
      # TODO: don't hard code this
      ccxt_sym = "BTC/USD"

      print("issue order")

      if(decision == 'BUY'):
        rresp = client.create_limit_buy_order(ccxt_sym, amount, price)
        oid = rresp['id']
        log_trade(conn, symbol, price, amount, oid, decision)
        return(oid)

      if(decision == 'SELL'):
        # To catch bad precision loopback re-order
        if (precision > 0):
          print('Debug precision: ', amount, str(amount))
          rresp = client.create_limit_sell_order(ccxt_sym, amount, price)
        else:
          rresp = client.create_limit_sell_order(ccxt_sym, amount, price)
        oid = rresp['id']
        log_trade(conn, symbol, price, amount, oid, decision)
        return(oid)

    except Exception as issue_error:
      print(type(issue_error))
      print(issue_error.args)
      print(str(issue_error.args[0]).replace(',','|'))

      # In scenario with improper amount precision
      if ('precision of amount' in str(issue_error.args)):
        logging.warning(str('Improper Amount Precision - {}'.format(str(issue_error.args[0]))))
        m = re.search('(The precision of amount).*[0-9]{1}', str(issue_error.args[0]))
        precision = int(m.group(0)[-1])
        print(precision)
        order_amount = truncate(amount, precision)
        if (order_amount > 0.0):
          print('Reissuing order', order_amount, precision)
          issue_order(decision, symbol, price, order_amount, conn, precision)
          return('Reissued Order')
        else:
          return('Error issueing order: order_amount too low for precision')
      return(str(issue_error).replace(',','|'))

  def is_best_order(decision, symbol, o_optimal, client, pending_orders, order_df):
    pair = symbol.replace('-','')
    if (decision == 'BUY'):
      if (o_optimal > pending_orders['BUY'][0][2]):
        return(False)
      else:
        return(True)

    elif (decision == 'SELL'):
      if (o_optimal < pending_orders['SELL'][0][2]):
        return(False)
      else:
        return(True)
