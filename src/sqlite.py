from peewee import *
import datetime

db = SqliteDatabase('bitmex1.db')
# conn = sqlite3.connect('/tmp/20180420.db')

class BaseModel(Model):
  class Meta:
    database = db

class Orders(BaseModel):
  ts = IntegerField()
  price = FloatField()
  amount = FloatField()
  value = FloatField()
  b_a = TextField()

class Ticker(BaseModel):
  ts = IntegerField()
  dateteime = IntegerField()
  close = FloatField()
  high = FloatField()
  vol = FloatField()
  volvalue = FloatField()
  buy = FloatField()
  sell = FloatField()
  change = FloatField()
  changerate = FloatField()
  lastDealPrice = FloatField()

class Requests(BaseModel):
  start_ts = IntegerField()
  req_ts = IntegerField()
  final_ts = IntegerField()
  msg = TextField()
  pair = TextField()
  inst = TextField()

class Balances(BaseModel):
  ts = IntegerField()
  coin = TextField()
  balance = FloatField()
  freeze = FloatField()

class KalmanTbl(BaseModel):
  ts = IntegerField()
  C = FloatField()
  V = FloatField()
  e = FloatField()
  yhat = FloatField()
  m = FloatField()
  Q = FloatField()
  K = FloatField()
  P = FloatField()
  R = FloatField()
  Ve = FloatField()
  max_vol = FloatField()

