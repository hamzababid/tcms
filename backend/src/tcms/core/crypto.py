"""Secrets at rest and opaque tokens (NFR-SEC-08, docs/03 §13 A02).

Encryption: AES-256-GCM with a key ring from TCMS_ENCRYPTION_KEYS (`k1:base64key[,k0:oldkey]`, first is
active). Ciphertext layout: `<key id>:` + 12-byte nonce + ciphertext+tag, so old keys keep decrypting
after rotation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ALPHANUM = string.ascii_letters + string.digits


class KeyRingError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyRing:
    keys: dict[str, bytes]
    active: str

    @classmethod
    def parse(cls, spec: str) -> KeyRing:
        keys: dict[str, bytes] = {}
        order: list[str] = []
        for item in (p.strip() for p in spec.split(",") if p.strip()):
            kid, sep, b64 = item.partition(":")
            if not sep or not kid.isalnum():
                raise KeyRingError("TCMS_ENCRYPTION_KEYS entries must look like 'k1:<base64 32-byte key>'")
            key = base64.b64decode(b64)
            if len(key) != 32:
                raise KeyRingError(f"encryption key {kid} must be 32 bytes")
            keys[kid] = key
            order.append(kid)
        if not order:
            raise KeyRingError("TCMS_ENCRYPTION_KEYS is empty")
        return cls(keys, order[0])

    def encrypt(self, plaintext: bytes, *, aad: bytes = b"") -> bytes:
        nonce = secrets.token_bytes(12)
        ct = AESGCM(self.keys[self.active]).encrypt(nonce, plaintext, aad)
        return self.active.encode() + b":" + nonce + ct

    def decrypt(self, blob: bytes, *, aad: bytes = b"") -> bytes:
        kid, sep, rest = blob.partition(b":")
        key = self.keys.get(kid.decode(errors="replace"))
        if not sep or key is None:
            raise KeyRingError("unknown encryption key id")
        return AESGCM(key).decrypt(rest[:12], rest[12:], aad)


def random_token(length: int = 43) -> str:
    """URL-safe random token (≥ 256 bits for the default length)."""
    return "".join(secrets.choice(_ALPHANUM) for _ in range(length))


def sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def hmac_sha256(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
