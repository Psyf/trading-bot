from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, Enum, ARRAY
from sqlalchemy.ext.mutable import MutableList, MutableDict
from sqlalchemy.ext.declarative import declarative_base
from dataclasses import dataclass
import datetime

Base = declarative_base()


@dataclass
class TradingCall(Base):
    __tablename__ = "trading_calls"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(Enum("BUY", "SELL"))
    entry = Column(JSON)
    stop_loss = Column(Float)
    targets = Column(JSON)
    timestamp = Column(DateTime)
    open_order = Column(JSON)
    close_orders = Column(JSON)

    def __repr__(self):
        return f"TradingCall({self.id}, {self.timestamp}, {self.symbol}, {self.side}, entry={self.entry}, stop_loss={self.stop_loss}, targets={self.targets}, open_order={self.open_order}, close_orders={self.close_orders})"


@dataclass
class Message:
    id: int
    text: str
    date: datetime.datetime
