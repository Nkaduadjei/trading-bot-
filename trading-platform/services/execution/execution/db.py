import os
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    """Every order that passed the approval check, including ones the broker rejected."""
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # uniqueness = no double orders
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    symbol: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))      # submitted, filled, rejected, or the broker's own status
    filled_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    reason: Mapped[str] = mapped_column(String(200), default="")
    approved_at: Mapped[int] = mapped_column(Integer)    # when the risk manager approved it
    approval_signature: Mapped[str] = mapped_column(String(64))  # proof it was approved
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class FillRow(Base):
    __tablename__ = "fills"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float)


class EquityRow(Base):
    """A reading of the account after each order (and on request), for the equity curve."""
    __tablename__ = "equity_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    positions: Mapped[str] = mapped_column(Text)         # JSON: symbol -> quantity


class PriceRow(Base):
    """Last known price per symbol, used to rebuild the paper account after a restart."""
    __tablename__ = "paper_prices"
    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class MetaRow(Base):
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


def make_session_factory(url: str):
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool
    engine = create_engine(url, **kw)
    Base.metadata.create_all(engine)
    if url.startswith("sqlite:///") and ":memory:" not in url:
        path = url[len("sqlite:///"):]
        if os.path.exists(path):
            os.chmod(path, 0o600)          # trading history is private to this user
    return sessionmaker(engine, expire_on_commit=False)
