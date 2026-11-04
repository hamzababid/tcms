"""S3-compatible object storage for attachments and transfers (docs/03 §11, NFR-SEC-07).

M0 provides storage primitives (streamed upload with size limit, hashing, MIME sniffing against the
allow-list). Attachment records and their routes are added with the first owning entity (M2).
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import IO, TYPE_CHECKING, Any
from uuid import UUID

import boto3
import magic
from botocore.config import Config

from tcms.core import clock, ids
from tcms.core.config import Settings
from tcms.core.errors import FileTooLarge, UnsupportedFileType

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

# docs/02 §9.2 allow-list, checked against the sniffed type (never the client-supplied one).
ALLOWED_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/csv",
        "application/json",
        "text/xml",
        "application/xml",
        "application/zip",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "video/mp4",
        "video/webm",
    }
)
SNIFF_BYTES = 8192
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    size_bytes: int
    sha256: bytes
    content_type: str


def make_client(settings: Settings) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value()
        if settings.s3_secret_access_key
        else None,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4", connect_timeout=5, read_timeout=30, retries={"max_attempts": 2}
        ),
    )


def object_key_for(organization_id: UUID, at: datetime | None = None) -> str:
    when = at or clock.now()
    return f"org/{organization_id}/{when:%Y}/{when:%m}/{ids.new_id()}"


def sniff(head: bytes) -> str:
    return str(magic.from_buffer(head, mime=True))


class _LimitedHashingReader(io.RawIOBase):
    """Wraps a stream: counts and hashes bytes, aborts past `limit`."""

    def __init__(self, first: bytes, rest: IO[bytes], limit: int) -> None:
        self._chunks: Iterator[bytes] = self._iter(first, rest)
        self._buffer = b""
        self.limit = limit
        self.size = 0
        self.digest = hashlib.sha256()

    def _iter(self, first: bytes, rest: IO[bytes]) -> Iterator[bytes]:
        if first:
            yield first
        while chunk := rest.read(CHUNK):
            yield chunk

    def readable(self) -> bool:
        return True

    def readinto(self, b: Any) -> int:
        while not self._buffer:
            chunk = next(self._chunks, None)
            if chunk is None:
                return 0
            self.size += len(chunk)
            if self.size > self.limit:
                raise FileTooLarge(f"File exceeds {self.limit // (1024 * 1024)} MB")
            self.digest.update(chunk)
            self._buffer = chunk
        n = min(len(b), len(self._buffer))
        b[:n] = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return n


def store(client: S3Client, bucket: str, key: str, stream: IO[bytes], *, max_bytes: int) -> StoredObject:
    """Stream to object storage while enforcing the size limit and the type allow-list."""
    head = stream.read(SNIFF_BYTES)
    content_type = sniff(head)
    if content_type not in ALLOWED_TYPES:
        raise UnsupportedFileType(f"Files of type {content_type} are not allowed")
    reader = _LimitedHashingReader(head, stream, max_bytes)
    try:
        client.upload_fileobj(io.BufferedReader(reader), bucket, key, ExtraArgs={"ContentType": content_type})
    except Exception as exc:
        # boto3 may wrap the limit error raised inside its transfer threads.
        if reader.size > max_bytes:
            client.delete_object(Bucket=bucket, Key=key)
            raise FileTooLarge(f"File exceeds {max_bytes // (1024 * 1024)} MB") from exc
        raise
    return StoredObject(key, reader.size, reader.digest.digest(), content_type)


def check_bucket(client: S3Client, bucket: str) -> None:
    client.head_bucket(Bucket=bucket)
