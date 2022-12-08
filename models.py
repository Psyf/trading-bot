from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, Enum, Boolean
from sqlalchemy.ext.declarative import declarative_base
from dataclasses import dataclass
import datetime

Base = declarative_base()


@dataclass
class TradingCall(Base):
    __tablename__ = "trading_calls"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    side = Column(Enum("BUY", "SELL"), nullable=False)
    entry = Column(JSON, nullable=False)  # Should be [float, float]
    stop_loss = Column(Float, nullable=False)
    targets = Column(JSON, nullable=False)  # should be float[6]
    timestamp = Column(DateTime, nullable=False)
    open_order = Column(JSON)  # should be {open_order}
    close_order = Column(JSON)  # should be {close_order}
    texthash = Column(String, nullable=False)
    bragged = Column(Boolean, nullable=False, default=False)
    completed = Column(Boolean, nullable=False, default=False)
    reason = Column(String, nullable=True)

    def __repr__(self):
        return f"TradingCall({self.id}, {self.timestamp}, {self.symbol}, {self.side}, entry={self.entry}, stop_loss={self.stop_loss}, targets={self.targets}, open_order={self.open_order}, close_order={self.close_order}, texthash={self.texthash}, bragged={self.bragged}, completed={self.completed}, reason={self.reason})"


@dataclass
class Message:
    id: int
    text: str
    date: datetime.datetime
