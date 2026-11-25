# execution

Talks to the broker and nothing else. Paper mode is the default.

- `execution/models.py`: order and position shapes (match `contracts/order.schema.json`)
- `execution/paper.py`: simulated broker for paper trading, no network
- `execution/alpaca.py`: Alpaca REST client (paper endpoint by default)
- `execution/config.py`: picks the broker. Live needs two explicit settings
- `execution/approval.py`: verifies the risk manager's signature (it cannot create signatures)
- `execution/api.py`, `main.py`: HTTP service on port 8002. `POST /orders` accepts ONLY signed, fresh approvals
- `execution/db.py`, `store.py`: SQLite database of orders, fills, equity snapshots and paper prices
- `execution/restore.py`: rebuilds the paper account from the database on startup
- History endpoints (token required): `GET /orders`, `GET /trades`, `GET /equity`, `POST /snapshot`
- Not built yet: migrations (tables are created automatically), tracking an Alpaca order after submit (status is stored as returned), trade-only key check, and a market-data price source for new symbols on Alpaca

Run tests: `pip install -r requirements.txt && python -m pytest -q`
