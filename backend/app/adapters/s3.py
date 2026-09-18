"""
AgentPay Sentinel — Adapters: AWS S3 Storage

Implements StorageAdapter using Amazon S3.

Security:
  - Bucket must be configured with Block Public Access enabled
  - Server-Side Encryption (AES-256) applied to every object
  - No presigned URLs — backend streams all file operations
  - Bucket name comes from config, never hardcoded
  - IAM role grants only s3:GetObject and s3:PutObject on the evidence prefix

Key format: evidence/{user_id}/{file_id}/{filename}
This prefix makes IAM resource scoping simple and unambiguous.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from .base import StorageAdapter

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# S3 key prefix for all evidence objects — used in IAM policy resource ARN
_EVIDENCE_PREFIX = "evidence"


class S3StorageAdapter(StorageAdapter):
    """
    AWS S3-backed evidence file store.

    Instantiated once per Lambda container (module-level singleton in dependencies.py).
    boto3 client is thread-safe for concurrent requests within the same Lambda instance.
    """

    def __init__(self, settings: "Settings") -> None:
        if not settings.S3_BUCKET_NAME:
            raise ValueError(
                "S3_BUCKET_NAME must be set when USE_LOCAL_ADAPTERS=False. "
                "Set this environment variable to the name of your evidence bucket."
            )
        self._bucket = settings.S3_BUCKET_NAME
        self._client = boto3.client("s3", region_name=settings.AWS_REGION)
        logger.info(
            "S3StorageAdapter initialised",
            extra={"bucket": self._bucket, "region": settings.AWS_REGION},
        )

    def _make_key(self, user_id: str, file_id: str, filename: str) -> str:
        """
        Build a deterministic S3 key.

        Format: evidence/{user_id}/{file_id}/{filename}

        The 'evidence/' prefix is the IAM resource boundary — the Lambda
        execution role only receives permissions on this prefix.
        """
        # Sanitise components — strip path separators to prevent key injection
        safe_user_id = user_id.replace("/", "_").replace("..", "_")
        safe_file_id = file_id.replace("/", "_").replace("..", "_")
        safe_filename = filename.replace("/", "_").replace("..", "_")
        return f"{_EVIDENCE_PREFIX}/{safe_user_id}/{safe_file_id}/{safe_filename}"

    async def store_file(
        self,
        user_id: str,
        file_id: str,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload file bytes to S3 with SSE-AES256.
        Returns the S3 key (used as storage_key everywhere in the application).
        """
        key = self._make_key(user_id, file_id, filename)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                ServerSideEncryption="AES256",
                # Metadata for operational visibility (no sensitive data)
                Metadata={
                    "user-id": user_id,
                    "file-id": file_id,
                },
            )
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "S3 PutObject failed",
                extra={"key": key, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to store evidence file in S3 (key={key}): {error_code}"
            ) from exc

        logger.info("Stored evidence file in S3", extra={"key": key})
        return key

    async def get_file(self, storage_key: str) -> bytes:
        """
        Retrieve file bytes from S3 by storage key.
        Raises FileNotFoundError if the object does not exist.
        """
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=storage_key)
            content: bytes = response["Body"].read()
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code in {"NoSuchKey", "404"}:
                raise FileNotFoundError(
                    f"Evidence file not found in S3: {storage_key}"
                ) from exc
            logger.error(
                "S3 GetObject failed",
                extra={"key": storage_key, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to retrieve evidence file from S3 (key={storage_key}): {error_code}"
            ) from exc

        return content
