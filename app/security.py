"""Password hashing (PBKDF2) and HS256 JWTs using only the standard library.

Swap these for passlib + python-jose in production if you prefer; the
interface (`hash_password`, `verify_password`, `create_token`, `decode_token`)
stays the same.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Optional

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(sub: str, secret: str, expires_in: int = 3600) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"sub": sub, "exp": int(time.time()) + expires_in}).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(sig)}"


def decode_token(token: str, secret: str) -> Optional[dict[str, Any]]:
    try:
        header, payload, sig = token.split(".")
        expected = hmac.new(secret.encode(), f"{header}.{payload}".encode(),
                            hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            return None
        data = json.loads(_b64d(payload))
        if data.get("exp", 0) < int(time.time()):
            return None
        return data
    except (ValueError, json.JSONDecodeError):
        return None
