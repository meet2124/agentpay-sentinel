"""
AgentPay Sentinel — Unit Tests: S3StorageAdapter

Uses moto to mock AWS S3 entirely in-process.
No real AWS credentials or real S3 requests are made.

Run: python -m pytest tests/unit/test_s3_adapter.py -v
"""

from __future__ import annotations

import os
import pytest
import boto3
from moto import mock_aws

# Point boto3 at the moto mock — moto intercepts all boto3 calls
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

from app.adapters.s3 import S3StorageAdapter

_BUCKET_NAME = "test-sentinel-evidence"
_REGION = "ap-south-1"


class _MockSettings:
    """Minimal settings stub for adapter construction."""
    S3_BUCKET_NAME = _BUCKET_NAME
    AWS_REGION = _REGION


@pytest.fixture()
def s3_adapter():
    """
    Fixture: start moto S3 mock, create the test bucket, yield adapter, teardown.
    moto intercepts boto3 calls for the duration of the test.
    """
    with mock_aws():
        # Create the bucket that the adapter will write to
        s3 = boto3.client("s3", region_name=_REGION)
        s3.create_bucket(
            Bucket=_BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": _REGION},
        )
        yield S3StorageAdapter(settings=_MockSettings())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_file_returns_key(s3_adapter):
    """store_file() must return a non-empty string key."""
    key = await s3_adapter.store_file(
        user_id="usr_test",
        file_id="evid_abc123",
        content=b"invoice bytes",
        filename="invoice.pdf",
        content_type="application/pdf",
    )
    assert isinstance(key, str)
    assert len(key) > 0


@pytest.mark.asyncio
async def test_store_file_key_format(s3_adapter):
    """Key must follow evidence/{user_id}/{file_id}/{filename} format."""
    key = await s3_adapter.store_file(
        user_id="usr_test",
        file_id="evid_xyz",
        content=b"data",
        filename="doc.pdf",
        content_type="application/pdf",
    )
    assert key.startswith("evidence/usr_test/evid_xyz/")
    assert "doc.pdf" in key


@pytest.mark.asyncio
async def test_store_and_retrieve_roundtrip(s3_adapter):
    """Stored bytes must be retrievable identically."""
    content = b"original invoice content \xf0\x9f\x93\x84"  # include non-ASCII
    key = await s3_adapter.store_file(
        user_id="usr_roundtrip",
        file_id="evid_roundtrip",
        content=content,
        filename="test.pdf",
        content_type="application/pdf",
    )
    retrieved = await s3_adapter.get_file(key)
    assert retrieved == content


@pytest.mark.asyncio
async def test_get_file_not_found_raises(s3_adapter):
    """get_file() must raise FileNotFoundError for a missing key."""
    with pytest.raises(FileNotFoundError, match="Evidence file not found"):
        await s3_adapter.get_file("evidence/nonexistent/key.pdf")


@pytest.mark.asyncio
async def test_store_json_fixture(s3_adapter):
    """JSON content type (used for test fixtures) must be stored correctly."""
    json_bytes = b'{"vendor_name": "ABC Hardware", "amount": 1850}'
    key = await s3_adapter.store_file(
        user_id="usr_json",
        file_id="evid_json",
        content=json_bytes,
        filename="invoice.json",
        content_type="application/json",
    )
    retrieved = await s3_adapter.get_file(key)
    assert retrieved == json_bytes


@pytest.mark.asyncio
async def test_key_injection_protection(s3_adapter):
    """Path separators in user_id / file_id / filename must be sanitised."""
    key = await s3_adapter.store_file(
        user_id="usr/../admin",         # path traversal attempt
        file_id="evid/../../etc",
        content=b"data",
        filename="../../etc/passwd",
        content_type="application/pdf",
    )
    # Must NOT contain ".." in any segment
    assert ".." not in key
    # Must still be a valid key starting with the evidence prefix
    assert key.startswith("evidence/")


@pytest.mark.asyncio
async def test_store_overwrite_idempotent(s3_adapter):
    """Storing the same key twice must succeed without error (last-write wins)."""
    kwargs = dict(
        user_id="usr_idem",
        file_id="evid_idem",
        content=b"v1",
        filename="f.pdf",
        content_type="application/pdf",
    )
    key1 = await s3_adapter.store_file(**kwargs)
    kwargs["content"] = b"v2"
    key2 = await s3_adapter.store_file(**kwargs)

    assert key1 == key2
    # Retrieve should return the latest version
    result = await s3_adapter.get_file(key1)
    assert result == b"v2"
