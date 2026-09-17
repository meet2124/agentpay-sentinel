"""
AgentPay Sentinel — Service: Evidence Extraction

Handles file upload to storage and document parsing via the LLM adapter.
Textract is an optional fallback — not a mandatory dependency.
Evidence is ALWAYS extracted server-side; clients cannot inject pre-parsed data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException, UploadFile, status

from ..adapters.base import LLMAdapter, StorageAdapter
from ..config import get_settings
from ..models.evidence import Evidence, EvidenceItem, EvidenceSourceType, ExtractionMethod


_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/json",   # JSON fixture for testing
}

_CONTENT_TYPE_TO_SOURCE = {
    "application/pdf": EvidenceSourceType.INVOICE_PDF,
    "image/jpeg": EvidenceSourceType.INVOICE_IMAGE,
    "image/png": EvidenceSourceType.INVOICE_IMAGE,
    "image/webp": EvidenceSourceType.INVOICE_IMAGE,
    "application/json": EvidenceSourceType.INVOICE_PDF,   # treats JSON fixture as invoice
}


class EvidenceService:
    def __init__(
        self,
        storage_adapter: StorageAdapter,
        llm_adapter: LLMAdapter,
    ) -> None:
        self._storage = storage_adapter
        self._llm = llm_adapter
        self._settings = get_settings()

        # In-process store: evidence_id → Evidence (replaced by DynamoDB on Day 2)
        self._evidence_store: dict[str, Evidence] = {}

    async def upload_and_extract(
        self,
        file: UploadFile,
        user_id: str,
        intent_id: Optional[str] = None,
    ) -> Evidence:
        """
        Upload file to storage, then immediately extract structured evidence.
        Returns a validated Evidence object.
        """
        content_type = file.content_type or "application/octet-stream"
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type: {content_type}. Allowed: PDF, JPEG, PNG, WEBP.",
            )

        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded file is empty.",
            )

        evidence_id = f"evid_{uuid.uuid4().hex[:12]}"

        # Store file
        storage_key = await self._storage.store_file(
            user_id=user_id,
            file_id=evidence_id,
            content=content,
            filename=file.filename or "upload",
            content_type=content_type,
        )

        # Extract evidence — LLM adapter returns raw dict
        raw = await self._llm.extract_evidence(content, file.filename or "", content_type)

        # Parse and validate
        evidence = self._build_evidence(
            raw=raw,
            evidence_id=evidence_id,
            intent_id=intent_id,
            user_id=user_id,
            storage_key=storage_key,
            original_filename=file.filename,
            content_type=content_type,
        )

        self._evidence_store[evidence_id] = evidence
        return evidence

    async def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        return self._evidence_store.get(evidence_id)

    def _build_evidence(
        self,
        raw: dict,
        evidence_id: str,
        intent_id: Optional[str],
        user_id: str,
        storage_key: str,
        original_filename: Optional[str],
        content_type: str,
    ) -> Evidence:
        """Construct and validate an Evidence object from raw LLM output."""
        source_type = _CONTENT_TYPE_TO_SOURCE.get(content_type, EvidenceSourceType.INVOICE_PDF)

        # Parse line items
        items = []
        for item in raw.get("line_items", []):
            try:
                items.append(
                    EvidenceItem(
                        description=item.get("description", ""),
                        quantity=float(item.get("quantity", 1)),
                        unit_price=float(item.get("unit_price", 0)),
                        total=float(item.get("total", 0)),
                    )
                )
            except Exception:
                pass  # Malformed line items are skipped, not fatal

        # Parse invoice date
        invoice_date = None
        if raw.get("invoice_date"):
            try:
                invoice_date = date.fromisoformat(str(raw["invoice_date"]))
            except ValueError:
                pass

        extraction_method_str = raw.get("extraction_method", "STUB").upper()
        try:
            extraction_method = ExtractionMethod(extraction_method_str)
        except ValueError:
            extraction_method = ExtractionMethod.STUB

        confidence = float(raw.get("extraction_confidence", 0.5))
        if not 0.0 <= confidence <= 1.0:
            confidence = max(0.0, min(1.0, confidence))

        return Evidence(
            evidence_id=evidence_id,
            intent_id=intent_id,
            user_id=user_id,
            source_type=source_type,
            s3_key=storage_key,
            original_filename=original_filename,
            vendor_name=raw.get("vendor_name"),
            vendor_gstin=raw.get("vendor_gstin"),
            amount=float(raw["amount"]) if raw.get("amount") is not None else None,
            currency=raw.get("currency", "INR"),
            invoice_number=raw.get("invoice_number"),
            invoice_date=invoice_date,
            line_items=items,
            extraction_method=extraction_method,
            extraction_confidence=confidence,
        )
