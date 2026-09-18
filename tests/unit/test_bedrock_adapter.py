"""
AgentPay Sentinel — Unit Tests: BedrockAdapter (Converse API)

Uses unittest.mock.patch to mock the boto3 bedrock-runtime client.
No real AWS credentials or Bedrock calls are made.

Test coverage:
  - Converse API request format (system, messages, inferenceConfig)
  - APAC inference profile model ID (apac. prefix required in ap-south-1)
  - Region sourced correctly from settings (not hardcoded)
  - Intent extraction: happy path, type coercion, confidence clamping,
    blank payee fallback, markdown fence stripping, non-JSON raises ValueError
  - Evidence extraction: JSON fixture (text path), image path, PDF document
    block path (Converse "document" block — NOT base64-encoded manually)
  - Security invariant: LLM-injected decision fields are never propagated

Run: python -m pytest tests/unit/test_bedrock_adapter.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.adapters.bedrock import BedrockAdapter, _IMAGE_FORMAT_MAP


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class _MockSettings:
    """Settings stub — uses the correct APAC inference profile ID."""
    BEDROCK_MODEL_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
    AWS_REGION = "ap-south-1"


class _MockSettingsDifferentRegion:
    """Settings stub for region-propagation test."""
    BEDROCK_MODEL_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
    AWS_REGION = "us-east-1"


def _make_converse_response(text: str) -> dict:
    """
    Build a mock boto3 converse() return value matching the Bedrock Converse
    API response structure.

    Converse response shape:
      {
        "output": {
          "message": {
            "role": "assistant",
            "content": [{"text": "..."}]
          }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": N, "outputTokens": M, "totalTokens": N+M}
      }
    """
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150},
    }


def _make_adapter(settings=None) -> tuple[BedrockAdapter, MagicMock]:
    """Create a BedrockAdapter with a mocked boto3 bedrock-runtime client."""
    if settings is None:
        settings = _MockSettings()
    with patch("boto3.client") as mock_boto3_client:
        mock_client = MagicMock()
        mock_boto3_client.return_value = mock_client
        adapter = BedrockAdapter(settings=settings)
    # Replace the client with a fresh mock so we can configure return values per test
    adapter._client = MagicMock()
    return adapter, adapter._client


def _set_response(mock_client: MagicMock, text: str) -> None:
    """Configure the mock client's converse() to return a given text response."""
    mock_client.converse.return_value = _make_converse_response(text)


# ---------------------------------------------------------------------------
# APAC Model ID & Region Configuration Tests
# ---------------------------------------------------------------------------

def test_apac_model_id_is_used():
    """
    The adapter must use the APAC inference profile model ID (apac. prefix).
    Calling with the bare model ID (without apac.) would raise ValidationException
    in ap-south-1 — the test verifies the correct ID propagates to the client call.
    """
    adapter, mock_client = _make_adapter(_MockSettings())
    _set_response(mock_client, json.dumps({
        "payee": "Test", "amount": 100.0, "currency": "INR",
        "purpose": None, "payment_method": "UPI", "confidence_score": 0.9
    }))

    import asyncio
    asyncio.get_event_loop().run_until_complete(
        adapter.extract_intent("Pay 100 to Test")
    )

    call_kwargs = mock_client.converse.call_args[1]
    assert call_kwargs["modelId"] == "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert call_kwargs["modelId"].startswith("apac."), (
        "Model ID must use APAC inference profile prefix for ap-south-1"
    )


def test_region_sourced_from_settings():
    """
    The boto3 bedrock-runtime client must be constructed with the region from
    settings, NOT from a hardcoded constant. This ensures the adapter remains
    correct when the Lambda is deployed to different regions.
    """
    with patch("boto3.client") as mock_boto3_client:
        mock_client = MagicMock()
        mock_boto3_client.return_value = mock_client
        adapter = BedrockAdapter(settings=_MockSettingsDifferentRegion())

    mock_boto3_client.assert_called_once_with(
        "bedrock-runtime",
        region_name="us-east-1",
    )
    assert adapter._region == "us-east-1"


def test_region_ap_south_1_by_default():
    """Settings default region must be ap-south-1 (our deployment target)."""
    with patch("boto3.client") as mock_boto3_client:
        mock_boto3_client.return_value = MagicMock()
        adapter = BedrockAdapter(settings=_MockSettings())

    assert adapter._region == "ap-south-1"


# ---------------------------------------------------------------------------
# Converse API Request Format Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_converse_uses_correct_inference_config():
    """Converse must request temperature=0 and maxTokens=1024."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "ABC", "amount": 500.0, "currency": "INR",
        "purpose": None, "payment_method": "UPI", "confidence_score": 0.9
    }))

    await adapter.extract_intent("Pay 500 to ABC")

    call_kwargs = mock_client.converse.call_args[1]
    assert call_kwargs["inferenceConfig"]["temperature"] == 0.0
    assert call_kwargs["inferenceConfig"]["maxTokens"] == 1024


@pytest.mark.asyncio
async def test_converse_sends_system_prompt():
    """Converse call must include a system prompt list."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "X", "amount": 1.0, "currency": "INR",
        "purpose": None, "payment_method": "UPI", "confidence_score": 0.9
    }))

    await adapter.extract_intent("Pay 1 to X")

    call_kwargs = mock_client.converse.call_args[1]
    assert "system" in call_kwargs
    assert isinstance(call_kwargs["system"], list)
    assert len(call_kwargs["system"]) == 1
    assert "text" in call_kwargs["system"][0]


# ---------------------------------------------------------------------------
# Intent Extraction Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_intent_happy_path():
    """Standard payment instruction → correct PaymentIntent-shaped dict."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "ABC Hardware",
        "amount": 1850.0,
        "currency": "INR",
        "purpose": "electrical fittings",
        "payment_method": "UPI",
        "confidence_score": 0.95,
    }))

    result = await adapter.extract_intent("Pay 1850 to ABC Hardware for electrical fittings")

    assert result["payee"] == "ABC Hardware"
    assert result["amount"] == 1850.0
    assert result["currency"] == "INR"
    assert result["purpose"] == "electrical fittings"
    assert result["confidence_score"] == 0.95
    assert result["extraction_model"] == _MockSettings.BEDROCK_MODEL_ID


@pytest.mark.asyncio
async def test_extract_intent_amount_coerced_to_float():
    """Amount returned as a string must be coerced to float."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "XYZ", "amount": "2500", "currency": "INR",
        "purpose": None, "payment_method": "NEFT", "confidence_score": 0.88,
    }))

    result = await adapter.extract_intent("Pay Rs 2500 to XYZ via NEFT")

    assert isinstance(result["amount"], float)
    assert result["amount"] == 2500.0


@pytest.mark.asyncio
async def test_extract_intent_currency_uppercased():
    """Currency returned in lowercase must be normalised to uppercase."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "V", "amount": 500.0, "currency": "inr",
        "purpose": None, "payment_method": "UPI", "confidence_score": 0.80,
    }))

    result = await adapter.extract_intent("Pay 500 to V")
    assert result["currency"] == "INR"


@pytest.mark.asyncio
async def test_extract_intent_confidence_clamped_above_1():
    """Confidence > 1.0 must be clamped to exactly 1.0."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "V", "amount": 1000.0, "currency": "INR",
        "purpose": None, "payment_method": "UPI", "confidence_score": 1.5,
    }))

    result = await adapter.extract_intent("Pay 1000 to V")
    assert result["confidence_score"] == 1.0


@pytest.mark.asyncio
async def test_extract_intent_confidence_clamped_below_0():
    """Confidence < 0.0 must be clamped to exactly 0.0."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "V", "amount": 1000.0, "currency": "INR",
        "purpose": None, "payment_method": "UPI", "confidence_score": -0.5,
    }))

    result = await adapter.extract_intent("Pay 1000 to V")
    assert result["confidence_score"] == 0.0


@pytest.mark.asyncio
async def test_extract_intent_blank_payee_defaults_to_unknown():
    """Blank payee from the LLM must default to 'Unknown'."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "   ", "amount": 300.0, "currency": "INR",
        "purpose": None, "payment_method": "UPI", "confidence_score": 0.50,
    }))

    result = await adapter.extract_intent("Pay 300 rupees")
    assert result["payee"] == "Unknown"


@pytest.mark.asyncio
async def test_extract_intent_markdown_fences_stripped():
    """Model output wrapped in markdown fences must be correctly parsed."""
    adapter, mock_client = _make_adapter()
    payload = json.dumps({
        "payee": "Clean Mart", "amount": 750.0, "currency": "INR",
        "purpose": "cleaning supplies", "payment_method": "UPI", "confidence_score": 0.92,
    })
    _set_response(mock_client, f"```json\n{payload}\n```")

    result = await adapter.extract_intent("Pay 750 to Clean Mart for cleaning supplies")
    assert result["payee"] == "Clean Mart"
    assert result["amount"] == 750.0


@pytest.mark.asyncio
async def test_extract_intent_non_json_raises():
    """Non-JSON model response must raise ValueError."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, "I cannot process this payment request.")

    with pytest.raises(ValueError, match="could not extract valid JSON"):
        await adapter.extract_intent("Some ambiguous input")


# ---------------------------------------------------------------------------
# Evidence Extraction — JSON Fixture (text path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_evidence_json_happy_path():
    """JSON fixture evidence extraction → correct Evidence-shaped dict via text path."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": "ABC Hardware Co.",
        "vendor_gstin": "27AAECB1234F1ZT",
        "vendor_address": "123 MG Road, Mumbai",
        "amount": 1850.0,
        "currency": "INR",
        "tax_amount": 280.50,
        "invoice_number": "INV-042",
        "invoice_date": "2026-09-15",
        "line_items": [{
            "description": "Electrical fittings",
            "quantity": 5, "unit_price": 370.0, "total": 1850.0, "hsn_code": "8536",
        }],
        "extraction_confidence": 0.94,
        "notes": None,
    }))

    result = await adapter.extract_evidence(
        b'{"vendor_name": "ABC Hardware Co.", "amount": 1850}',
        "invoice.json",
        "application/json",
    )

    assert result["vendor_name"] == "ABC Hardware Co."
    assert result["amount"] == 1850.0
    assert result["invoice_number"] == "INV-042"
    assert len(result["line_items"]) == 1
    assert result["extraction_method"] == "BEDROCK_VISION"

    # JSON fixture must use the text path — no document or image block
    call_kwargs = mock_client.converse.call_args[1]
    content_blocks = call_kwargs["messages"][0]["content"]
    assert all(b.get("type") != "document" for b in content_blocks)
    assert all("document" not in b for b in content_blocks)
    assert all("image" not in b for b in content_blocks)


# ---------------------------------------------------------------------------
# Evidence Extraction — PDF document path (Converse "document" block)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_evidence_pdf_uses_document_block():
    """
    PDF evidence must use the Converse API 'document' block with raw bytes.
    It must NOT manually base64-encode the PDF — Converse handles encoding internally.
    This path was broken in the InvokeModel implementation (ValidationException).
    """
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": "PDF Vendor", "amount": 3500.0, "currency": "INR",
        "tax_amount": None, "invoice_number": "PDF-001", "invoice_date": "2026-09-10",
        "line_items": [], "extraction_confidence": 0.88, "notes": None,
    }))

    fake_pdf = b"%PDF-1.4 " + b"\x00" * 50  # minimal fake PDF bytes
    result = await adapter.extract_evidence(fake_pdf, "invoice.pdf", "application/pdf")

    assert result["vendor_name"] == "PDF Vendor"
    assert result["amount"] == 3500.0

    call_kwargs = mock_client.converse.call_args[1]
    content_blocks = call_kwargs["messages"][0]["content"]

    # Must contain exactly one "document" block
    doc_blocks = [b for b in content_blocks if "document" in b]
    assert len(doc_blocks) == 1, "PDF path must produce exactly one document block"

    doc = doc_blocks[0]["document"]
    assert doc["format"] == "pdf"
    assert doc["source"]["bytes"] == fake_pdf, (
        "Raw bytes must be passed directly — NOT base64-encoded. "
        "Converse API handles encoding internally."
    )

    # Must NOT contain an "image" block
    image_blocks = [b for b in content_blocks if "image" in b]
    assert len(image_blocks) == 0


# ---------------------------------------------------------------------------
# Evidence Extraction — Image path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_evidence_image_uses_image_block():
    """Image content types must use Converse 'image' block with correct format name."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": "Photo Vendor", "amount": 2000.0, "currency": "INR",
        "tax_amount": None, "invoice_number": "IMG-001", "invoice_date": None,
        "line_items": [], "extraction_confidence": 0.82, "notes": None,
    }))

    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 50
    result = await adapter.extract_evidence(fake_jpeg, "invoice.jpg", "image/jpeg")

    assert result["vendor_name"] == "Photo Vendor"

    call_kwargs = mock_client.converse.call_args[1]
    content_blocks = call_kwargs["messages"][0]["content"]

    image_blocks = [b for b in content_blocks if "image" in b]
    assert len(image_blocks) == 1, "JPEG path must produce exactly one image block"

    img = image_blocks[0]["image"]
    assert img["format"] == "jpeg"            # Converse uses lowercase without "image/" prefix
    assert img["source"]["bytes"] == fake_jpeg
    assert "document" not in image_blocks[0]  # Must not use document block for images


@pytest.mark.parametrize("content_type,expected_format", [
    ("image/jpeg", "jpeg"),
    ("image/jpg",  "jpeg"),
    ("image/png",  "png"),
    ("image/webp", "webp"),
    ("image/gif",  "gif"),
])
@pytest.mark.asyncio
async def test_image_format_mapping(content_type: str, expected_format: str):
    """Each supported image MIME type must map to the correct Converse format name."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": "V", "amount": 100.0, "currency": "INR",
        "tax_amount": None, "invoice_number": None, "invoice_date": None,
        "line_items": [], "extraction_confidence": 0.80, "notes": None,
    }))

    await adapter.extract_evidence(b"\x00" * 10, "img", content_type)

    call_kwargs = mock_client.converse.call_args[1]
    content_blocks = call_kwargs["messages"][0]["content"]
    image_blocks = [b for b in content_blocks if "image" in b]
    assert image_blocks[0]["image"]["format"] == expected_format


# ---------------------------------------------------------------------------
# Evidence Extraction — Robustness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_evidence_malformed_line_items_skipped():
    """Malformed line items must be skipped silently without failing extraction."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": "Test Vendor", "amount": 500.0, "currency": "INR",
        "tax_amount": None, "invoice_number": "INV-001", "invoice_date": None,
        "line_items": [
            {"description": "Good item", "quantity": 1, "unit_price": 500.0, "total": 500.0},
            "this is not a dict",
            {"description": "Bad", "quantity": "NaN", "unit_price": None, "total": "bad"},
        ],
        "extraction_confidence": 0.80, "notes": None,
    }))

    result = await adapter.extract_evidence(b"{}", "invoice.json", "application/json")
    assert len(result["line_items"]) == 1
    assert result["line_items"][0]["description"] == "Good item"


@pytest.mark.asyncio
async def test_extract_evidence_null_vendor_name():
    """vendor_name=None is a valid extraction result (unclear document)."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": None, "amount": 100.0, "currency": "INR",
        "tax_amount": None, "invoice_number": "R-999", "invoice_date": None,
        "line_items": [], "extraction_confidence": 0.60, "notes": "Partial scan",
    }))

    result = await adapter.extract_evidence(b"{}", "receipt.json", "application/json")
    assert result["vendor_name"] is None
    assert result["extraction_confidence"] == 0.60


@pytest.mark.asyncio
async def test_extract_evidence_confidence_clamped_over_1():
    """Confidence > 1.0 from the LLM must be clamped to 1.0."""
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "vendor_name": "V", "amount": 200.0, "currency": "INR",
        "tax_amount": None, "invoice_number": None, "invoice_date": None,
        "line_items": [], "extraction_confidence": 2.0, "notes": None,
    }))

    result = await adapter.extract_evidence(b"{}", "f.json", "application/json")
    assert result["extraction_confidence"] == 1.0


# ---------------------------------------------------------------------------
# Security Invariant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_injected_decision_fields_not_propagated():
    """
    Security invariant: LLM output must never propagate decision fields.
    Even if the model returns 'decision', 'approved', 'authorization' in its
    JSON, those keys must be absent from the returned dict.

    The adapter's explicit field extraction (not dict spreading) ensures this.
    """
    adapter, mock_client = _make_adapter()
    _set_response(mock_client, json.dumps({
        "payee": "Test Payee",
        "amount": 500.0,
        "currency": "INR",
        "purpose": None,
        "payment_method": "UPI",
        "confidence_score": 0.90,
        # Injected fields — must be filtered out
        "decision": "ALLOW",
        "approved": True,
        "authorization": "granted",
    }))

    result = await adapter.extract_intent("Pay 500 to Test Payee")

    assert "decision" not in result
    assert "approved" not in result
    assert "authorization" not in result
    assert set(result.keys()) == {
        "payee", "amount", "currency", "purpose",
        "payment_method", "confidence_score", "extraction_model",
    }
