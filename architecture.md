# AgentPay Sentinel — System Architecture

> **Evidence-Aware Trust Gateway for AI-Initiated Payments**
> Version: 0.2.0 (Hackathon MVP — Revised)
> Last Updated: 2026-09-17

---

## 1. Design Philosophy

```
LLM  →  understands intent + evidence + context
Policy Engine  →  makes the final authorization decision (deterministic, explicit signals)
```

The AI agent is never the final authority on whether a payment is authorized.
All authorization decisions are made by a deterministic policy layer that operates on
**explicit boolean/enumerated signals** — not on a floating-point score.

A numeric risk presentation value may be derived for the UI, but it plays no role in
the authorization logic. The policy engine reads named signals directly.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER / AI AGENT                                │
│              (Browser UI or programmatic agent client)                  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite + TS)                     │
│  • Upload invoice (PDF/image)                                           │
│  • Input payment intent (amount, payee, purpose)                        │
│  • View trust decision + evidence comparison                            │
│  • View tamper-evident audit trail                                      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ REST API
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    AWS API GATEWAY                                      │
│  • Rate limiting, CORS, auth token validation                           │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               TRUST GATEWAY — FastAPI Application                       │
│               (Single deployment: Lambda + container or EC2)            │
│                                                                         │
│  Internal modular services (all in-process, no per-service Lambda):     │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  1. Auth Service        session/token validation                 │  │
│  │  2. Intent Service      LLM extraction (Bedrock) → structured    │  │
│  │  3. Evidence Service    document parsing (Bedrock Vision)        │  │
│  │  4. Comparison Service  deterministic signal computation          │  │
│  │  5. Signal Evaluator    explicit boolean/enum risk signals        │  │
│  │  6. Policy Engine       priority-ordered rules → ALLOW/DENY/HRA  │  │
│  │  7. Audit Service       tamper-evident trail (chained SHA-256)    │  │
│  │  8. Payment Simulator   clearly-labeled sandbox only              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  AWS adapters (stub locally, real on Day 2):                           │
│    S3Store | DynamoStore | BedrockClient                               │
└─────────────────────────────────────────────────────────────────────────┘
                   │              │              │
                   ▼              ▼              ▼
              ┌────────┐   ┌──────────┐   ┌──────────────┐
              │   S3   │   │ DynamoDB │   │   Bedrock    │
              │evidence│   │audit/sess│   │Claude Sonnet │
              └────────┘   └──────────┘   └──────────────┘
```

**Deployment note**: One FastAPI application deployed as a single Lambda function
(or container). Internal services are Python modules, not separate Lambda functions.
Separate Lambdas are introduced only if a demonstrated performance or isolation
need arises (e.g., async evidence extraction for large files).

---

## 3. Request Lifecycle — Step-by-Step

```
Step 1: AUTHENTICATE
  Agent/User sends session token
  → Auth Service validates (API-key session Day 1, Cognito JWT Day 3)
  → Returns: User{id, name, tier, spending_limit_inr}
  Note: no "user trust_score" — we evaluate the TRANSACTION, not the human.

Step 2: EXTRACT INTENT
  Agent sends raw payment instruction (natural language or structured)
  → Bedrock (Claude Sonnet) extracts structured fields
  → Schema-validated before any further processing (LLM output = untrusted)
  → Returns: PaymentIntent{payee, amount, currency, purpose, payment_method}

Step 3: EXTRACT EVIDENCE
  Agent uploads invoice to S3 (Day 1: local temp store)
  → Evidence Service calls Bedrock Vision to parse document
  → Textract is an optional fallback, not a mandatory dependency
  → Returns: Evidence{vendor_name, amount, invoice_number, line_items[], ...}

Step 4: COMPUTE EXPLICIT SIGNALS  ← DETERMINISTIC, NO LLM
  Comparison Service computes named boolean/enum signals:

  Signal                      Type      How computed
  ─────────────────────────── ───────── ───────────────────────────────────
  amount_match                bool      |intent.amount − evidence.amount| ≤ ₹1
  payee_match                 bool      fuzzy_sim(intent.payee, evidence.vendor) ≥ 0.85
  evidence_present            bool      evidence object exists and is non-empty
  evidence_extraction_ok      bool      extraction_confidence ≥ 0.70
  amount_within_limit         bool      intent.amount ≤ user.spending_limit_inr
  payee_seen_before           bool      DynamoDB payee history lookup
  currency_match              bool      intent.currency == evidence.currency

  → Returns: TransactionSignals{...all signals above}

Step 5: POLICY EVALUATION  ← DETERMINISTIC, reads signals directly
  Priority-ordered rules evaluated against TransactionSignals:
  First matching rule wins. No floating-point score in condition logic.

  [See Section 6: Policy Rules]

  → Returns: PolicyResult{decision, matched_rule_ids[], reason}

Step 6: AUTHORIZATION DECISION
  Decision is exactly the PolicyResult decision. No additional LLM call.
  → Returns: AuthorizationDecision{
      decision: ALLOW | DENY | REQUIRE_HUMAN_APPROVAL,
      signals: TransactionSignals,
      matched_rule_ids[], reason, expires_at
    }

  Presentation-only: a display_risk_score (0–100) may be derived from
  signals for the UI gauge. It is computed after the decision and has
  no effect on authorization.

Step 7: AUDIT EVENT (written BEFORE response is sent)
  Tamper-evident audit trail:
  → event_hash = SHA-256(canonical JSON of event payload)
  → prev_hash = hash of previous event for this user
  → chained_hash = SHA-256(event_hash + prev_hash)
  → Stored in DynamoDB with chained_hash
  → CloudWatch: metrics emitted (decision_made, decision_type, amount_band)

Step 8: MOCK PAYMENT EXECUTION (only when decision == ALLOW)
  Clearly labeled sandbox simulator:
  → Returns: PaymentResult{
      status: "SIMULATED_SUCCESS",
      transaction_id: "MOCK-YYYYMMDD-NNN",
      disclaimer: "⚠️ Sandbox simulation only. No real payment was made."
    }
```

---

## 4. Primary Demo Scenario (Mandatory)

This is the canonical scenario used in the hackathon demo:

```
User intent (legitimate):
  "Pay ₹1,850 to ABC Hardware."
  Evidence uploaded: ABC Hardware invoice, ₹1,850, INV-042

Malicious / incorrect agent action:
  Agent attempts: ₹18,500 to XYZ Traders

Trust Gateway response:
  Signal: amount_match        = FALSE  (₹18,500 ≠ ₹1,850 — delta ₹16,650)
  Signal: payee_match         = FALSE  (similarity("XYZ Traders","ABC Hardware") = 0.12)
  Policy: DENY
  Reason: "Amount mismatch: agent requested ₹18,500 but evidence shows ₹1,850.
           Payee mismatch: agent specified 'XYZ Traders' but evidence is for
           'ABC Hardware'. Payment blocked."

  No mock payment is simulated.
  Full denial logged in tamper-evident audit trail.
```

---

## 5. AWS Services Map

| Service | Role | When introduced |
|---|---|---|
| **API Gateway** | HTTP entry point, CORS, rate limiting | Day 1 (local dev server Day 1) |
| **S3** | Evidence file storage | Day 2 |
| **DynamoDB** | Audit trail, session store, payee history | Day 2 |
| **Amazon Bedrock** | Intent + evidence extraction (Claude Sonnet) | Day 2 |
| **Lambda** | Single function wrapping the FastAPI app | Day 2 |
| **Cognito** | JWT-based user auth | Day 3 |
| **CloudWatch** | Metrics + structured logs | Day 2 |
| **Textract** | Optional OCR fallback for scanned PDFs | Day 3 (if needed) |
| **Cedar / AgentCore** | Declarative policy — additive, not a blocker | Day 4 (if time allows) |

> **Day 1**: Everything runs locally. All AWS adapters have local stub implementations.
> AWS services are swapped in behind adapter interfaces on Day 2 — no application logic changes.

---

## 6. Policy Rules (MVP — Signal-Based, No Score Dependencies)

Rules are evaluated in priority order. First match wins.
Policy conditions reference **named signals** from `TransactionSignals`, not a derived score.

| Priority | Rule ID | Condition (on explicit signals) | Decision |
|---|---|---|---|
| 10 | `deny_evidence_missing_high_amount` | `NOT evidence_present AND amount > 500` | DENY |
| 20 | `deny_amount_mismatch` | `evidence_present AND NOT amount_match` | DENY |
| 30 | `deny_payee_mismatch` | `evidence_present AND NOT payee_match` | DENY |
| 40 | `deny_low_confidence_extraction` | `evidence_present AND NOT evidence_extraction_ok` | DENY |
| 50 | `human_approval_exceeds_limit` | `NOT amount_within_limit` | REQUIRE_HUMAN_APPROVAL |
| 60 | `human_approval_unknown_payee_medium_amount` | `NOT payee_seen_before AND amount > 2000` | REQUIRE_HUMAN_APPROVAL |
| 70 | `allow_full_match` | `amount_match AND payee_match AND evidence_present AND amount_within_limit` | ALLOW |
| 80 | `allow_small_no_evidence` | `NOT evidence_present AND amount <= 500 AND amount_within_limit` | ALLOW |

**Cedar / AgentCore** (Day 4, additive): These same rules may be ported to Cedar policy language.
The Python policy engine remains fully functional and is never blocked by Cedar availability.

---

## 7. Module Breakdown

### 7.1 Backend (`backend/app/`)

```
backend/app/
├── main.py                     # FastAPI app, CORS, middleware, router registration
├── config.py                   # Pydantic Settings (env vars, AWS region, limits)
├── models/
│   ├── user.py                 # User, UserTier (no trust_score)
│   ├── payment_intent.py       # PaymentIntent, IntentStatus
│   ├── evidence.py             # Evidence, EvidenceItem, EvidenceMatch
│   ├── signals.py              # TransactionSignals (explicit boolean/enum)
│   ├── policy.py               # PolicyRule, PolicyResult
│   ├── authorization.py        # AuthorizationDecision, Decision enum
│   └── audit.py                # AuditEvent, AuditEventType, chained hash fields
├── routers/
│   ├── auth.py                 # POST /auth/session, GET /auth/me
│   ├── payments.py             # POST /payments/initiate, /approve, /deny
│   ├── evidence.py             # POST /evidence/upload, /extract; GET /evidence/{id}
│   ├── audit.py                # GET /audit/events, GET /audit/events/{id}
│   └── policy.py               # GET /policies/rules
├── services/
│   ├── auth_service.py         # Session validation, user lookup
│   ├── intent_service.py       # Bedrock intent extraction + schema validation
│   ├── evidence_service.py     # Bedrock Vision extraction; Textract as optional fallback
│   ├── comparison_service.py   # Deterministic signal computation from intent + evidence
│   ├── policy_service.py       # Priority-ordered rule evaluation
│   ├── authorization_service.py# Pipeline orchestrator → final decision
│   ├── audit_service.py        # Tamper-evident event logging (chained SHA-256)
│   └── payment_simulator.py    # Clearly-labeled sandbox mock payment
├── adapters/
│   ├── base.py                 # Abstract base classes (StorageAdapter, LLMAdapter)
│   ├── local.py                # Local stub implementations (Day 1)
│   ├── s3.py                   # S3 evidence storage (Day 2)
│   ├── dynamo.py               # DynamoDB audit + session (Day 2)
│   └── bedrock.py              # Bedrock LLM + Vision (Day 2)
└── utils/
    ├── fuzzy.py                # Fuzzy string matching (rapidfuzz)
    └── crypto.py               # SHA-256, chained hash utilities
```

**No `policies/rules.py`** — rule definitions live in `models/policy.py` as `MVP_POLICY_RULES`.
**No per-service Lambda** — all services are plain Python modules called by `authorization_service.py`.

### 7.2 Frontend (`frontend/src/`)

```
frontend/src/
├── components/
│   ├── PaymentForm/            # Payee, amount, currency, purpose input
│   ├── InvoiceUploader/        # Drag-drop upload with preview
│   ├── TrustDecisionPanel/     # Animated ALLOW/DENY/HUMAN_APPROVAL verdict
│   ├── SignalBreakdown/        # Table of all explicit signals (replaces RiskGauge)
│   ├── EvidenceViewer/         # Side-by-side intent vs extracted evidence
│   └── AuditLog/               # Tamper-evident trail with chained hash display
├── pages/
│   ├── Dashboard.tsx           # Main workflow page
│   ├── AuditTrail.tsx          # Historical decisions + hash chain viewer
│   └── PolicyExplorer.tsx      # Active policy rules (read-only)
├── api/client.ts               # Typed fetch wrapper
├── types/index.ts              # TypeScript types mirroring backend models
└── stores/trustStore.ts        # Zustand state for the payment workflow
```

### 7.3 Tests (`tests/`)

```
tests/
├── unit/
│   ├── test_policy_engine.py   # All 8 rules: matching + non-matching cases
│   ├── test_signal_computation.py # Each signal: correct true/false outcome
│   └── test_audit_chain.py     # Hash chain integrity + tamper detection
├── integration/
│   └── test_full_workflow.py   # Happy path, denial (amount+payee mismatch), HRA path
└── fixtures/
    ├── sample_invoice.json     # Pre-parsed invoice fixture
    └── sample_users.json       # BASIC / STANDARD / PREMIUM tier users
```

---

## 8. Security Principles

1. **Evidence extracted server-side only** — client cannot inject pre-parsed evidence
2. **LLM output is schema-validated before reaching policy** — Bedrock responses treated as untrusted
3. **Policy reads explicit signals, never raw LLM text** — no prompt injection path to authorization
4. **Audit-first** — event is written to DynamoDB before API response is returned
5. **Tamper-evident audit trail** — each event carries a chained SHA-256 hash linking to prior event
6. **Mock payment is unambiguously labeled** — disclaimer embedded in every `MockPaymentResult`
7. **Cedar is additive** — policy engine functions without it; Cedar is never a blocker

---

## 9. Non-Goals (MVP)

- Real UPI / banking integration (sandbox only)
- Device fingerprinting
- Global user trust score (we evaluate transactions, not people)
- One Lambda per internal service (single-app deployment)
- Multi-currency conversion
- Mobile app
- Multi-agent orchestration
- Mandatory Textract dependency
