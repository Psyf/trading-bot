import os
import time
from binance.spot import Spot
from dotenv import load_dotenv
from models import Trade
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import traceback
from utils import *
import itertools
from bot import Bot

# SETUP ENV
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)
BINANCE_API_KEY = os.getenv("API_KEY")
BINANCE_API_SECRET = os.getenv("API_SECRET")
BINANCE_API_URL = os.getenv("API_URL")

# SETUP DB
engine = create_engine("sqlite:///tradingbot.db")
SESSION = sessionmaker(bind=engine)()

# CONSTANTS
ORDER_SIZE = 100  # USD per trade
ORDER_EXPIRY_TIME_HOURS = 24  # 1 day
DELAY_BETWEEN_STEPS = 10  # seconds
TARGET_NUM = 3

LOGGER = setup_logger("spotoor")


class SpotBot(Bot):
    client: Spot

    def __init__(self, api_key, api_secret, api_url, session, logger):
        super().__init__(Spot, api_key, api_secret, api_url, session, logger)

    def get_price(self, symbol):
        return float(self.client.avg_price(symbol)["price"])

    def get_order(self, symbol, orderId):
        return self.client.get_order(symbol, orderId=orderId)

    def send_open_order(self, trade: Trade):
        if trade.open_order is not None or trade.side != "BUY":
            # We dont support SHORT orders yet.
            return trade

        try:
            info = self.client.exchange_info(trade.symbol)["symbols"][0]
            # TODO sanity check on the asset pair
            quantity = format_quantity(ORDER_SIZE / max(iter(trade.entry)), info)

            params = {
                "symbol": trade.symbol,
                "side": trade.side,
                "type": "LIMIT",
                "quantity": quantity,
                "price": format_price(max(iter(trade.entry)), info),
                # TODO this might help avoid calling get_order again. need to confirm
                "newOrderRespType": "FULL",
                "timeInForce": "GTC",
            }

            response = self.client.new_order(**params)
            confirmed_order = self.get_order(trade.symbol, orderId=response["orderId"])
            trade.open_order = confirmed_order

            self.session.add(trade)
            self.session.commit()
            self.logger.info(f"New opening order => {trade.id} : {trade.open_order}")
        except Exception as e:
            self.logger.error(
                f"Could not create new opening order => {trade.id}/{trade.symbol} : {e}"
            )

        return trade

    def filter_need_to_stop_loss(self, trades):
        return [
            trade for trade in trades if self.get_price(trade.symbol) < trade.stop_loss
        ]

    def send_take_profit_order(self, trade: Trade):
        params = {
            "symbol": trade.symbol,
            "side": "SELL" if trade.side == "BUY" else "BUY",
            "newOrderRespType": "FULL",
        }
        try:
            info = self.client.exchange_info(trade.symbol)["symbols"][0]

            fills = self.client.my_trades(
                trade.symbol, orderId=trade.open_order["orderId"]
            )
            qty = float(trade.open_order["executedQty"]) - sum(
                float(fill["commission"]) for fill in fills
            )
            params["quantity"] = format_quantity(qty, info)

            current_price = self.get_price(trade.symbol)
            target = format_price(trade.targets[TARGET_NUM], info)
            if current_price > target:
                params["type"] = "MARKET"
            else:
                params["type"] = "LIMIT"
                params["timeInForce"] = "GTC"
                params["price"] = target

            response = self.client.new_order(**params)

            trade.take_profit_order = response
            self.session.add(trade)
            self.session.commit()
            self.logger.info(f"New close order => {trade.id} : {response}")

        except Exception as e:
            self.logger.error(
                f"Could not create new close order => {trade.id}/{trade.symbol} : {params} : {e} {traceback.format_exc()}"
            )

        return trade

    def send_take_profit_orders(self, filledOrders: list[Trade]):
        return [self.send_take_profit_order(trade) for trade in filledOrders]

    def send_cancel_take_profit_orders(self, trades: list[Trade]):
        for trade in trades:
            try:
                trade.take_profit_order = self.client.cancel_order(
                    trade.symbol, orderId=trade.take_profit_order["orderId"]
                )
            except:
                self.logger.info(
                    f"Could not cancel close order => {trade.id}/{trade.symbol}"
                )

            try:
                trade.stop_loss_order = self.client.new_order(
                    **{
                        "symbol": trade.symbol,
                        "side": "SELL" if trade.side == "BUY" else "BUY",
                        "type": "MARKET",
                        "quantity": float(trade.take_profit_order["origQty"]),
                        "newOrderRespType": "FULL",
                    }
                )
                trade.closed = 1
                self.session.commit()
                self.logger.info(f"Cancelled close order => {trade.id}/{trade.symbol}")
            except:
                self.logger.error(
                    f"Could not market order => {trade.id}/{trade.symbol}"
                )

    def step(self):
        self.logger.debug("--- NEW STEP ---")

        pendingOpeningOrders = self.get_trades_with_pending_opening_order()
        self.logger.debug(f"Pending opening orders => {pendingOpeningOrders}")
        filledOpeningOrders = self.filter_trades_with_filled_order(
            self.update_order_statuses(pendingOpeningOrders, "open_order"), "open_order"
        )

        pendingTakeProfitOrders = self.get_trades_with_pending_take_profit_order()
        self.logger.debug(f"Pending take_profit orders => {pendingTakeProfitOrders}")
        self.update_order_statuses(pendingTakeProfitOrders, "take_profit_order")

        self.send_take_profit_orders(filledOpeningOrders)

        # Cull orders taking too long to fill
        self.cancel_open_orders(
            self.filter_trades_with_orders_taking_too_long_to_fill(
                self.get_trades_with_pending_opening_order(),
                "open_order",
                ORDER_EXPIRY_TIME_HOURS,
            )
        )
        self.send_cancel_take_profit_orders(
            self.filter_trades_with_orders_taking_too_long_to_fill(
                self.get_trades_with_pending_take_profit_order(),
                "take_profit_order",
                ORDER_EXPIRY_TIME_HOURS,
            )
        )

        # STOP LOSS
        self.send_cancel_take_profit_orders(
            self.filter_need_to_stop_loss(
                self.get_trades_with_pending_take_profit_order()
            )
        )

        # Get account and balance information
        account_balance = float(
            [
                b["free"]
                for b in self.client.account()["balances"]
                if b["asset"] == "USDT"
            ][0]
        )

        if account_balance > ORDER_SIZE:
            unseen_trades = self.get_unexecuted_trades(latest_first=True, limit=100)
            self.logger.debug(f"Unseen trades => {unseen_trades}")
            viable_trades = self.filter_viable_trades(unseen_trades)
            pendingOpeningOrders = self.send_open_orders(
                itertools.islice(viable_trades, int(account_balance // ORDER_SIZE))
            )
        else:
            self.logger.debug("!!! Insufficient USDT balance !!!")

        # TODO: Token accounting


def main():
    bot = SpotBot(BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_API_URL, SESSION, LOGGER)

    while True:
        try:
            bot.step()
        except Exception:
            # logger.info detailed trace of the error
            LOGGER.error("!!! step failed :/ !!!")
            LOGGER.error(traceback.format_exc())

        time.sleep(DELAY_BETWEEN_STEPS)


main()
