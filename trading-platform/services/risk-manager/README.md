# risk-manager

The gate. Every order must pass through `RiskManager.check` before it can reach the execution service.

- `risk_manager/config.py`: the limits (risk per trade, position size, exposure, daily loss, drawdown)
- `risk_manager/killswitch.py`: manual or automatic halt, saved to a file so it survives restarts
- `risk_manager/gate.py`: the checks. Resizes orders down to fit, or rejects. Fails closed on any error
- `risk_manager/sizing.py`: turns a strategy signal into a proposed order
- Output is a plain dict matching `contracts/order.schema.json`. This service imports nothing from `execution`

Run tests: `pip install -r requirements.txt && python -m pytest -q`
