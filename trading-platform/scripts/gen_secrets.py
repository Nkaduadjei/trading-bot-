"""Generates the secrets your .env needs.

  python scripts/gen_secrets.py              prints every secret (nothing is written)
  python scripts/gen_secrets.py --fill .env  adds ONLY the ones that are missing or empty.
                                             It never changes a value that already exists,
                                             so it is safe to run again after an update.

BACK UP KEY_ENCRYPTION_KEY somewhere safe: if you lose it, stored broker keys cannot be read again.
"""
import os
import re
import secrets
import sys

from cryptography.fernet import Fernet

MAKERS = {
    "JWT_SECRET": lambda: secrets.token_urlsafe(48),           # signs login tokens
    "KEY_ENCRYPTION_KEY": lambda: Fernet.generate_key().decode(),  # encrypts stored broker keys
    "APPROVAL_KEY": lambda: secrets.token_urlsafe(48),         # risk manager signs, execution verifies
    "EXECUTION_TOKEN": lambda: secrets.token_urlsafe(48),      # who may call the execution service
    "RISK_TOKEN": lambda: secrets.token_urlsafe(48),           # who may call the risk manager
    "AUTH_ADMIN_TOKEN": lambda: secrets.token_urlsafe(48),     # lets the admin console list users
}


def fill(path):
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    have = {m.group(1) for l in lines if (m := re.match(r"^([A-Z_][A-Z0-9_]*)=(.+)$", l)) and m.group(2).strip()}
    todo = [n for n in MAKERS if n not in have]
    lines = [l for l in lines if not any(re.match(rf"^{n}=\s*$", l) for n in todo)]
    lines += [f"{n}={MAKERS[n]()}" for n in todo]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    print("Added:", ", ".join(todo) if todo else "nothing, every secret already exists")


if len(sys.argv) == 3 and sys.argv[1] == "--fill":
    fill(sys.argv[2])
elif len(sys.argv) == 1:
    for n, make in MAKERS.items():
        print(f"{n}={make()}")
else:
    sys.exit("usage: gen_secrets.py [--fill .env]")
