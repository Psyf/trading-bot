import os
from binance.spot import Spot as Client
from dotenv import load_dotenv
from parse_call import TradingCall, TradingCallParser

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
API_URL = os.getenv("API_URL")

ORDER_SIZE = 250  # USD per trade


def run_binance_api():
    client = Client(base_url=API_URL)

    # Get server timestamp
    print(client.time())
    # Get klines of BTCUSDT at 1m interval
    print(client.klines("BTCUSDT", "1m"))
    # Get last 10 klines of BNBUSDT at 1h interval
    print(client.klines("BNBUSDT", "1h", limit=10))

    # API key/secret are required for user data endpoints
    client = Client(API_KEY, API_SECRET, base_url=API_URL)

    # Get account and balance information
    print(client.account())

    # Post a new order
    params = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": 0.002,
        "price": 9500,
    }

    response = client.new_order(**params)
    print(response)


def parse_trade():
    # limit pairs available in test api. So, we use BTC
    with open("trading_call_btc.txt", "r") as f:
        content = f.read()
        print(content)
        return TradingCallParser().parse(content)


def fetch_trades():
    return [parse_trade()]


class BinanceAPI:
    def __init__(self):
        self.client = Client(API_KEY, API_SECRET, base_url=API_URL)

    def send_open_order(self, trade: TradingCall):
        if not trade.open_order == {} or not trade.side == "BUY":
            # We dont support SHORT orders yet.
            return trade
        # Get account and balance information
        print(self.client.account())

        # Post a new order
        quantity = round(ORDER_SIZE / trade.entry[0], 6)

        params = {
            "symbol": trade.symbol,
            "side": trade.side,
            "type": "LIMIT_MAKER",
            "timeInForce": "GTC",
            "quantity": quantity,
            "price": max(trade.entry),
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
            "type": "OCO",
            "stopLimitTimeInForce": "GTC",
            "stopLimitPrice": round(
                trade.stop_loss * (0.99 if trade.side == "BUY" else 1.01), 6
            ),
            "stopPrice": trade.stop_loss,
        }
        qty = float(trade.open_order["origQty"])
        paramsOne = params.copy()
        paramsOne["price"] = trade.targets[2]
        paramsOne["quantity"] = round(qty / 2)
        responseOne = self.client.new_order(**paramsOne)

        print(responseOne)
        paramsTwo = params.copy()
        paramsTwo["price"] = trade.targets[4]
        paramsTwo["quantity"] = qty - paramsOne["quantity"]

        responseTwo = self.client.new_order(**paramsTwo)
        print(responseTwo)

        trade.close_orders = [responseOne, responseTwo]
        return trade

    def send_close_orders(self, filledOrders: list[TradingCall]):
        return [self.send_close_order(trade) for trade in filledOrders]


def main():
    binance_api = BinanceAPI()
    pendingOrders = []  # read pending orders from sqlite
    filledOrders = binance_api.check_pending_orders(pendingOrders)
    binance_api.send_close_orders(filledOrders)

    # TODO read from telegram bot
    trades = fetch_trades()
    pendingOrders = binance_api.send_open_orders(trades)
    # TODO - save pendingOrders to sql lite


main()
