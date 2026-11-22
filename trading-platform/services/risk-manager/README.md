# risk-manager

The gate. Every order must pass through `RiskManager.check` before it can reach the execution service.

- `risk_manager/config.py`: the limits (risk per trade, position size, exposure, daily loss, drawdown)
- `risk_manager/killswitch.py`: manual or automatic halt, saved to a file so it survives restarts
- `risk_manager/gate.py`: the checks. Resizes orders down to fit, or rejects. Fails closed on any error
- `risk_manager/sizing.py`: turns a strategy signal into a proposed order
- `risk_manager/api.py`, `main.py`: HTTP service on port 8003. `POST /evaluate` reads the account from execution and returns a SIGNED approval or a rejection. Kill switch over HTTP
- `risk_manager/approval.py`: signs approved orders. `state.py`: remembers equity peak and day start
- Output is a plain dict matching `contracts/order.schema.json`. This service imports nothing from `execution`

Run tests: `pip install -r requirements.txt && python -m pytest -q`
