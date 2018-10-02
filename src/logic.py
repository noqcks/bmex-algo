import logging
from .sqlite import Balances
from .bitmex import BitMex
import numpy as np
import sys

class Logic():
  decision = False
  pending_orders = []
  client = None
  symbol = None
  m = None
  Q = None
  trade_alloc = None
  mode = None
  thresh = 0
  df_buy = None
  df_sell = None
  pair = None

  def __init__(self, symbol, client, m, Q, df_buy, df_sell, c_min_amount = 30.0, trade_alloc = 0.001, mode = 'test'):
    self.symbol = symbol
    self.client = client
    self.m = m
    self.Q = Q
    self.trade_alloc = trade_alloc
    self.c_min_amount = c_min_amount
    self.df_buy = df_buy
    self.df_sell = df_sell
    self.mode = mode
    self.pair = symbol.replace('-','')
    self.thresh = self.find_threshold()
    # TODO: split NOT based on length! This is error prone.
    # self.c_maj, self.c_min = symbol[:len(symbol)//2], symbol[len(symbol)//2:]
    self.c_maj, self.c_min = "XBT", "BTC"
    self.current_balance = {}

  def trade_logic(self):
    logging.info("Starting trade logic...")
    df = {}
    df['BUY'] = self.df_buy
    df['SELL'] = self.df_sell

    self.decision, self.pending_orders = BitMex.check_pending_orders(
                                          self.symbol,
                                          self.client,
                                          self.c_maj,
                                          self.c_min,
                                          self.current_balance,
                                          self.thresh,
                                          self.trade_alloc
                                        )

    logging.info("Decision:" + str(self.decision))

    if self.good_trade_conditions(df[self.decision]):
      logging.info("Good Trading Conditions? [YES]")
      # check for excess orders
      # n_orders = the number of pending orders for a decision
      n_orders = 0
      if self.pending_orders != []:
        n_orders = len(self.pending_orders[self.decision])

      # set optimal order price
      if (self.decision == 'BUY'):
        o_optimal = df[self.decision].iloc[:,0].max()
      else:
        o_optimal = df[self.decision].iloc[:,0].min()

      if(n_orders > 1):
        ## TODO: don't cancel all orders here, just cancel excess orders
        orders_to_cancel = BitMex.eliminate_excess_orders(self.pending_orders[self.decision], self.decision)
        BitMex.cancel_all_orders(self.client, self.orders_to_cancel, self.decision)
        # if (resp is None):
        #   logging.info("Cancelling Excess Orders [Success]")
        # else:
        #   logging.info("Cancelling Excess Orders [Fail]:" + resp)

      elif(n_orders == 0):
        # Issue buy when no pending orders
        if (self.decision == 'BUY'):
          logging.info('Issue Order: ' + (self.decision, self.pair, o_optimal, self.trade_alloc/o_optimal, self.client))
          if (self.mode != 'test'):
            resp = BitMex.issue_order(self.decision, self.symbol, o_optimal, self.trade_alloc/o_optimal, self.client)
            logging.info('Issue Order Resp: ' + str(resp))
            print("BUY")
            sys.exit(1)

        # Issue sell
        else:
          if self.c_maj in self.current_balance:
            logging.info('Issue Order: Init, Decision: {}, Pair: {}, o_optimal: {}, Current Balance: {}'.format(self.decision, self.pair, o_optimal, self.current_balance[self.c_maj]))

          if (self.mode != 'test' and self.current_balance[self.c_maj] > 0):
            resp = BitMex.issue_order(
              self.decision,
              self.symbol,
              o_optimal,
              self.current_balance[self.c_maj],
              self.client
            )
            logging.info('Issue Order Resp: ' + str(resp))

      else:
        if self.not_best_order(o_optimal):
          logging.info('Updating Order: ' + [o_optimal, self.decision, self.trade_alloc])

          if (self.mode != 'test'):
            resp = BitMex.update_order(self.pending_orders[self.decision], o_optimal, self.decision, self.trade_alloc, self.client, self.symbol)
            logging.info('Updating Order Resp: ' + string(resp))

    else:
      logging.info("Good Trading Conditions? [NO]")
      if (len(self.pending_orders[self.decision]) > 0):
        # cancel pending orders
        BitMex.cancel_all_orders(self, self.client, self.pending_orders, self.decision)
        logging.info("Cancelled All Pending Orders")

    logging.info("Finished trade logic...")
    return 'Ran', self.decision

  def find_threshold(self):
    logging.info("Finding threshold...")
    threshold_default = 0.01
    if(len(self.df_buy) + len(self.df_sell) > 0):
      o_optimal = (self.df_sell.iloc[:,0].min() + self.df_buy.iloc[:,0].max())/2
      threshold = self.c_min_amount / o_optimal
      return threshold
    else:
      return threshold_default

  ## good_trade_conditions will check that we have an opportunity to make a trade
  ## based on our expected price of a coin and compare it to the current price of
  ## the coin.
  ## default: False
  def good_trade_conditions(self, df, cost=0.001, trade_entry=1.5, trade_exit=1.5):
    logging.info("Checking trade conditions...")

    # check our expected price of btc and compare it to market price
    # if there are no bids or asks do what?
    if(len(df) > 0):
      if (self.decision == 'BUY'):
        # difference between price of btc and expected price from kalman
        # e = error
        e = df.iloc[:,0].max() - self.m
        # SD from market price/ expected price deviation according to trade_entry number
        # 1.5 SD if trade_entry = 1.5
        condition = min(((-1*(trade_entry)) * np.sqrt(self.Q)), ((-1*(trade_entry)) * self.m * cost))
        if (e < condition):
          return True
        else:
          return False
      else:
        e = df.iloc[:,0].min() - self.m
        condition = max(((trade_exit) * np.sqrt(self.Q)), (trade_exit * self.m * cost))
        if (e > condition):
          return True
        else:
          return False
    elif(df == None):
      logging.info("Pulling of Orders probably failed - None was passed")
      return False
    else:
      logging.info("Place ridiculous orders")
      return False

  def not_best_order(self, o_optimal):
    pair = self.symbol.replace('-','')
    if (self.decision == 'BUY'):
      if (o_optimal > self.pending_orders['BUY'][0][2]):
        return True
      else:
        return False

    elif (self.decision == 'SELL'):
      if (o_optimal < self.pending_orders['SELL'][0][2]):
        return True
      else:
        return False
