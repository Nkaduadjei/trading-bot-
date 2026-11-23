import json
import os
import time


def record(path: str, now: float, admin: str, action: str, detail: str = ""):
    """Append one line per admin action. The file is private to this user (mode 600)."""
    line = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)) + " UTC",
                       "admin": admin, "action": action, "detail": detail[:200]})
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(line + "\n")


def tail(path: str, n: int = 50) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = f.read().splitlines()[-n:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out
