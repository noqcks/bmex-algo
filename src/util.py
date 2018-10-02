import time
import datetime
from .sqlite import (
  Balances
)

import logging

class Util():
  def is_time_horizon(dt, freq = datetime.timedelta(minutes=15), offset = datetime.timedelta(minutes=0), duration = datetime.timedelta(minutes=5), inittime = datetime.datetime(2018,4,22)):
    # This function checks how far after a 'time loop' (of length 'freq') the input time falls
    # We can use this to determine if a trade should happen or not

    # dt = time to check
    # freq = period of time
    # offset = minute offset to add (from init time) - should loop fairly fast unless weird values are used
    # duration = length of 'on time' after 'trigger' is hit
    # inittime = start of 'time'. Used to determine offset. Shouldn't be an issue, perhaps we reset this every year

    timesince_init = dt - inittime
    remainder = ((timesince_init - offset) % freq)
    return(remainder < duration)

  def log_request(conn, ts, msg, pair, inst):
    req_log = sum([[ts],[ts],[ts],[msg],[pair],[inst]],[])
    cur = conn.cursor()
    cur.execute('''INSERT INTO requests (start_ts, req_ts, final_ts, msg, pair, inst) VALUES (?,?,?,?,?,?)''', req_log)
    conn.commit()

  def truncate(number, digits) -> float:
    stepper = pow(10.0, digits)
    return(math.trunc(stepper * number) / stepper)

  def log_trade(conn, symbol, price, amount, msg, buy_or_sell):
    pair = symbol.replace('-','')
    req_log = sum([[time.time() * 1000],[pair],[price],[amount],[msg],[buy_or_sell]],[])
    cur = conn.cursor()
    cur.execute('''INSERT INTO trades (ts, pair, price, amount, msg, b_a) VALUES (?,?,?,?,?,?)''', req_log)
    conn.commit()

  def update_balances(client, symbol):
    # Update Balances
    try:
      balance = client.fetch_balance()
      # BTC
      Balances.create(
        ts=time.time() * 1000,
        coin="BTC",
        balance=balance['BTC']['free'],
        freeze=0
      )
      Balances.create(
        ts=time.time() * 1000,
        coin="XBT",
        balance=balance['BTC']['used'],
        freeze=0
      )
      req_log = [time.time() * 1000] + [symbol] + [balance['info'][0]['amount']] + [0]
      logging.info("Balance Update [Success]" + str(req_log))
    except Exception as e:
      logging.info("Balance Updat [Fail]: " + e)
