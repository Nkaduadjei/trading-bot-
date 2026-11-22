# Order approval (signed by the risk manager, checked by execution)

Execution must accept an order ONLY with a valid approval. This is what makes the risk gate impossible to skip.

```json
{"order": {"client_order_id": "...", "symbol": "SPY", "side": "buy", "qty": 10},
 "approved_at": 1700000000,
 "signature": "<hex>"}
```

- `signature` = HMAC-SHA256 (hex) with `APPROVAL_KEY` of the message below
- message = JSON of `{"order": <order>, "approved_at": <int seconds>}` with keys sorted, no spaces
  (`separators=(",", ":")`), and `qty` always written as a float (10 becomes `10.0`)
- `APPROVAL_KEY` is shared ONLY by risk-manager (signs) and execution (verifies). Never the gateway.
- Execution rejects an approval older than 30 seconds, or dated more than 5 seconds in the future
- Replays are harmless: the same `client_order_id` never creates a second order

`approval-vector.json` is a fixed example. Both services test against it, so they cannot drift apart.
