import os
from binance.spot import Spot as Client
from dotenv import load_dotenv
from parse_call import TradingCallParser
from models import TradingCall, Message
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

BINANCE_API_KEY = os.getenv("API_KEY")
BINANCE_API_SECRET = os.getenv("API_SECRET")
BINANCE_API_URL = os.getenv("API_URL")

ORDER_SIZE = 250  # USD per trade

# Create an engine that connects to the database
engine = create_engine("sqlite:///tradingbot.db")
session = sessionmaker(bind=engine)()


def run_binance_api():
    client = Client(base_url=BINANCE_API_URL)

    # Get server timestamp
    print(client.time())
    # Get klines of BTCUSDT at 1m interval
    print(client.klines("BTCUSDT", "1m"))
    # Get last 10 klines of BNBUSDT at 1h interval
    print(client.klines("BNBUSDT", "1h", limit=10))

    # API key/secret are required for user data endpoints
    client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, base_url=BINANCE_API_URL)

    # Get account and balance information
    print(client.account())

    # Post a new order
    params = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT_MAKER",
        "quantity": 0.002,
        "price": 9500,
    }

    response = client.new_order(**params)
    print(response)


def parse_trade():
    # limit pairs available in test api. So, we use BTC
    with open("trading_call_btc.txt", "r") as f:
        content = f.read()
        return TradingCallParser().parse(Message(0, content, datetime.datetime.now()))


def fetch_unseen_trades(latest_first: bool = True, limit=10):
    return (
        session.query(TradingCall)
        .filter(TradingCall.open_order == None)
        .order_by(TradingCall.id.desc())
        .limit(limit)
        .all()
    )


class BinanceAPI:
    def __init__(self):
        self.client = Client(
            BINANCE_API_KEY, BINANCE_API_SECRET, base_url=BINANCE_API_URL
        )

    def send_open_order(self, trade: TradingCall):
        if trade.open_order is not None or trade.side != "BUY":
            # We dont support SHORT orders yet.
            return trade

        # Post a new order
        quantity = round(ORDER_SIZE / trade.entry[0], 6)
        print(quantity)
        params = {
            "symbol": trade.symbol,
            "side": trade.side,
            "type": "LIMIT_MAKER",
            "timeInForce": "GTC",
            "quantity": quantity,
            "price": max(iter(trade.entry)),
        }
        # print(client.ticker_price("BTCUSDT"))
        # print(client.get_order("BTCUSDT", orderId="20200470"))
        response = self.client.new_order(**params)
        print(response)
        print(response["orderId"])
        trade.open_order = response
        return trade

    def send_open_orders(self, trades):
        return [self.send_open_order(trade) for trade in trades]

    def check_pending_orders(self, pendingOrders: list[TradingCall]):
        return [
            trade
            for trade in pendingOrders
            if self.client.get_order("BTCUSDT", orderId=trade.open_order["orderId"])[
                "status"
            ]
            == "FILLED"
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
        qty = float(trade.open_order["origQty"])

        paramsOne = params.copy()
        paramsOne["price"] = trade.targets[2]
        paramsOne["quantity"] = round(qty / 2, 6)
        responseOne = self.client.new_oco_order(**paramsOne)

        print(responseOne)
        paramsTwo = params.copy()
        paramsTwo["price"] = trade.targets[4]
        paramsTwo["quantity"] = qty - paramsOne["quantity"]

        responseTwo = self.client.new_oco_order(**paramsTwo)
        print(responseTwo)

        trade.close_orders = [responseOne, responseTwo]
        return trade

    def send_close_orders(self, filledOrders: list[TradingCall]):
        return [self.send_close_order(trade) for trade in filledOrders]


def main():
    binance_api = BinanceAPI()
    pendingLimitOrders = (
        session.query(TradingCall)
        .filter(TradingCall.open_order is not None)
        .filter(TradingCall.close_orders is None)
        .all()
    )
    # Get account and balance information
    print(binance_api.client.account())
    print(pendingLimitOrders)
    filledLimitOrders = binance_api.check_pending_orders(pendingLimitOrders)
    binance_api.send_close_orders(filledLimitOrders)
    unseen_trades = fetch_unseen_trades(
        latest_first=True, limit=10
    )  # TODO: limit = BUSD available / ORDER_SIZE
    print(unseen_trades)
    pendingLimitOrders = binance_api.send_open_orders(unseen_trades)

    # TODO: Token accounting
    # TODO: see all the pending orders and if they've been too long pending, cull

    # send_close/open_orders mutate the entities in the database
    session.commit()


main()
