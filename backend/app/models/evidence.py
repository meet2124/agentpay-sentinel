"""
AgentPay Sentinel — Data Models
Evidence, EvidenceItem models.

Evidence is ALWAYS extracted server-side.
The client can only upload a raw file — it cannot inject pre-parsed evidence data.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class EvidenceSourceType(str, Enum):
    INVOICE_PDF = "INVOICE_PDF"
    INVOICE_IMAGE = "INVOICE_IMAGE"
    RECEIPT_PDF = "RECEIPT_PDF"
    RECEIPT_IMAGE = "RECEIPT_IMAGE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    NONE = "NONE"


class ExtractionMethod(str, Enum):
    BEDROCK_VISION = "BEDROCK_VISION"
    TEXTRACT = "TEXTRACT"       # Optional fallback — not a mandatory dependency
    STUB = "STUB"               # Local development only
    MANUAL = "MANUAL"


class EvidenceItem(BaseModel):
    """A single line item from an invoice."""

    description: str = Field(..., examples=["Electrical fittings - Type A"])
    quantity: float = Field(..., gt=0, examples=[5.0])
    unit_price: float = Field(..., ge=0, examples=[370.00])
    total: float = Field(..., ge=0, examples=[1850.00])
    hsn_code: Optional[str] = Field(None, description="HSN/SAC code for GST")


class Evidence(BaseModel):
    """
    Structured evidence extracted from a supporting document.
    Produced exclusively by the evidence service — never accepted from the client.
    """

    evidence_id: str = Field(..., examples=["evid_def456"])
    intent_id: Optional[str] = Field(None, description="Linked PaymentIntent ID (set after extraction)")
    user_id: str

    # Source
    source_type: EvidenceSourceType = Field(...)
    s3_key: Optional[str] = Field(None)
    original_filename: Optional[str] = Field(None)

    # Extracted vendor fields
    vendor_name: Optional[str] = Field(None, examples=["ABC Hardware Co."])
    vendor_gstin: Optional[str] = Field(None)
    vendor_address: Optional[str] = Field(None)

    # Extracted financial fields
    amount: Optional[float] = Field(None, ge=0, examples=[1850.00])
    currency: Optional[str] = Field(None, examples=["INR"])
    tax_amount: Optional[float] = Field(None, ge=0)

    # Document metadata
    invoice_number: Optional[str] = Field(None, examples=["INV-042"])
    invoice_date: Optional[date] = Field(None)
    due_date: Optional[date] = Field(None)

    line_items: List[EvidenceItem] = Field(default_factory=list)
    notes: Optional[str] = Field(None)

    # Extraction quality
    extraction_method: ExtractionMethod = Field(default=ExtractionMethod.STUB)
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (0–1). Values < 0.70 trigger deny_low_confidence_extraction.",
        examples=[0.94],
    )
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
