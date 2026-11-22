import json
import os
import time


class StateStore:
    """Remembers the equity peak and the day's starting equity, so drawdown and daily-loss
    limits survive restarts. If the file exists but can't be read it RAISES: silently starting
    fresh would reset the peak and weaken the drawdown protection."""

    def __init__(self, path=None):
        self.path, self.s = path, {}
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    self.s = json.load(f)
                float(self.s["peak_equity"]), float(self.s["start_of_day_equity"]), str(self.s["day"])
            except Exception:
                raise RuntimeError(f"risk state file {path} is unreadable; fix or remove it on purpose")

    def update(self, equity: float, now: float):
        """Returns (start_of_day_equity, peak_equity) after recording this equity reading."""
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if self.s.get("day") != day:
            self.s["day"], self.s["start_of_day_equity"] = day, equity
        self.s["peak_equity"] = max(self.s.get("peak_equity", equity), equity)
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.s, f)
            os.replace(tmp, self.path)
        return self.s["start_of_day_equity"], self.s["peak_equity"]
