import os
import time
from typing import List
from binance.spot import Spot as Client
from dotenv import load_dotenv
from parse_call import TradingCallParser
from models import TradingCall, Message
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import traceback

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

BINANCE_API_KEY = os.getenv("API_KEY")
BINANCE_API_SECRET = os.getenv("API_SECRET")
BINANCE_API_URL = os.getenv("API_URL")

ORDER_SIZE = 250  # USD per trade

# Create an engine that connects to the database
engine = create_engine("sqlite:///tradingbot.db")
session = sessionmaker(bind=engine)()


def step_size_to_precision(ss):
    return ss.find("1") - 1


def fetch_unseen_trades(latest_first: bool = True, limit=10, lookback_hours=1):
    return (
        session.query(TradingCall)
        .filter(TradingCall.open_order == None)
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

            # ONLY FOR TEST NET. It has a limited asset list ###
            if trade.symbol != "LTCUSDT":
                continue

            current_price = float(self.client.avg_price(trade.symbol)["price"])

            if current_price < min_price or current_price > max_price:
                print("skipping {}".format(trade.symbol))
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

        qty_precision = step_size_to_precision(
            [i["stepSize"] for i in info["filters"] if i["filterType"] == "LOT_SIZE"][0]
        )

        price_filters = [
            i for i in info["filters"] if i["filterType"] == "PRICE_FILTER"
        ][0]
        price_precision = step_size_to_precision(price_filters["tickSize"])

        # Post a new order
        quantity = round(ORDER_SIZE / trade.entry[0], qty_precision)

        params = {
            "symbol": trade.symbol,
            "side": trade.side,
            "type": "LIMIT_MAKER",
            "quantity": quantity,
            "price": round(max(iter(trade.entry)), price_precision),
        }

        response = self.client.new_order(**params)
        print("New limit order creation response =>", response)
        confirmed_order = self.client.get_order(
            trade.symbol, orderId=response["orderId"]
        )
        trade.open_order = confirmed_order
        return trade

    def send_open_orders(self, trades):
        return [self.send_open_order(trade) for trade in trades]

    def update_order_status(self, trade: TradingCall):
        order = self.client.get_order(trade.symbol, orderId=trade.open_order["orderId"])
        if order["status"] != trade.open_order.get("status", None):
            trade.open_order = order

        return trade

    def update_order_statuses(self, pendingOrders: list[TradingCall]):
        return [self.update_order_status(trade) for trade in pendingOrders]

    def filter_filled_orders(self, trades):
        return [
            trade
            for trade in trades
            if trade.open_order.get("status", None) == "FILLED"
        ]

    def send_close_order(self, trade: TradingCall):
        params = {
            "symbol": trade.symbol,
            "side": "SELL" if trade.side == "BUY" else "BUY",
            "stopLimitTimeInForce": "GTC",
            "stopLimitPrice": round(
                trade.stop_loss * (0.99 if trade.side == "BUY" else 1.01), 6
            ),
            "stopPrice": trade.stop_loss,
        }
        qty = float(trade.open_order["executedQty"])

        paramsOne = params.copy()
        paramsOne["price"] = trade.targets[2]
        paramsOne["quantity"] = round(qty / 2, 6)
        responseOne = self.client.new_oco_order(**paramsOne)

        print("OCO Order 1 => ", responseOne)
        confirmedOrderOne = self.client.get_order(
            trade.symbol, orderId=responseOne["orderId"]
        )
        paramsTwo = params.copy()
        paramsTwo["price"] = trade.targets[4]
        paramsTwo["quantity"] = qty - paramsOne["quantity"]

        responseTwo = self.client.new_oco_order(**paramsTwo)
        confirmedOrderTwo = self.client.get_order(
            trade.symbol, orderId=responseTwo["orderId"]
        )
        print("OCO Order 2 => ", responseTwo)

        trade.close_orders = [confirmedOrderOne, confirmedOrderTwo]
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
    print("--- NEW STEP ---")
    print("Pending limit orders =>", pendingLimitOrders)

    # for o in pendingLimitOrders:
    #     o.open_order = sql.null()
    # session.commit()
    # return
    filledLimitOrders = binance_api.update_order_statuses(pendingLimitOrders)
    print("Filled limit orders =>", filledLimitOrders)
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
            latest_first=True, limit=50
        )  # TODO: limit = BUSD available / ORDER_SIZE

        print("Unseen trades =>", unseen_trades)
        viable_trades = binance_api.filter_viable_trades(unseen_trades)
        pendingLimitOrders = binance_api.send_open_orders(viable_trades)
    else:
        print("!!! Insufficient USDT balance !!!")

    # TODO: Token accounting
    # TODO: see all the pending orders and if they've been too long pending, cull

    # send_close/open_orders mutate the entities in the database
    session.commit()


def main():
    binance_api = BinanceAPI()

    while True:
        try:
            step(binance_api)
        except Exception as e:
            # print detailed trace of the error
            print("!!! step failed :/ !!!")
            print(traceback.format_exc())

        time.sleep(30)


main()
