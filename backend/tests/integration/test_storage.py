"""Storage primitives: size limit, content sniffing allow-list, hashing (NFR-SEC-07, TCMS-137)."""

from __future__ import annotations

import hashlib
import io
import uuid

import pytest
from pydantic import SecretStr

from tcms.core.config import Settings
from tcms.core.errors import FileTooLarge, UnsupportedFileType
from tcms.platform import storage

pytestmark = pytest.mark.integration

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4c50000000049454e44ae426082"
)


@pytest.fixture(scope="module")
def s3(minio: dict[str, str]):  # type: ignore[no-untyped-def]
    client = storage.make_client(
        Settings(
            s3_endpoint_url=minio["endpoint"],
            s3_access_key_id=minio["access_key"],
            s3_secret_access_key=SecretStr(minio["secret_key"]),
        )
    )
    client.create_bucket(Bucket="storage-tests")
    return client


def test_store_png_records_size_hash_and_sniffed_type(s3) -> None:  # type: ignore[no-untyped-def]
    key = storage.object_key_for(uuid.uuid4())
    obj = storage.store(s3, "storage-tests", key, io.BytesIO(PNG), max_bytes=1024)
    assert obj.content_type == "image/png"
    assert obj.size_bytes == len(PNG)
    assert obj.sha256 == hashlib.sha256(PNG).digest()
    assert s3.get_object(Bucket="storage-tests", Key=key)["Body"].read() == PNG


def test_spoofed_type_is_rejected(s3) -> None:  # type: ignore[no-untyped-def]
    """An executable renamed .png is rejected by content sniffing (415)."""
    elf = b"\x7fELF\x02\x01\x01" + b"\x00" * 200
    with pytest.raises(UnsupportedFileType):
        storage.store(
            s3, "storage-tests", storage.object_key_for(uuid.uuid4()), io.BytesIO(elf), max_bytes=1024
        )


def test_svg_is_not_allowed(s3) -> None:  # type: ignore[no-untyped-def]
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(UnsupportedFileType):
        storage.store(
            s3, "storage-tests", storage.object_key_for(uuid.uuid4()), io.BytesIO(svg), max_bytes=1024
        )


def test_oversize_upload_is_rejected_and_not_kept(s3) -> None:  # type: ignore[no-untyped-def]
    key = storage.object_key_for(uuid.uuid4())
    big = b"x" * (3 * 1024 * 1024)  # text/plain
    with pytest.raises(FileTooLarge):
        storage.store(s3, "storage-tests", key, io.BytesIO(big), max_bytes=1024 * 1024)
    listed = s3.list_objects_v2(Bucket="storage-tests", Prefix=key).get("KeyCount", 0)
    assert listed == 0


def test_object_key_layout() -> None:
    org = uuid.uuid4()
    key = storage.object_key_for(org)
    assert key.startswith(f"org/{org}/")
    assert len(key.split("/")) == 5
