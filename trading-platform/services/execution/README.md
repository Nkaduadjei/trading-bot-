# execution

Talks to the broker and nothing else. Paper mode is the default.

- `execution/models.py`: order and position shapes (match `contracts/order.schema.json`)
- `execution/paper.py`: simulated broker for paper trading, no network
- `execution/alpaca.py`: Alpaca REST client (paper endpoint by default)
- `execution/config.py`: picks the broker. Live needs two explicit settings
- Not built yet: trade-only key check, and refusing orders that did not pass the risk manager

Run tests: `pip install -r requirements.txt && python -m pytest -q`
