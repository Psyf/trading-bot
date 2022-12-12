from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Float,
    JSON,
    Enum,
    SmallInteger,
)
from sqlalchemy.ext.declarative import declarative_base
from typing import Literal, TypeAlias
from dataclasses import dataclass

Base = declarative_base()

OrderType = Literal["open_order", "take_profit_order", "stop_loss_order"]


@dataclass
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    side = Column(Enum("BUY", "SELL"), nullable=False)
    entry = Column(JSON, nullable=False)  # Should be [float, float]
    stop_loss = Column(Float, nullable=False)
    targets = Column(JSON, nullable=False)  # should be float[6]
    timestamp = Column(DateTime, nullable=False)
    texthash = Column(String, nullable=False)
    bragged = Column(SmallInteger, nullable=False, server_default="0")
    open_order = Column(JSON)  # should be {open_order}
    take_profit_order = Column(JSON)  # should be {take_profit_order}
    stop_loss_order = Column(JSON)  # should be {stop_loss_order}
    closed = Column(SmallInteger, nullable=False, server_default="0")

    def __repr__(self):
        return f"Trade({self.id}, {self.timestamp}, {self.symbol}, {self.side}, entry={self.entry}, stop_loss={self.stop_loss}, targets={self.targets}, texthash={self.texthash}, bragged={self.bragged}, open_order={self.open_order}, take_profit_order={self.take_profit_order}, stop_loss_order={self.stop_loss_order}, closed={self.closed})"
