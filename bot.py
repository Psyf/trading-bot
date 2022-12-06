import os
import time
from typing import List
from binance.spot import Spot as Client
from dotenv import load_dotenv
from models import TradingCall
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import traceback
import logging
import sys

# SETUP ENV
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)
BINANCE_API_KEY = os.getenv("API_KEY")
BINANCE_API_SECRET = os.getenv("API_SECRET")
BINANCE_API_URL = os.getenv("API_URL")

# SETUP DB
engine = create_engine("sqlite:///tradingbot.db")
session = sessionmaker(bind=engine)()

# CONSTANTS
ORDER_SIZE = 100  # USD per trade

# SETUP LOGGING to log to file with timestamp and console and auto-rotate
logging.basicConfig(
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(
            "logs/binance-" + datetime.datetime.utcnow().strftime("%s") + ".log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
    level=logging.INFO,
)


def step_size_to_precision(ss):
    return ss.find("1") - 1


def format_quantity(qty: float, exchange_info):
    qty_precision = step_size_to_precision(
        [
            i["stepSize"]
            for i in exchange_info["filters"]
            if i["filterType"] == "LOT_SIZE"
        ][0]
    )
    return round(qty, qty_precision)


def format_price(price: float, exchange_info):
    price_precision = step_size_to_precision(
        [i for i in exchange_info["filters"] if i["filterType"] == "PRICE_FILTER"][0][
            "tickSize"
        ]
    )
    return round(price, price_precision)


def fetch_unseen_trades(latest_first: bool = True, limit=10, lookback_hours=1):
    return (
        session.query(TradingCall)
        .filter(TradingCall.open_order.is_(None))
        .filter(
            TradingCall.timestamp
            >= datetime.datetime.now() - datetime.timedelta(hours=lookback_hours)
        )
        .order_by(TradingCall.id.desc() if latest_first else TradingCall.id.asc())
        .limit(limit)
        .all()
    )


class BinanceAPI:
    def __init__(self):
        self.client = Client(
            BINANCE_API_KEY, BINANCE_API_SECRET, base_url=BINANCE_API_URL
        )

    def filter_viable_trades(self, trades: List[TradingCall]):
        for trade in trades:
            max_price = trade.targets[2]
            min_price = trade.stop_loss

            # # ONLY FOR TEST NET. It has a limited asset list ###
            # if trade.symbol != "LTCUSDT":
            #     continue

            current_price = float(self.client.avg_price(trade.symbol)["price"])

            if current_price < min_price or current_price > max_price:
                logging.info("skipping {}".format(trade.symbol))
                # for testing.
                # trade.entry = [
                #     round(current_price * 0.99, 5),
                #     round(current_price * 0.98, 5),
                # ]
                # trade.targets[5] = round(current_price * 1.02, 5)
                # yield trade
                continue
            else:
                yield trade

    def send_open_order(self, trade: TradingCall):
        if trade.open_order is not None or trade.side != "BUY":
            # We dont support SHORT orders yet.
            return trade

        info = self.client.exchange_info(trade.symbol)["symbols"][0]
        # TODO sanity check on the asset pair
        assert info["ocoAllowed"]
        quantity = format_quantity(ORDER_SIZE / trade.entry[0], info)

        params = {
            "symbol": trade.symbol,
            "side": trade.side,
            "type": "LIMIT_MAKER",
            "quantity": quantity,
            "price": format_price(max(iter(trade.entry)), info),
            # TODO this might help avoid calling get_order again. need to confirm
            "newOrderRespType": "FULL",
        }

        response = self.client.new_order(**params)
        confirmed_order = self.client.get_order(
            trade.symbol, orderId=response["orderId"]
        )
        trade.open_order = confirmed_order

        session.add(trade)
        session.commit()
        logging.info(f"New limit order => {trade.id} : {trade.open_order}")

        return trade

    def send_open_orders(self, trades):
        return [self.send_open_order(trade) for trade in trades]

    def update_order_status(self, trade: TradingCall):
        order = self.client.get_order(trade.symbol, orderId=trade.open_order["orderId"])
        if order["status"] != trade.open_order.get("status", None):
            trade.open_order = order
            session.add(trade)
            session.commit()
            logging.info(f"Filled limit order => {trade.id} : {order}")
        return trade

    def update_order_statuses(self, pendingOrders: list[TradingCall]):
        return [self.update_order_status(trade) for trade in pendingOrders]

    def filter_filled_orders(self, trades):
        return [
            trade
            for trade in trades
            if trade.open_order.get("status", None) == "FILLED"
        ]

    def send_oco_or_market(self, params, current_price):
        return (
            self.client.new_order(
                **{
                    "symbol": params["symbol"],
                    "side": params["side"],
                    "type": "MARKET",
                    "quantity": params["quantity"],
                    "newOrderRespType": params["newOrderRespType"],
                }
            )
            if current_price > params["price"]
            else self.client.new_oco_order(**params)
        )

    def send_close_order(self, trade: TradingCall):
        info = self.client.exchange_info(trade.symbol)["symbols"][0]
        assert info["ocoAllowed"]
        current_price = float(self.client.avg_price(trade.symbol)["price"])

        params = {
            "symbol": trade.symbol,
            "side": "SELL" if trade.side == "BUY" else "BUY",
            # "stopLimitTimeInForce": "GTC",
            # "stopLimitPrice": format_price(
            #     trade.stop_loss * (0.99 if trade.side == "BUY" else 1.01), info
            # ),
            "stopPrice": format_price(trade.stop_loss, info),
            "newOrderRespType": "FULL",
        }

        qty = float(trade.open_order["executedQty"])
        paramsOne = params.copy()
        # TODO: We are setting the OCO value to market if the target has been hit.
        # This seems to work. Which means the or_market order will only
        # be required if the market price changes. The right way is to probably do a catch and then do a market
        # if the OCO fails for price reasons.
        paramsOne["price"] = format_price(max([trade.targets[2], current_price]), info)
        paramsOne["quantity"] = format_quantity(qty / 2, info)
        responseOne = self.send_oco_or_market(paramsOne, current_price)

        paramsTwo = params.copy()
        paramsTwo["price"] = format_price(max([trade.targets[4], current_price]), info)
        paramsTwo["quantity"] = format_quantity(qty - paramsOne["quantity"], info)

        responseTwo = self.send_oco_or_market(paramsTwo, current_price)
        # confirmedOrderOne = self.client.get_order(
        #     trade.symbol, orderId=responseOne["orderId"]
        # )
        # confirmedOrderTwo = self.client.get_order(
        #     trade.symbol, orderId=responseTwo["orderId"]
        # )

        trade.close_orders = [responseOne, responseTwo]

        session.add(trade)
        session.commit()
        logging.info(f"New oco orders => {trade.id} : {trade.close_orders}")

        return trade

    def send_close_orders(self, filledOrders: list[TradingCall]):
        return [self.send_close_order(trade) for trade in filledOrders]


def step(binance_api: BinanceAPI):
    pendingLimitOrders = (
        session.query(TradingCall)
        .filter(TradingCall.open_order.is_not(None))
        .filter(TradingCall.close_orders.is_(None))
        .all()
    )
    logging.info("--- NEW STEP ---")
    logging.info(f"Pending limit orders => {pendingLimitOrders}")

    # for o in pendingLimitOrders:
    #     o.open_order = sql.null()
    # session.commit()
    # return
    filledLimitOrders = binance_api.update_order_statuses(pendingLimitOrders)
    binance_api.send_close_orders(filledLimitOrders)

    # Get account and balance information
    account_balance = float(
        [
            b["free"]
            for b in binance_api.client.account()["balances"]
            if b["asset"] == "USDT"
        ][0]
    )

    if account_balance > ORDER_SIZE:
        unseen_trades = fetch_unseen_trades(
            latest_first=True, limit=int(account_balance // ORDER_SIZE)
        )
        logging.info(f"Unseen trades => {unseen_trades}")
        viable_trades = binance_api.filter_viable_trades(unseen_trades)
        pendingLimitOrders = binance_api.send_open_orders(viable_trades)
    else:
        logging.info("!!! Insufficient USDT balance !!!")

    # TODO: Token accounting
    # TODO: see all the pending orders and if they've been too long pending, cull


def main():
    binance_api = BinanceAPI()

    while True:
        try:
            step(binance_api)
        except Exception as e:
            # logging.info detailed trace of the error
            logging.error("!!! step failed :/ !!!")
            logging.error(traceback.format_exc())

        time.sleep(30)


main()
