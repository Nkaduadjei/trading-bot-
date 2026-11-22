"""Checks the risk manager's signature. This service can verify approvals but deliberately
cannot create them: there is no signing code here."""
import hashlib
import hmac
import json

from .models import OrderRequest

FIELDS = {"client_order_id", "symbol", "side", "qty"}


class ApprovalError(Exception):
    pass


def _signature(key: str, order: dict, approved_at: int) -> str:
    o = {"client_order_id": str(order["client_order_id"]), "symbol": str(order["symbol"]),
         "side": str(order["side"]), "qty": float(order["qty"])}
    msg = json.dumps({"order": o, "approved_at": int(approved_at)}, sort_keys=True,
                     separators=(",", ":"))
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def verify(key: str, approval: dict, now: float, max_age: int = 30, skew: int = 5) -> OrderRequest:
    try:
        order, at, sig = approval["order"], approval["approved_at"], approval["signature"]
        if set(order) != FIELDS:
            raise ApprovalError("unexpected order fields")
        if not isinstance(at, int) or isinstance(at, bool):
            raise ApprovalError("approved_at must be whole seconds")
        if not hmac.compare_digest(_signature(key, order, at), str(sig)):
            raise ApprovalError("bad signature")
        age = now - at
        if age > max_age:
            raise ApprovalError("approval expired")
        if age < -skew:
            raise ApprovalError("approval is dated in the future")
        return OrderRequest(order["client_order_id"], order["symbol"], order["side"],
                            float(order["qty"]))
    except ApprovalError:
        raise
    except Exception as e:
        raise ApprovalError("malformed approval") from e
