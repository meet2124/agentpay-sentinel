"""
AgentPay Sentinel — Adapters: AWS Bedrock (Claude via Converse API)

Implements LLMAdapter using Amazon Bedrock's Converse API with
Anthropic Claude (APAC cross-region inference profile for ap-south-1).

Why Converse API (not InvokeModel)?
  - InvokeModel requires manual base64 encoding and model-specific request body
    construction; the "document" content block type (for PDFs) is only valid in
    the Converse API — sending it through InvokeModel raises ValidationException.
  - Converse is the modern, unified Bedrock API; it handles base64 encoding
    internally, supports documents/PDFs natively, and is model-agnostic.
  - One consistent API call covers all three extraction paths (text, image, PDF).

APAC Inference Profile (ap-south-1):
  Claude 3.5 Sonnet v2 is NOT available for direct in-region InvokeModel in
  ap-south-1. It must be accessed via the APAC cross-region inference profile:
    Model ID: apac.anthropic.claude-3-5-sonnet-20241022-v2:0
  This routes requests across ap-northeast-1, us-east-1, us-west-2, etc.
  The IAM resource ARN must use a wildcard region (*) to permit routing.

Security / Trust Model:
  CRITICAL — All LLM output is UNTRUSTED. This adapter:
    1. JSON-parses the raw model response
    2. Type-coerces all values (amounts → float, confidence → float clamped 0–1)
    3. Returns only a typed dict — never raw text, never decision values
  Raw LLM text NEVER reaches the policy engine.
  The calling service validates the returned dict via Pydantic before any
  business decision is made.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from .base import LLMAdapter

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_INTENT_SYSTEM_PROMPT = """\
You are a payment intent parser for an AI payment authorization system.
Your ONLY job is to extract structured payment information from natural language.
You MUST respond with ONLY a valid JSON object — no explanation, no preamble, no markdown.

Required JSON schema:
{
  "payee": "<string: name of the recipient>",
  "amount": <number: payment amount as float>,
  "currency": "<string: ISO 4217 code, default INR>",
  "purpose": "<string or null: stated reason for payment>",
  "payment_method": "<string: UPI | NEFT | IMPS | RTGS | UNKNOWN>",
  "confidence_score": <number: 0.0 to 1.0, your confidence in the extraction>
}

Rules:
- amount MUST be a positive number (no currency symbols)
- currency MUST be a 3-letter ISO code
- payment_method defaults to UPI if not specified
- confidence_score MUST be between 0.0 and 1.0
- If the input is ambiguous, set confidence_score below 0.80
- Do NOT invent a payee if none is mentioned — use "Unknown"
- Do NOT output anything other than the JSON object
"""

_EVIDENCE_SYSTEM_PROMPT = """\
You are a financial document parser for an AI payment authorization system.
Your ONLY job is to extract structured invoice/receipt data from the provided document.
You MUST respond with ONLY a valid JSON object — no explanation, no preamble, no markdown.

Required JSON schema:
{
  "vendor_name": "<string or null: name of the vendor/seller>",
  "vendor_gstin": "<string or null: GST identification number if present>",
  "vendor_address": "<string or null: vendor address if present>",
  "amount": <number or null: total invoice amount as float>,
  "currency": "<string: ISO 4217 code, default INR>",
  "tax_amount": <number or null: total tax amount>,
  "invoice_number": "<string or null: invoice/receipt number>",
  "invoice_date": "<string or null: date in YYYY-MM-DD format>",
  "line_items": [
    {
      "description": "<string>",
      "quantity": <number>,
      "unit_price": <number>,
      "total": <number>,
      "hsn_code": "<string or null>"
    }
  ],
  "extraction_confidence": <number: 0.0 to 1.0, your confidence in the extraction>,
  "notes": "<string or null: any relevant notes or caveats>"
}

Rules:
- amount MUST be a positive number (no currency symbols)
- extraction_confidence MUST be between 0.0 and 1.0
- Set extraction_confidence below 0.70 if the document is unclear or data is missing
- line_items can be an empty list if no line items are visible
- Do NOT output anything other than the JSON object
"""

# Map HTTP content-types → Converse API image format names
_IMAGE_FORMAT_MAP: dict[str, str] = {
    "image/jpeg": "jpeg",
    "image/jpg":  "jpeg",
    "image/png":  "png",
    "image/webp": "webp",
    "image/gif":  "gif",
}

# Regex fallback to extract a JSON object from dirty LLM output
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Bedrock Converse adapter
# ---------------------------------------------------------------------------

class BedrockAdapter(LLMAdapter):
    """
    AWS Bedrock-backed LLM adapter using the Converse API.

    Uses the APAC cross-region inference profile for ap-south-1 deployments:
      Model ID: apac.anthropic.claude-3-5-sonnet-20241022-v2:0

    A single _converse() method handles all extraction paths:
      - Text (intent extraction, JSON fixtures)
      - Image JPEG/PNG/WebP (invoice photos)
      - PDF documents (native Converse "document" block — no base64 needed)

    The boto3 client is constructed once per Lambda container (module-level
    singleton via dependencies.py) and is thread-safe.
    """

    def __init__(self, settings: "Settings") -> None:
        self._model_id: str = settings.BEDROCK_MODEL_ID
        self._region: str = settings.AWS_REGION
        # bedrock-runtime is the endpoint for both InvokeModel and Converse
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self._region,
        )
        logger.info(
            "BedrockAdapter initialised",
            extra={"model_id": self._model_id, "region": self._region},
        )

    # ── Core Converse call ───────────────────────────────────────────────────

    def _converse(self, system_prompt: str, content_blocks: list[dict]) -> str:
        """
        Single Converse API call used by all extraction paths.

        Args:
            system_prompt: Model role / output constraints
            content_blocks: List of Converse content blocks (text, image, document)

        Returns:
            Raw text response from the model.

        Raises:
            RuntimeError: On Bedrock API errors or empty responses.
        """
        try:
            response = self._client.converse(
                modelId=self._model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": content_blocks}],
                inferenceConfig={
                    "maxTokens": 1024,
                    "temperature": 0.0,    # Deterministic output — critical for audit
                },
            )
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "Bedrock Converse failed",
                extra={"error_code": error_code, "model_id": self._model_id},
            )
            raise RuntimeError(
                f"Bedrock Converse failed ({error_code}). "
                "Verify: model access enabled in console, IAM allows bedrock:InvokeModel "
                f"on arn:aws:bedrock:*::foundation-model/{self._model_id.split('.')[-1]}."
            ) from exc

        # Converse response: output.message.content is a list of content blocks
        # Text blocks have a "text" key (not "type": "text" like InvokeModel)
        content = response.get("output", {}).get("message", {}).get("content", [])
        text_blocks = [b["text"] for b in content if "text" in b]
        if not text_blocks:
            raise RuntimeError("Bedrock Converse returned empty response content")

        return "".join(text_blocks)

    # ── JSON extraction helpers ──────────────────────────────────────────────

    def _extract_json(self, raw_text: str) -> dict[str, Any]:
        """
        Extract a JSON object from the model's raw text output.
        Tolerates markdown code fences (``` or ```json) that models sometimes add.

        Raises:
            ValueError: If no valid JSON object is found.
        """
        stripped = raw_text.strip()

        # Direct parse (model followed instructions perfectly)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        no_fences = re.sub(r"```(?:json)?", "", stripped).strip()
        try:
            return json.loads(no_fences)
        except json.JSONDecodeError:
            pass

        # Last resort: find the first JSON object via regex
        match = _JSON_BLOCK_RE.search(raw_text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"BedrockAdapter: could not extract valid JSON from model response. "
            f"Raw response (first 200 chars): {raw_text[:200]!r}"
        )

    def _clamp_confidence(self, value: Any, field_name: str) -> float:
        """Coerce and clamp a confidence value to [0.0, 1.0]."""
        try:
            f = float(value)
        except (TypeError, ValueError):
            logger.warning(
                "BedrockAdapter: invalid %s value, defaulting to 0.5",
                field_name,
                extra={"value": str(value)},
            )
            return 0.5
        return max(0.0, min(1.0, f))

    # ── LLMAdapter interface ─────────────────────────────────────────────────

    async def extract_intent(self, raw_input: str) -> dict[str, Any]:
        """
        Parse a natural language payment instruction → PaymentIntent-shaped dict.

        Uses the text path: single text content block.

        LLM output determines: payee name (string), amount (number), currency.
        LLM output NEVER determines: ALLOW / DENY / REQUIRE_HUMAN_APPROVAL.
        All returned values are type-coerced. The caller validates via Pydantic.
        """
        logger.info(
            "BedrockAdapter.extract_intent called",
            extra={"input_length": len(raw_input), "model_id": self._model_id},
        )

        raw_text = self._converse(
            system_prompt=_INTENT_SYSTEM_PROMPT,
            content_blocks=[
                {"text": f"Extract the payment intent from this instruction:\n\n{raw_input}"},
            ],
        )

        data = self._extract_json(raw_text)

        # Type-coerce all fields — never trust raw LLM types
        return {
            "payee": str(data.get("payee") or "Unknown").strip() or "Unknown",
            "amount": float(data.get("amount") or 0),
            "currency": str(data.get("currency") or "INR").upper()[:3],
            "purpose": str(data["purpose"]) if data.get("purpose") else None,
            "payment_method": str(data.get("payment_method") or "UPI"),
            "confidence_score": self._clamp_confidence(
                data.get("confidence_score", 0.85), "confidence_score"
            ),
            "extraction_model": self._model_id,
        }

    async def extract_evidence(
        self, file_content: bytes, filename: str, content_type: str
    ) -> dict[str, Any]:
        """
        Parse an invoice/receipt document → Evidence-shaped dict.

        Content routing:
          - application/pdf  → Converse "document" block (bytes, format="pdf")
                               Native PDF support; Bedrock handles page rendering.
          - image/*          → Converse "image" block (bytes, format=jpeg/png/webp/gif)
          - application/json → Text block (JSON fixtures for local testing)
          - other            → Text block with hex fallback

        Converse API handles base64 encoding internally — no manual encoding needed.
        Output is UNTRUSTED; caller validates via Pydantic Evidence model.
        """
        logger.info(
            "BedrockAdapter.extract_evidence called",
            extra={
                "filename": filename,
                "content_type": content_type,
                "content_length": len(file_content),
                "model_id": self._model_id,
            },
        )

        extract_prompt = (
            "Extract all invoice/receipt information from this document. "
            "Return ONLY the JSON object with no explanation."
        )

        if content_type == "application/pdf":
            # Native PDF: Converse "document" block — boto3 handles base64 internally
            content_blocks: list[dict] = [
                {
                    "document": {
                        "name": "invoice",
                        "format": "pdf",
                        "source": {"bytes": file_content},
                    }
                },
                {"text": extract_prompt},
            ]

        elif content_type in _IMAGE_FORMAT_MAP:
            # Image: Converse "image" block — boto3 handles base64 internally
            content_blocks = [
                {
                    "image": {
                        "format": _IMAGE_FORMAT_MAP[content_type],
                        "source": {"bytes": file_content},
                    }
                },
                {"text": extract_prompt},
            ]

        elif content_type == "application/json":
            # JSON fixture (test/demo): send as plain text
            try:
                text_content = file_content.decode("utf-8")
            except UnicodeDecodeError:
                text_content = file_content.decode("latin-1")
            content_blocks = [
                {
                    "text": (
                        f"Extract invoice data from this JSON document:\n\n"
                        f"{text_content}\n\n{extract_prompt}"
                    )
                },
            ]

        else:
            # Unknown content type — attempt text decode, fall back gracefully
            logger.warning(
                "BedrockAdapter.extract_evidence: unknown content_type %r, using text path",
                content_type,
            )
            try:
                text_content = file_content.decode("utf-8", errors="replace")
            except Exception:
                text_content = "<binary content — could not decode>"
            content_blocks = [
                {
                    "text": (
                        f"Extract invoice data from this document "
                        f"(content-type: {content_type}):\n\n"
                        f"{text_content}\n\n{extract_prompt}"
                    )
                },
            ]

        raw_text = self._converse(
            system_prompt=_EVIDENCE_SYSTEM_PROMPT,
            content_blocks=content_blocks,
        )

        data = self._extract_json(raw_text)

        # Type-coerce all fields — line_items validated item by item
        raw_line_items = data.get("line_items") or []
        validated_line_items = []
        for item in raw_line_items:
            if not isinstance(item, dict):
                continue
            try:
                validated_line_items.append({
                    "description": str(item.get("description") or ""),
                    "quantity":    float(item.get("quantity") or 1),
                    "unit_price":  float(item.get("unit_price") or 0),
                    "total":       float(item.get("total") or 0),
                    "hsn_code":    str(item["hsn_code"]) if item.get("hsn_code") else None,
                })
            except (TypeError, ValueError):
                logger.warning(
                    "BedrockAdapter: skipping malformed line item",
                    extra={"item": str(item)[:100]},
                )

        amount_raw = data.get("amount")
        return {
            "vendor_name":    str(data["vendor_name"]).strip() if data.get("vendor_name") else None,
            "vendor_gstin":   str(data["vendor_gstin"]) if data.get("vendor_gstin") else None,
            "vendor_address": str(data["vendor_address"]) if data.get("vendor_address") else None,
            "amount":         float(amount_raw) if amount_raw is not None else None,
            "currency":       str(data.get("currency") or "INR").upper()[:3],
            "tax_amount":     float(data["tax_amount"]) if data.get("tax_amount") is not None else None,
            "invoice_number": str(data["invoice_number"]) if data.get("invoice_number") else None,
            "invoice_date":   str(data["invoice_date"]) if data.get("invoice_date") else None,
            "line_items":     validated_line_items,
            "extraction_confidence": self._clamp_confidence(
                data.get("extraction_confidence", 0.75), "extraction_confidence"
            ),
            "notes":          str(data["notes"]) if data.get("notes") else None,
            "extraction_method": "BEDROCK_VISION",
        }
