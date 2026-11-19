import json
import os


class KillSwitch:
    """When engaged, only orders that reduce risk (sells) are allowed.

    Saved to a file so a restart cannot quietly un-halt the system. If the file exists
    but cannot be read, the switch starts ENGAGED (fail closed).
    """

    def __init__(self, path=None):
        self.path, self.engaged, self.reason = path, False, ""
        if path and os.path.exists(path):
            try:
                with open(path) as f:
                    d = json.load(f)
                self.engaged, self.reason = bool(d["engaged"]), str(d.get("reason", ""))
            except Exception:
                self.engaged, self.reason = True, "kill switch file unreadable"

    def engage(self, reason):
        self.engaged, self.reason = True, reason
        self._save()

    def release(self):
        self.engaged, self.reason = False, ""
        self._save()

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"engaged": self.engaged, "reason": self.reason}, f)
        os.replace(tmp, self.path)  # atomic: never leaves a half-written file
