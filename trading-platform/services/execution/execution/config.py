import os

from .alpaca import AlpacaBroker
from .paper import PaperBroker


def make_broker(env=None):
    """Pick a broker from settings. Paper is the default; live needs TWO explicit settings."""
    env = os.environ if env is None else env
    mode = env.get("TRADING_MODE", "paper").lower()
    if mode == "paper":
        if env.get("BROKER_API_KEY") and env.get("BROKER_API_SECRET"):
            return AlpacaBroker(env["BROKER_API_KEY"], env["BROKER_API_SECRET"], live=False)
        return PaperBroker()
    if mode == "live":
        if env.get("LIVE_TRADING_CONFIRM") != "yes-i-understand":
            raise RuntimeError("live trading needs LIVE_TRADING_CONFIRM=yes-i-understand")
        return AlpacaBroker(env.get("BROKER_API_KEY"), env.get("BROKER_API_SECRET"), live=True)
    raise ValueError(f"unknown TRADING_MODE {mode!r}")
