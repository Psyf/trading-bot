from binance.um_futures import UMFutures
import os
import time
from typing import List
from dotenv import load_dotenv
from models import Trade
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import traceback
from utils import format_quantity, format_price, setup_logger
import itertools
from bot import Bot

# SETUP ENV
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)
BINANCE_API_KEY = os.getenv("FUTURES_API_KEY")
BINANCE_API_SECRET = os.getenv("FUTURES_API_SECRET")
BINANCE_API_URL = os.getenv("FUTURES_API_URL")

# SETUP DB
engine = create_engine("sqlite:///tradingbot.db")
SESSION = sessionmaker(bind=engine)()

# CONSTANTS
ORDER_SIZE = 1000  # USD per trade
ORDER_EXPIRY_TIME_HOURS = 24  # 1 day
DELAY_BETWEEN_STEPS = 10  # seconds
TARGET_NUM = 3
LEVERAGE = 10

LOGGER = setup_logger("futoor")


class FuturesBot(Bot):
    client: UMFutures

    def __init__(self, api_key, api_secret, api_url, session, logger):
        super().__init__(UMFutures, api_key, api_secret, api_url, session, logger)

    def get_price(self, symbol: str):
        return float(self.client.mark_price(symbol)["markPrice"])

    def get_order(self, symbol: str, order_id: int):
        return self.client.query_order(symbol=symbol, orderId=order_id)

    def send_open_order(self, trade: Trade):
        """
        Have to long/short + TP + SL separately because atomic endpoint is private
        See: https://dev.binance.vision/t/how-to-implement-otoco-tp-sl-orders-using-api/1622/18
        """
        if trade.open_order is not None:
            return trade

        try:
            position_risk = self.client.get_position_risk(symbol=trade.symbol)[0]

            if position_risk["marginType"].lower() != "isolated":
                self.client.change_margin_type(str(trade.symbol), "ISOLATED")
            if position_risk["leverage"] != LEVERAGE:
                self.client.change_leverage(str(trade.symbol), LEVERAGE)
        except Exception as e:
            self.logger.error(
                f"Could not change margin type/leverage => {trade.id}/{trade.symbol} : {e}"
            )
            return

        info = [
            x
            for x in self.client.exchange_info()["symbols"]
            if x.get("symbol") == trade.symbol
        ][0]
        # TODO sanity check on the asset pair
        price = (
            max(iter(trade.entry)) if trade.side == "BUY" else min(iter(trade.entry))
        )
        quantity = format_quantity(ORDER_SIZE * LEVERAGE / price, info)

        # open the long/short position
        try:
            params = {
                "symbol": trade.symbol,
                "side": trade.side,
                "type": "LIMIT",
                "quantity": quantity,
                "reduceOnly": "false",
                "price": format_price(price, info),
                "newOrderRespType": "FULL",
                "timeInForce": "GTC",
            }

            response = self.client.new_order(**params)
            confirmed_order = self.get_order(str(trade.symbol), response["orderId"])
            trade.open_order = confirmed_order

            self.session.add(trade)
            self.session.commit()
            self.logger.info(f"New opening order => {trade.id} : {trade.open_order}")
        except Exception as e:
            self.logger.error(
                f"Could not create new opening order => {trade.id}/{trade.symbol} : {e}"
            )
            return

        return trade

    def send_tpsl_orders(self, trades: List[Trade]):
        return [
            item
            for item in [self.send_tpsl_order(trade) for trade in trades]
            if item is not None
        ]

    def send_tpsl_order(self, trade):
        try:
            info = [
                x
                for x in self.client.exchange_info()["symbols"]
                if x.get("symbol") == trade.symbol
            ][0]
        except Exception as e:
            self.logger.error(f"Could not get info for {trade.symbol}: {str(e)}")
            return

        quantity = trade.open_order["executedQty"]

        # create the stop loss order
        try:
            params = {
                "symbol": trade.symbol,
                "side": "SELL" if trade.side == "BUY" else "BUY",
                "type": "STOP_MARKET",
                "quantity": quantity,
                "reduceOnly": "true",
                "stopPrice": format_price(trade.stop_loss, info),
                "newOrderRespType": "FULL",
                "timeInForce": "GTE_GTC",
                "workingType": "MARK_PRICE",
            }

            response = self.client.new_order(**params)
            confirmed_order = self.get_order(trade.symbol, response["orderId"])
            trade.stop_loss_order = confirmed_order

            self.session.add(trade)
            self.session.commit()
            self.logger.info(
                f"New stop loss order => {trade.id} : {trade.stop_loss_order}"
            )
        except Exception as e:
            self.logger.error(
                f"Could not create new stop loss order => {trade.id}/{trade.symbol} : {e}"
            )
            return

        # create the take profit order
        try:
            params = {
                "symbol": trade.symbol,
                "side": "SELL" if trade.side == "BUY" else "BUY",
                "type": "TAKE_PROFIT_MARKET",
                "quantity": quantity,
                "reduceOnly": "true",
                "stopPrice": format_price(trade.targets[TARGET_NUM], info),
                "newOrderRespType": "FULL",
                "timeInForce": "GTE_GTC",
                "workingType": "MARK_PRICE",
            }

            response = self.client.new_order(**params)
            confirmed_order = self.get_order(trade.symbol, response["orderId"])
            trade.take_profit_order = confirmed_order

            self.session.add(trade)
            self.session.commit()
            self.logger.info(
                f"New take profit order => {trade.id} : {trade.take_profit_order}"
            )
        except Exception as e:
            self.logger.error(
                f"Could not create new take profit order => {trade.id}/{trade.symbol} : {e}"
            )
            return

        return trade

    def cancel_tpsl_orders_and_close_position(self, trades: list[Trade]):
        """
        If you're cancelling a position that has filled open but did not trigger sl/tp,
        you just have to market sell and tp/sl will be cancelled automatically

        Note: If either of the tp/sl orders are filled, you don't have to do anything!
        """
        for trade in trades:
            try:
                self.client.new_order(
                    **{
                        "symbol": trade.symbol,
                        "side": "SELL" if trade.side == "BUY" else "BUY",
                        "type": "MARKET",
                        "quantity": float(trade.open_order["origQty"]),
                        "newOrderRespType": "FULL",
                    }
                )
                trade.closed = 1
                self.session.commit()
                self.logger.info(f"closed position => {trade.id}/{trade.symbol}")
            except Exception as e:
                self.logger.error(
                    f"Could not close position => {trade.id}/{trade.symbol}: {str(e)}"
                )

    def step(self):
        self.logger.debug("--- NEW STEP ---")

        pendingOpeningOrders = self.get_trades_with_pending_opening_order()
        self.logger.debug(f"Pending opening orders => {pendingOpeningOrders}")
        filledOpeningOrders = self.filter_trades_with_filled_order(
            self.update_order_statuses(pendingOpeningOrders, "open_order"), "open_order"
        )

        pendingTpSlOrders = self.get_trades_with_pending_take_profit_order()
        self.logger.debug(f"Pending tp/sl orders => {pendingTpSlOrders}")
        pendingTpSlOrders = self.update_order_statuses(
            pendingTpSlOrders, "take_profit_order"
        )
        self.update_order_statuses(pendingTpSlOrders, "stop_loss_order")

        self.send_tpsl_orders(filledOpeningOrders)

        # Cull orders taking too long to fill
        self.cancel_open_orders(
            self.filter_trades_with_orders_taking_too_long_to_fill(
                self.get_trades_with_pending_opening_order(),
                "open_order",
                ORDER_EXPIRY_TIME_HOURS,
            ),
        )
        self.cancel_tpsl_orders_and_close_position(
            self.filter_trades_with_orders_taking_too_long_to_fill(
                self.get_trades_with_pending_take_profit_order(),
                "take_profit_order",
                ORDER_EXPIRY_TIME_HOURS,
            ),
        )

        # Get account and balance information
        account_balance = float(
            [
                b["availableBalance"]
                for b in self.client.account()["assets"]
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
    bot = FuturesBot(
        BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_API_URL, SESSION, LOGGER
    )

    while True:
        try:
            bot.step()
        except Exception:
            # self.logger.info detailed trace of the error
            LOGGER.error("!!! step failed :/ !!!")
            LOGGER.error(traceback.format_exc())

        time.sleep(DELAY_BETWEEN_STEPS)


main()
