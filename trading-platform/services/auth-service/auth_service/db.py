from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    totp_secret_enc: Mapped[Optional[str]] = mapped_column(String(300), default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_totp_step: Mapped[int] = mapped_column(Integer, default=-1)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float)


class BrokerKey(Base):
    __tablename__ = "broker_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    broker: Mapped[str] = mapped_column(String(40))
    api_key_enc: Mapped[str] = mapped_column(String(600))
    api_secret_enc: Mapped[str] = mapped_column(String(600))
    api_key_hint: Mapped[str] = mapped_column(String(8))  # last 4 characters, for recognising a key
    created_at: Mapped[float] = mapped_column(Float)


def make_session_factory(url: str):
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool  # one shared in-memory database (tests)
    engine = create_engine(url, **kw)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
