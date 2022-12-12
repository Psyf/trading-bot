from typing import List, Type, Literal, TypeAlias
from binance.spot import Spot
from binance.um_futures import UMFutures
from models import Trade, OrderType
import datetime
from sqlalchemy.orm import Session
from logging import Logger


class Bot:
    def __init__(
        self,
        ClientClass: Type[Spot] | Type[UMFutures],
        api_key: str,
        api_secret: str,
        api_url: str,
        session: Session,
        logger: Logger,
    ):
        self.client = ClientClass(api_key, api_secret, base_url=api_url)
        self.session = session
        self.logger = logger

    def send_open_orders(self, trades):
        return [
            item
            for item in [self.send_open_order(trade) for trade in trades]
            if item is not None
        ]

    def filter_viable_trades(self, trades: List[Trade]):
        for trade in trades:
            # # ONLY FOR TEST NET. It has a limited asset list ###
            # if trade.symbol != "LTCUSDT":
            #     continue
            if trade.side == "BUY":
                max_price = trade.targets[0]
                min_price = trade.stop_loss
            elif trade.side == "SELL":
                min_price = trade.targets[0]
                max_price = trade.stop_loss

            try:
                current_price = self.get_price(trade.symbol)
            except:
                self.logger.error(f"Could not get price => {trade.id}/{trade.symbol}")
                continue

            if current_price < min_price or current_price > max_price:
                self.logger.debug(
                    f"Skipping because price not in range => {trade.id}/{trade.symbol}"
                )
                continue
            else:
                yield trade

    def filter_trades_with_filled_order(
        self,
        trades: list[Trade],
        order_type: str,
    ):
        return [
            trade
            for trade in trades
            if getattr(trade, order_type).get("status", None) == "FILLED"
        ]

    def filter_trades_with_orders_taking_too_long_to_fill(
        self, trades: list[Trade], order_type, max_expiry_hours: int
    ):
        return [
            trade
            for trade in trades
            if getattr(trade, order_type).get("status", None)
            == "NEW"  # TODO: What about partially filled ones?
            and (
                datetime.datetime.now()
                - datetime.datetime.fromtimestamp(
                    (
                        getattr(trade, order_type).get("time", None)
                        or getattr(trade, order_type).get("transactTime", None)
                    )
                    // 1000
                )
            )
            > datetime.timedelta(hours=max_expiry_hours)
        ]

    def update_order_status(
        self,
        trade: Trade,
        order_type: OrderType,
    ):
        order = self.get_order(trade.symbol, getattr(trade, order_type)["orderId"])
        if order["status"] != getattr(trade, order_type).get("status", None):
            setattr(trade, order_type, order)
            self.session.add(trade)
            self.session.commit()
            self.logger.info(f"updated status {order_type} => {trade.id} : {order}")
        return trade

    def update_order_statuses(self, trades: list[Trade], order_type: OrderType):
        return [self.update_order_status(trade, order_type) for trade in trades]

    def cancel_open_orders(self, trades: list[Trade]):
        for trade in trades:
            try:
                trade.open_order = self.client.cancel_order(
                    trade.symbol, orderId=trade.open_order["orderId"]
                )
                trade.closed = 1
                self.session.commit()
                self.logger.info(f"Cancelled open order => {trade.id}/{trade.symbol}")
            except:
                self.logger.info(
                    f"Could not cancel open order => {trade.id}/{trade.symbol}"
                )

    def get_unexecuted_trades(
        self, latest_first: bool = True, limit=10, lookback_hours=12
    ):
        return (
            self.session.query(Trade)
            .filter(Trade.open_order.is_(None))
            .filter(
                Trade.timestamp
                >= datetime.datetime.now() - datetime.timedelta(hours=lookback_hours)
            )
            .filter(Trade.bragged == 0)
            .order_by(Trade.id.desc() if latest_first else Trade.id.asc())
            .limit(limit)
            .all()
        )

    def get_trades_with_pending_opening_order(self):
        return (
            self.session.query(Trade)
            .filter(Trade.open_order.is_not(None))
            .filter(Trade.take_profit_order.is_(None))
            .filter(Trade.closed == 0)
            .all()
        )

    def get_trades_with_pending_take_profit_order(self):
        return (
            self.session.query(Trade)
            .filter(Trade.take_profit_order.is_not(None))
            .filter(Trade.closed == 0)
            .all()
        )

    def send_open_order(self, trade):
        raise NotImplementedError

    def get_price(self, symbol):
        raise NotImplementedError

    def get_order(self, symbol, orderId):
        raise NotImplementedError
