import re
import requests
import pandas as pd
import time
import sqlite3
import sys
import numpy as np
import ccxt as ccxt
import logging
import math
import datetime

import logging
import time

from src.bitmex import BitMex

from src.sqlite import db
from src.sqlite import (
  Orders,
  Ticker,
  Requests,
  Balances,
  KalmanTbl
)
import peewee

from src.logic import Logic
from src.util import Util
from src.kalman import Kalman

# Track start time of entire script
s_ts = time.time()
launchtime = datetime.datetime.now() # used to segment time for longer time horizing trade periods

# Initialize logging
logging.basicConfig(level=logging.INFO)

# CCXT client
client = ccxt.bitmex({'apiKey': 'APIKEY', 'secret': 'APISECRET'})

# Collect symbols from kucoin
symbol = 'XBTUSD'

# For testnet
if 'test' in client.urls:
  client.urls['api'] = client.urls['test']

db.connect()
# create tables if they don't exist
db.create_tables([Orders, Ticker, Requests, Balances, KalmanTbl])

################################################################################
################################################################################
################################################################################

## TODO: implement baseclass with client as attribute (bitmex + logic children class with access to client)
def run_loop():
  while True:
    sys.stdout.write("-----\n")
    sys.stdout.flush()

    try:
      logging.info("Starting up trader...")
      logging.info('Symbol: ' + symbol)

      # initialize first kalman row if it doesn't exist
      try:
        KalmanTbl.get()
      except peewee.DoesNotExist:
        logging.info("Initializing first kalman row.")
        KalmanTbl.create(
          ts=int(time.time()*1000),
          C=0,
          V=0,
          e=0,
          yhat=0,
          m=0,
          Q=0,
          K=0,
          P=0,
          R=0,
          Ve=0,
          max_vol=0
        )

      Util.update_balances(client, symbol)

      # TODO: Use is_time_horizon() to guarantee optimal kalman times for a given pair
      # if Util.is_time_horizon(launchtime, freq = datetime.timedelta(hours=4)):
      k = Kalman()
      kalman_mean, Q = k.kalman(symbol, client)
      # else:
      #   print('Not updating () for this time: '.format(symbol), launchtime)
      #   kalman_mean, Q = None, None

      # Pull/Write Orderbooks
      try:
        df_buy, df_sell = BitMex.pull_bitmex_orderbooks(symbol, 30)
      except:
        start_ts = time.time()
        req_log = [start_ts, start_ts, start_ts, sys.exc_info(), symbol, 'orders fail']
        logging.info(req_log)

      # Trade logic
      # Execute trade as long as order books are passed on
      if ((df_buy is not None) and (kalman_mean is not None)):
        try:
          # TODO: use time horizon
          # if Util.is_time_horizon(launchtime, freq = datetime.timedelta(hours=4)):
          logic = Logic(
            symbol=symbol,
            client=client,
            m=kalman_mean,
            Q=Q,
            trade_alloc=40.0,
            mode='live',
            df_buy=df_buy,
            df_sell=df_sell
          )
          logic.trade_logic()
          # else:
          #   logging.info('Not trading {} for this time: '.format(symbol) + str(launchtime))
        except Exception as e:
          logging.error(e)
      else:
        logging.info('Cannot trade. kalman_mean = {}'.format(kalman_mean))

      ## TODO: we should log and store dealt orders to DB

      # Script loop success log
      end_ts = time.time()
      req_log = [s_ts, int(end_ts), int(end_ts), 'Success', 'all_kucoin', 'Full Script Run']
      logging.info(req_log)
      logging.info('SUCCESS - Done in {}'.format(end_ts - s_ts))
      time.sleep(30)
    except:
      logging.error('Failed: ' + str(sys.exc_info()))
      end_ts = time.time()
      req_log = [s_ts, end_ts, end_ts, 'Fail', 'all_kucoin', 'Script fail']
      logging.info(req_log)
      sys.exit()


# main program
# TODO: sleep every x mins? (5, 10, 15)
run_loop()
