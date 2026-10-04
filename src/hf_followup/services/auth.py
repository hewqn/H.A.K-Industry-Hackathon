"""Account login, signed bearer tokens, and role checks (admin can mutate, viewer reads)."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from hf_followup.domain.errors import DomainError

ROLES = ("admin", "viewer")
TOKEN_TTL_SECONDS = 8 * 3600
AUTH_ATTEMPT_LIMIT = 8
AUTH_ATTEMPT_WINDOW = 60

# Set by the admin dependency so command events record who performed them.
current_actor: ContextVar[str | None] = ContextVar("current_actor", default=None)

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, expected = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(derived.hex(), expected)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def public_user(user: dict) -> dict:
    return {k: user[k] for k in ("user_id", "username", "role", "created_at")}


def _unauthorized(message: str = "Log in to continue.") -> DomainError:
    return DomainError("not_authenticated", message, 401)


class AttemptGate:
    """Bound failed login/register retries per client so password guessing is slow."""

    def __init__(self, limit: int = AUTH_ATTEMPT_LIMIT, window: int = AUTH_ATTEMPT_WINDOW):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = time.time()
        recent = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window]
        self._hits[key] = recent
        return recent

    def check(self, key: str) -> None:
        if len(self._recent(key)) >= self.limit:
            raise DomainError("too_many_attempts", "Too many tries. Wait a minute and try again.", 429)

    def fail(self, key: str) -> None:
        self.check(key)
        self._hits.setdefault(key, []).append(time.time())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


class AuthService:
    def __init__(self, store, secret: str | None = None, ttl: int = TOKEN_TTL_SECONDS):
        self.store = store
        # Without a configured secret, tokens are only valid until the API restarts.
        self._secret = (secret or secrets.token_hex(32)).encode()
        self.ttl = ttl
        self.attempts = AttemptGate()

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())

    def issue_token(self, user: dict) -> dict:
        claims = {"sub": user["user_id"], "exp": int(time.time()) + self.ttl}
        body = _b64(json.dumps(claims, separators=(",", ":")).encode())
        return {
            "access_token": f"{body}.{self._sign(body)}",
            "token_type": "bearer",
            "expires_in": self.ttl,
            "user": public_user(user),
        }

    def authenticate(self, token: str) -> dict:
        body, _, signature = token.partition(".")
        if not body or not hmac.compare_digest(signature, self._sign(body)):
            raise _unauthorized("Invalid session token.")
        try:
            claims = json.loads(_unb64(body))
        except ValueError as exc:
            raise _unauthorized("Invalid session token.") from exc
        if claims.get("exp", 0) < time.time():
            raise DomainError("token_expired", "Session expired; log in again.", 401)
        user = self.store.get_by_id(claims.get("sub", ""))
        if user is None:
            raise _unauthorized("Account no longer exists.")
        return user

    def register(self, username: str, password: str) -> dict:
        username = username.strip().lower()
        if self.store.get_by_username(username):
            raise DomainError("username_taken", "That username is already registered.", 409)
        # The first account bootstraps the workspace as its administrator.
        role = "admin" if self.store.count() == 0 else "viewer"
        return self.store.create({
            "user_id": str(uuid.uuid4()),
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "created_at": datetime.now(UTC).isoformat(),
        })

    def login(self, username: str, password: str) -> dict:
        user = self.store.get_by_username(username.strip().lower())
        if user is None or not verify_password(password, user["password_hash"]):
            raise DomainError("invalid_credentials", "Incorrect username or password.", 401)
        return self.issue_token(user)

    def ensure_admin(self, username: str, password: str) -> None:
        """Seed an admin account from configuration when it does not exist yet."""
        username = username.strip().lower()
        existing = self.store.get_by_username(username)
        if existing is None:
            self.store.create({
                "user_id": str(uuid.uuid4()),
                "username": username,
                "password_hash": hash_password(password),
                "role": "admin",
                "created_at": datetime.now(UTC).isoformat(),
            })
            return
        if existing["role"] != "admin":
            self.store.set_role(existing["user_id"], "admin")
        self.store.set_password(existing["user_id"], hash_password(password))

    def list_users(self) -> list[dict]:
        return [public_user(u) for u in self.store.list_all()]

    def set_role(self, user_id: str, role: str) -> dict:
        if role not in ROLES:
            raise DomainError("invalid_role", f"Role must be one of {list(ROLES)}.", 422)
        user = self.store.get_by_id(user_id)
        if user is None:
            raise DomainError("user_not_found", "User does not exist.", 404)
        if user["role"] == "admin" and role != "admin":
            admins = sum(1 for u in self.store.list_all() if u["role"] == "admin")
            if admins <= 1:
                raise DomainError("last_admin", "Cannot demote the only admin.", 409)
        self.store.set_role(user_id, role)
        return public_user({**user, "role": role})
