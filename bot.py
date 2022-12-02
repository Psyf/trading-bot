import os
from binance.spot import Spot as Client
from dotenv import load_dotenv
from parse_call import TradingCallParser

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
API_URL = os.getenv("API_URL")


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


def main():
    trade = parse_trade()
    print(trade)
    client = Client(API_KEY, API_SECRET, base_url=API_URL)

    # Get account and balance information
    print(client.account())

    # Post a new order
    quantity = round(1000 / trade.entry[0], 6)

    params = {
        "symbol": trade.symbol,
        "side": trade.side,
        "type": "LIMIT",  # can also do LIMIT_MAKER, maybe lower fees.
        "timeInForce": "GTC",
        "quantity": quantity,
        "price": max(trade.entry),
    }

    response = client.new_order(**params)
    print(response)


main()
