import logging
import re
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import totp
from .config import Settings
from .db import BrokerKey, User, make_session_factory
from .security import (DUMMY_HASH, Vault, hash_password, make_token, read_token,
                       verify_password)

log = logging.getLogger("auth")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BAD_LOGIN = "invalid email or password"


class RegisterIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None


class CodeIn(BaseModel):
    code: str


class BrokerKeyIn(BaseModel):
    broker: str
    api_key: str
    api_secret: str
    trade_only_confirmed: bool = False


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="auth-service")
    Session_ = make_session_factory(settings.database_url)
    vault = Vault(settings.encryption_key)
    app.state.settings, app.state.session_factory, app.state.vault = settings, Session_, vault
    bearer = HTTPBearer(auto_error=False)

    def get_db():
        db = Session_()
        try:
            yield db
        finally:
            db.close()

    def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
        uid = read_token(creds.credentials, settings.jwt_secret, settings.clock()) if creds else None
        user = db.get(User, uid) if uid is not None else None
        if user is None:
            raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
        return user

    def clean_email(raw: str) -> str:
        e = raw.strip().lower()
        if len(e) > 254 or not EMAIL.match(e):
            raise HTTPException(422, "invalid email address")
        return e

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/register", status_code=201)
    def register(body: RegisterIn, db: Session = Depends(get_db)):
        email = clean_email(body.email)
        if len(body.password) < settings.min_password_length:
            raise HTTPException(422, f"password must be at least {settings.min_password_length} characters")
        if len(body.password) > 200:
            raise HTTPException(422, "password too long")
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, "an account with this email already exists")
        user = User(email=email, password_hash=hash_password(body.password), created_at=settings.clock())
        db.add(user)
        db.commit()
        log.info("registered user id=%s", user.id)
        return {"id": user.id, "email": user.email}

    @app.post("/auth/login")
    def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
        now = settings.clock()
        user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
        if user and user.locked_until > now:  # locked: even the right password is refused
            raise HTTPException(429, "too many failed attempts, try again later",
                                headers={"Retry-After": str(int(user.locked_until - now) + 1)})

        def fail():
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= settings.max_failed_logins:
                    user.locked_until = now + settings.lockout_minutes * 60
                    user.failed_attempts = 0
                    log.warning("user id=%s locked after repeated failures", user.id)
                db.commit()
            else:
                log.info("login attempt for unknown email")
            raise HTTPException(401, BAD_LOGIN)

        good = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
        if user is None or not good:
            fail()
        if user.totp_enabled:
            if not body.totp_code:
                raise HTTPException(401, "totp_required")
            step = totp.verify(vault.decrypt(user.totp_secret_enc), body.totp_code, now)
            if step is None or step <= user.last_totp_step:  # wrong, or a code already used
                fail()
            user.last_totp_step = step
        user.failed_attempts = 0
        db.commit()
        log.info("login ok user id=%s", user.id)
        return {"access_token": make_token(user.id, settings.jwt_secret,
                                           settings.access_token_minutes, now),
                "token_type": "bearer"}

    @app.get("/me")
    def me(user: User = Depends(current_user)):
        return {"id": user.id, "email": user.email, "totp_enabled": user.totp_enabled}

    @app.post("/auth/2fa/setup")
    def setup_2fa(user: User = Depends(current_user), db: Session = Depends(get_db)):
        if user.totp_enabled:
            raise HTTPException(409, "2FA is already enabled")
        secret = totp.new_secret()
        user.totp_secret_enc = vault.encrypt(secret)  # pending until confirmed with a real code
        db.commit()
        return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user.email)}

    @app.post("/auth/2fa/enable")
    def enable_2fa(body: CodeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        if user.totp_enabled:
            raise HTTPException(409, "2FA is already enabled")
        if not user.totp_secret_enc:
            raise HTTPException(409, "call /auth/2fa/setup first")
        if totp.verify(vault.decrypt(user.totp_secret_enc), body.code, settings.clock()) is None:
            raise HTTPException(401, "wrong code")
        user.totp_enabled = True
        db.commit()
        log.info("2FA enabled user id=%s", user.id)
        return {"totp_enabled": True}

    @app.post("/broker-keys", status_code=201)
    def add_key(body: BrokerKeyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
        if not body.trade_only_confirmed:
            raise HTTPException(422, "confirm the key is trade-only (no withdrawal permission)")
        if not (1 <= len(body.broker) <= 40 and 1 <= len(body.api_key) <= 200
                and 1 <= len(body.api_secret) <= 200):
            raise HTTPException(422, "broker, api_key or api_secret has an invalid length")
        row = BrokerKey(user_id=user.id, broker=body.broker.strip().lower(),
                        api_key_enc=vault.encrypt(body.api_key),
                        api_secret_enc=vault.encrypt(body.api_secret),
                        api_key_hint=body.api_key[-4:] if len(body.api_key) >= 8 else "****",
                        created_at=settings.clock())
        db.add(row)
        db.commit()
        log.info("broker key stored id=%s user id=%s", row.id, user.id)
        return {"id": row.id, "broker": row.broker, "api_key_hint": row.api_key_hint}

    @app.get("/broker-keys")
    def list_keys(user: User = Depends(current_user), db: Session = Depends(get_db)):
        rows = db.scalars(select(BrokerKey).where(BrokerKey.user_id == user.id)).all()
        return [{"id": r.id, "broker": r.broker, "api_key_hint": r.api_key_hint} for r in rows]

    @app.delete("/broker-keys/{key_id}", status_code=204)
    def delete_key(key_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = db.get(BrokerKey, key_id)
        if row is None or row.user_id != user.id:  # someone else's key looks the same as no key
            raise HTTPException(404, "not found")
        db.delete(row)
        db.commit()
        return Response(status_code=204)

    return app
