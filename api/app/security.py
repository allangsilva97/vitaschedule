import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt

SESSION_COOKIE = "vs_session"
SESSION_MINUTES = 15  # mesmo prazo de inatividade do front
_ALGO = "HS256"


def secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if not key:
        if os.environ.get("APP_ENV") == "production":
            raise RuntimeError("SECRET_KEY é obrigatório em produção")
        key = "dev-only-insecure-key-change-me-0123456789"
    return key


# --- Senhas: scrypt (stdlib), formato scrypt$N$r$p$salt$hash ---------------
_N, _R, _P = 2**14, 8, 1
DUMMY_HASH = f"scrypt${_N}${_R}${_P}${'00' * 16}${'00' * 32}"


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${_scrypt(password, salt, _N, _R, _P).hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Sempre faz o trabalho do hash (mesmo sem usuário) para não vazar a existência da conta pelo tempo."""
    try:
        _, n, r, p, salt, digest = (stored or DUMMY_HASH).split("$")
        calc = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
        return hmac.compare_digest(calc, bytes.fromhex(digest)) and stored is not None
    except Exception:
        return False


# --- Sessão: JWT em cookie HttpOnly ---------------------------------------
def make_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=SESSION_MINUTES)},
                      secret_key(), algorithm=_ALGO)


def read_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, secret_key(), algorithms=[_ALGO])["sub"])
    except Exception:
        return None


# --- Limitador de tentativas (em memória; vale por instância) -------------
class Throttle:
    def __init__(self, max_fails: int, window_s: int, lock_s: int):
        self.max, self.window, self.lock = max_fails, window_s, lock_s
        self.fails: dict[str, list[float]] = {}
        self.locked: dict[str, float] = {}

    def seconds_left(self, key: str) -> int:
        left = self.locked.get(key, 0) - time.monotonic()
        return int(left) + 1 if left > 0 else 0

    def fail(self, key: str) -> None:
        now = time.monotonic()
        hist = [t for t in self.fails.get(key, []) if now - t < self.window] + [now]
        if len(hist) >= self.max:
            self.locked[key] = now + self.lock
            hist = []
        self.fails[key] = hist
        if len(self.fails) > 10000:  # evita crescimento ilimitado
            self.fails.clear()
            self.locked.clear()

    def reset(self, key: str) -> None:
        self.fails.pop(key, None)
