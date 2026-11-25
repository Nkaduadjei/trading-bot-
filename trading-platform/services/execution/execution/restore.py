from .paper import PaperBroker
from .store import Store


def build_paper_broker(store: Store, start_cash: float = 100_000.0, commission_bps: float = 5.0,
                       slippage_bps: float = 5.0) -> PaperBroker:
    """A paper broker rebuilt from the database: saved prices, then every saved fill replayed in order.

    The starting cash is fixed the first time and remembered, so changing the setting later cannot
    quietly rewrite history.
    """
    saved = store.get_meta("paper_start_cash")
    if saved is None:
        store.set_meta("paper_start_cash", repr(float(start_cash)))
        cash = float(start_cash)
    else:
        cash = float(saved)
    broker = PaperBroker(cash=cash, commission_bps=commission_bps, slippage_bps=slippage_bps)
    for symbol, price in store.prices().items():
        broker.set_price(symbol, price)
    for symbol, side, qty, price in store.replay_fills():
        broker.apply_fill(symbol, side, qty, price)
    return broker
