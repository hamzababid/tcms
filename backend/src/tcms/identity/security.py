"""Password hashing, TOTP and recovery codes (docs/02 §3.3, NFR-SEC-01)."""

from __future__ import annotations

import secrets
import string
from datetime import datetime
from functools import lru_cache

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from tcms.core.crypto import hmac_sha256
from tcms.identity.rules import RECOVERY_CODE_COUNT, RECOVERY_CODE_LENGTH

_hasher = PasswordHasher()  # Argon2id with library defaults (RFC 9106 low-memory profile)
TOTP_INTERVAL = 30


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant work whether or not the user exists (AC-AUTH-02): unknown users verify a dummy hash."""
    try:
        return _hasher.verify(password_hash or _dummy_hash(), password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_totp_secret() -> str:
    return pyotp.random_base32()


def otpauth_uri(secret: str, *, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(name=account, issuer_name=issuer)


def matching_step(secret: str, code: str, now: datetime, last_used_step: int | None) -> int | None:
    """RFC 6238, SHA-1, 30 s, 6 digits, ±1 step; a step already used is rejected (replay)."""
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    current = int(now.timestamp()) // TOTP_INTERVAL
    for step in (current - 1, current, current + 1):
        if secrets.compare_digest(totp.at(step * TOTP_INTERVAL), code):
            if last_used_step is not None and step <= last_used_step:
                return None
            return step
    return None


_RC_ALPHABET = "".join(c for c in string.ascii_lowercase + string.digits if c not in "01ilo")


def new_recovery_codes() -> list[str]:
    return [
        "".join(secrets.choice(_RC_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


def normalize_recovery_code(code: str) -> str:
    return code.strip().lower().replace("-", "").replace(" ", "")


def hash_recovery_code(key: bytes, code: str) -> str:
    """Recovery codes are high-entropy; a keyed HMAC is sufficient and cheap to check against 10 rows."""
    return hmac_sha256(key, normalize_recovery_code(code))
