from .sqlite import KalmanTbl
from peewee import *
import time
import logging
from playhouse.shortcuts import model_to_dict
import pandas as pd
import numpy as np

class Kalman():
  def kalman_update(self, symbol, C, V, e, yhat, m, Q, K, P, R, Ve, max_vol):
    # set initial parameters
    delta = 0.00000000000001
    Vw = delta/(1-delta)

    ## TODO: get datetime of kalman row -1 day

    # set max_vol very small if isn't set in kalmanTbl
    if (max_vol == None or max_vol == 0):
      max_vol = 0.000000000001

    # one time step update with latest price and volume
    # estimate is initially estimate from previous time step
    R = P + Vw
    yhat = m
    Ve = R * (1 - min(V/max_vol, 1))

    # update Kalman estimate
    e = C - yhat
    Q = np.nansum([R , Ve])

    if (Q != 0):
      K = R / Q
    else:
      K = 0

    m = np.nansum([m, np.nanprod([K,e])])
    P = R - np.nanprod([K,R])
    return {'C': C, "V": V, "e": e, "yhat": yhat, "m": m, "Q": Q, "K": K, "P": P, "R": R, "Ve": Ve, "max_vol": max_vol}

  def kalman(self, symbol, client):
    # Tracking execution time
    start_ts = time.time() * 1000

    ccxt_sym = "BTC/USD"
    pair = symbol

    try:
      logging.info("Fetching bitmex OHLCV")
      ohlcv = client.fetch_ohlcv(ccxt_sym, '1m', limit= 5)
      df = pd.DataFrame(ohlcv)
      df.columns = ['ts','O','H','L','C','V']
      tdf = df[pd.notnull(df.C)]

      if(len(tdf) < 1):
        latestclose = client.fetch_ticker(ccxt_sym)['close']
        totalvol = 0
      else:
        latestclose = tdf.C.iloc[-1]
        totalvol = tdf.V.sum()

      req_ts = time.time() * 1000

      # Log request
      req_log = [start_ts, req_ts, req_ts, 's', pair, 'klines_ticker_pull']
      logging.info(req_log)

    except Exception as e:
      # Log request
      req_log = [start_ts, start_ts, start_ts, str(e).replace(',','|'), pair, 'kalman_upd fail']
      logging.warn(req_log)

      latestclose = totalvol = None

    # Retrieve latest kalman row and update kalman.
    # If no recent trades, decay kalman.
    try:
      lr = KalmanTbl.select().order_by(KalmanTbl.id.desc()).get()

      k_updated = self.kalman_update(pair,
                  latestclose,
                  totalvol,
                  lr.e,
                  lr.yhat,
                  lr.m,
                  lr.Q,
                  lr.K,
                  lr.P,
                  lr.R,
                  lr.Ve,
                  lr.max_vol
                )

      if (totalvol is None):
        logging.info('{} - No value'.format(pair))
      else:
        logging.info('{} - Update'.format(pair))

      # TODO: relocated the kalman update until after trade execution?
      # TODO: gotta be an easier way to do this....

      # Store updated Kalman
      KalmanTbl.update(
        ts=int(time.time() * 1000),
        C=k_updated['C'],
        V=k_updated['V'],
        e=k_updated['e'],
        yhat=k_updated['yhat'],
        m=k_updated['m'],
        Q=k_updated['Q'],
        K=k_updated['K'],
        P=k_updated['P'],
        R=k_updated['R'],
        Ve=k_updated['Ve'],
        max_vol=k_updated['max_vol']
      ).where(KalmanTbl.id == lr.id).execute()

      final_ts = time.time() * 1000

      # log request
      req_log = [start_ts, final_ts, final_ts, 's', pair, 'kalman_upd']
      logging.info(req_log)

      return(lr.e, lr.Q)

    except Exception as e:
      logging.error("Something went wrong updating the kalman.")
      logging.error(e)
      return(None,None)
