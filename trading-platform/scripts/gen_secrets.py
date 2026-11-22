"""Prints fresh secrets for your .env.   python scripts/gen_secrets.py >> .env

JWT_SECRET signs login tokens. KEY_ENCRYPTION_KEY encrypts stored broker keys.
BACK UP KEY_ENCRYPTION_KEY somewhere safe: if you lose it, stored broker keys cannot be read again.
Changing JWT_SECRET just logs everyone out.
"""
import secrets

from cryptography.fernet import Fernet

print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
print(f"KEY_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
