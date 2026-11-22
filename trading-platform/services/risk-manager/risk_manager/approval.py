"""Signs approved orders. Only this service can do it: execution holds the same key but
has verification code only, and the gateway never holds the key."""
import hashlib
import hmac
import json


def sign(key: str, order: dict, approved_at: int) -> str:
    o = {"client_order_id": str(order["client_order_id"]), "symbol": str(order["symbol"]),
         "side": str(order["side"]), "qty": float(order["qty"])}
    msg = json.dumps({"order": o, "approved_at": int(approved_at)}, sort_keys=True,
                     separators=(",", ":"))
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_approval(key: str, order: dict, now: float) -> dict:
    at = int(now)
    return {"order": order, "approved_at": at, "signature": sign(key, order, at)}
