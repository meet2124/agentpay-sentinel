# AgentPay Sentinel — Product Specification

> **Evidence-Aware Trust Gateway for AI-Initiated Payments**
> Version: 0.2.0 — Hackathon MVP (Revised)
> Hackathon: First Commit | AWS Ship It Track

---

## 1. Problem Statement

AI agents are beginning to perform consequential real-world actions: booking travel, filing documents, and increasingly — initiating financial transactions. Current AI systems have no deterministic trust boundary between "agent proposes payment" and "payment is executed."

This creates three critical failure modes:

| Failure Mode | Example | Risk |
|---|---|---|
| **Amount Hallucination** | Agent submits ₹18,500 when invoice says ₹1,850 | Financial loss |
| **Payee Substitution** | Agent targets "XYZ Traders" when evidence names "ABC Hardware" | Fraud |
| **Authorization Bypass** | Agent self-authorizes a payment with no supporting evidence | Trust violation |

**AgentPay Sentinel** is a Trust Gateway that sits between an AI agent and payment execution. It extracts intent and evidence via LLM, computes explicit deterministic signals, applies a policy engine, and makes the final authorization decision — independently of the LLM output.

---

## 2. Core Product Principle

> **"LLMs understand. Policies decide."**

The LLM layer (Amazon Bedrock) is used only for:
- Extracting structured payment intent from natural language
- Parsing unstructured invoice documents into structured Evidence objects

All LLM output is **schema-validated** before it reaches the policy layer.
The policy engine evaluates **explicit, named boolean/enum signals** — never raw LLM text.
A numeric `display_risk_score` may be computed for the UI, but plays no role in authorization logic.

---

## 3. User Persona

**Primary User: Developer / Technical Evaluator**
- Building an AI payment agent or evaluating trust infrastructure for agentic systems
- Wants to see a complete, reliable workflow — not a demo that lies about what's simulated

**Secondary User: Business Stakeholder (demo audience)**
- Wants to understand the trust value proposition visually
- Must be immediately wowed by the interface

---

## 4. MVP Scenarios

### 4.1 Primary Demo Scenario — Malicious Agent Interception (MANDATORY)

This is the canonical scenario used in the hackathon demo. It must work reliably.

```
Legitimate user intent:
  "Pay ₹1,850 to ABC Hardware."
  Evidence uploaded: ABC Hardware invoice, ₹1,850.00, INV-042

What a malicious or hallucinating agent attempts:
  Payee: "XYZ Traders"
  Amount: ₹18,500

Trust Gateway signals:
  amount_match   = FALSE  (₹18,500 vs ₹1,850 — delta: ₹16,650)
  payee_match    = FALSE  (similarity score: 0.12, threshold: 0.85)

Policy decision: DENY

UI displays:
  ❌ PAYMENT BLOCKED
  • Amount mismatch: Agent requested ₹18,500 — evidence shows ₹1,850
  • Payee mismatch: Agent targeted 'XYZ Traders' — evidence is for 'ABC Hardware'

No mock payment is simulated. Denial logged in tamper-evident audit trail.
```

### 4.2 Happy Path — All Signals Match (ALLOW)

```
User: "Pay ₹1,850 to ABC Hardware."
Evidence: ABC Hardware Co., ₹1,850.00, INV-042

Signals:
  amount_match          = TRUE  (delta: ₹0)
  payee_match           = TRUE  (similarity: 0.94)
  evidence_present      = TRUE
  evidence_extraction_ok= TRUE  (confidence: 0.94)
  amount_within_limit   = TRUE  (₹1,850 ≤ ₹10,000 limit)
  currency_match        = TRUE

Policy: ALLOW (rule: allow_full_match)
[SANDBOX] Payment simulated: MOCK-20260917-001
⚠️ Sandbox simulation. No real payment was made.
```

### 4.3 Human Approval Path — Ambiguous Case

```
User: "Pay ₹5,000 to TechSupply Co."
Evidence: TechSupplies Pvt Ltd, ₹5,000.00

Signals:
  amount_match        = TRUE
  payee_match         = FALSE  (similarity: 0.72 — below 0.85 threshold)
  amount_within_limit = TRUE
  payee_seen_before   = FALSE
  amount > 2000       = TRUE

Policy: REQUIRE_HUMAN_APPROVAL
  (rule: human_approval_unknown_payee_medium_amount)

UI: Shows signal breakdown + evidence comparison side-by-side
    Human clicks "Approve" → decision re-evaluated → ALLOW → Mock payment
```

---

## 5. Feature List

### P0 — Must Have (Day 1–2)

| Feature | Description |
|---|---|
| Payment Intent Input | Form: payee, amount, currency, purpose |
| Invoice Upload | Drag-drop PDF/image, stored in S3 (local temp Day 1) |
| Intent Extraction | Bedrock (Claude Sonnet) → structured PaymentIntent |
| Evidence Extraction | Bedrock Vision → structured Evidence (Textract optional fallback) |
| Signal Computation | Deterministic: amount_match, payee_match, evidence_present, etc. |
| Policy Evaluation | Priority-ordered rules on explicit signals → ALLOW/DENY/HRA |
| Authorization Decision | Final verdict with matched rules and signal breakdown |
| Trust Decision UI | Animated ALLOW (green) / DENY (red) / HRA (amber) with signal detail |
| Tamper-Evident Audit Trail | Chained SHA-256 hash per event, stored in DynamoDB |
| Mock Payment | Clearly-labeled sandbox — NEVER a real payment |

### P1 — Should Have (Day 3)

| Feature | Description |
|---|---|
| Evidence Viewer | Side-by-side intent vs extracted evidence comparison |
| Signal Breakdown Panel | Explicit table of all named signals (replaces opaque gauge) |
| Policy Explorer | Read-only rule list with condition + action |
| Payee History | Track seen vs new payees per user in DynamoDB |
| Audit Chain Viewer | Display hash chain with tamper-detection indicator |
| Cognito Auth | JWT-based session management |
| display_risk_score | Derived UI-only gauge (0–100) from signals — no policy role |

### P2 — Nice to Have (Day 4)

| Feature | Description |
|---|---|
| Cedar / AgentCore | Port policy rules to Cedar (additive — Python engine stays primary) |
| CloudWatch Metrics | decision_made, denial_rate, avg_amount_band |
| Textract Fallback | Activate for scanned PDFs if Bedrock Vision proves insufficient |
| Demo Recording | Screen-recorded walkthrough of all 3 scenarios |

---

## 6. API Contracts

### 6.1 Data Models

#### User

```json
{
  "user_id": "usr_abc123",
  "name": "Priya Sharma",
  "email": "priya@example.com",
  "tier": "STANDARD",
  "spending_limit_inr": 10000.00,
  "created_at": "2026-09-01T00:00:00Z",
  "is_active": true
}
```

> `trust_score` has been removed. The system evaluates individual transactions using
> explicit signals, not a global assessment of the human initiating them.

**UserTier enum**: `BASIC | STANDARD | PREMIUM | ENTERPRISE`

---

#### PaymentIntent

```json
{
  "intent_id": "intent_xyz789",
  "user_id": "usr_abc123",
  "session_id": "sess_001",
  "raw_input": "Pay ₹1,850 to ABC Hardware.",
  "payee": "ABC Hardware",
  "amount": 1850.00,
  "currency": "INR",
  "purpose": null,
  "payment_method": "UPI",
  "status": "PENDING_AUTHORIZATION",
  "confidence_score": 0.97,
  "extraction_model": "bedrock/claude-3-sonnet",
  "created_at": "2026-09-17T11:55:00Z",
  "expires_at": "2026-09-17T12:55:00Z"
}
```

**IntentStatus enum**: `PENDING_AUTHORIZATION | AUTHORIZED | DENIED | HUMAN_APPROVAL_REQUIRED | HUMAN_APPROVED | HUMAN_DENIED | EXPIRED`

---

#### Evidence

```json
{
  "evidence_id": "evid_def456",
  "intent_id": "intent_xyz789",
  "user_id": "usr_abc123",
  "source_type": "INVOICE_PDF",
  "s3_key": "evidence/usr_abc123/invoice_abc_hardware.pdf",
  "vendor_name": "ABC Hardware Co.",
  "vendor_gstin": "29AABCU9603R1ZX",
  "amount": 1850.00,
  "currency": "INR",
  "invoice_number": "INV-042",
  "invoice_date": "2026-09-15",
  "line_items": [
    {
      "description": "Electrical fittings - Type A",
      "quantity": 5,
      "unit_price": 370.00,
      "total": 1850.00
    }
  ],
  "extraction_method": "BEDROCK_VISION",
  "extraction_confidence": 0.94,
  "extracted_at": "2026-09-17T11:55:10Z"
}
```

**Textract** is an optional fallback for low-confidence Bedrock Vision extractions.
It is not a mandatory dependency.

---

#### TransactionSignals

The central output of the Comparison Service. These are the direct inputs to the Policy Engine.

```json
{
  "intent_id": "intent_xyz789",
  "evidence_id": "evid_def456",

  "amount_match": true,
  "amount_delta_inr": 0.00,

  "payee_match": true,
  "payee_similarity": 0.94,

  "evidence_present": true,
  "evidence_extraction_ok": true,
  "evidence_extraction_confidence": 0.94,

  "currency_match": true,

  "amount_within_limit": true,
  "amount_vs_limit_ratio": 0.185,

  "payee_seen_before": true,

  "display_risk_score": 12,

  "computed_at": "2026-09-17T11:55:12Z"
}
```

> `display_risk_score` is a derived presentation value for the UI gauge only.
> No policy rule conditions reference it.
> There is no `device_fingerprint` signal.

---

#### PolicyRule

```json
{
  "rule_id": "deny_amount_mismatch",
  "name": "Deny: Amount Mismatch",
  "description": "Deny when evidence is present but intent amount differs from evidence amount",
  "condition": "signals.evidence_present AND NOT signals.amount_match",
  "action": "DENY",
  "priority": 20,
  "is_active": true,
  "version": "1.0.0"
}
```

---

#### PolicyResult

```json
{
  "intent_id": "intent_xyz789",
  "decision": "DENY",
  "matched_rule_ids": ["deny_amount_mismatch", "deny_payee_mismatch"],
  "evaluated_rule_count": 8,
  "reason": "Amount mismatch (₹18,500 vs ₹1,850). Payee mismatch ('XYZ Traders' vs 'ABC Hardware').",
  "evaluated_at": "2026-09-17T11:55:13Z"
}
```

---

#### AuthorizationDecision

```json
{
  "decision_id": "dec_jkl345",
  "intent_id": "intent_xyz789",
  "user_id": "usr_abc123",
  "decision": "DENY",
  "reason": "Amount mismatch (₹18,500 vs ₹1,850). Payee mismatch ('XYZ Traders' vs 'ABC Hardware').",
  "matched_rule_ids": ["deny_amount_mismatch", "deny_payee_mismatch"],
  "signals": { "...TransactionSignals": "..." },
  "requires_human": false,
  "human_approved": null,
  "payment_result": null,
  "expires_at": "2026-09-17T12:55:13Z",
  "decided_at": "2026-09-17T11:55:13Z"
}
```

**Decision enum**: `ALLOW | DENY | REQUIRE_HUMAN_APPROVAL`

> `confidence` field has been removed from `AuthorizationDecision` — deterministic policy
> decisions are either matched or not; a floating-point confidence is misleading.

---

#### AuditEvent (Tamper-Evident)

Each event in the audit trail is linked to the previous event via a chained SHA-256 hash.
This makes any modification to a past record detectable.

```json
{
  "event_id": "audit_mno678",
  "event_type": "AUTHORIZATION_DECISION",
  "user_id": "usr_abc123",
  "intent_id": "intent_xyz789",
  "decision_id": "dec_jkl345",
  "decision": "DENY",

  "intent_snapshot": { "...PaymentIntent at decision time": "..." },
  "evidence_snapshot": { "...Evidence at decision time": "..." },
  "signals_snapshot": { "...TransactionSignals": "..." },
  "policy_snapshot": { "...PolicyResult": "..." },
  "payment_result_snapshot": null,

  "event_hash": "sha256:<hash of this event payload>",
  "prev_event_hash": "sha256:<hash of previous event for this user>",
  "chained_hash": "sha256:<SHA-256(event_hash + prev_event_hash)>",

  "timestamp": "2026-09-17T11:55:14Z"
}
```

**AuditEventType enum**: `SESSION_CREATED | INTENT_EXTRACTED | EVIDENCE_UPLOADED | EVIDENCE_EXTRACTED | SIGNALS_COMPUTED | POLICY_EVALUATED | AUTHORIZATION_DECISION | HUMAN_APPROVAL_REQUESTED | HUMAN_APPROVED | HUMAN_DENIED | PAYMENT_SIMULATED`

---

### 6.2 REST API Endpoints

#### Auth
```
POST /auth/session
  Body:     { "user_id": "usr_abc123", "api_key": "sk-test-..." }
  Response: { "session_id": "...", "token": "...", "expires_at": "...", "user": User }

GET /auth/me
  Headers:  Authorization: Bearer <token>
  Response: User
```

#### Payment Workflow
```
POST /payments/initiate
  Body:     { "raw_input": "Pay ₹1,850 to ABC Hardware.", "evidence_id": "evid_def456" }
  Response: AuthorizationDecision  (+ MockPaymentResult if decision == ALLOW)

POST /payments/{intent_id}/approve
  (Human confirms a REQUIRE_HUMAN_APPROVAL decision)
  Response: AuthorizationDecision

POST /payments/{intent_id}/deny
  (Human rejects a REQUIRE_HUMAN_APPROVAL decision)
  Response: AuthorizationDecision
```

#### Evidence
```
POST /evidence/upload
  Body:     multipart/form-data { file: <PDF|image> }
  Response: { "evidence_id": "...", "s3_key": "...", "status": "uploaded" }

POST /evidence/extract
  Body:     { "evidence_id": "evid_def456" }
  Response: Evidence

GET /evidence/{evidence_id}
  Response: Evidence
```

#### Audit
```
GET /audit/events
  Query:    ?user_id=&limit=50&offset=0&decision=DENY
  Response: { "events": AuditEvent[], "total": 123 }

GET /audit/events/{event_id}
  Response: AuditEvent
```

#### Policy
```
GET /policies/rules
  Response: { "rules": PolicyRule[], "version": "1.0.0" }
```

---

## 7. Policy Rules (MVP Set — Signal-Based)

Rules are evaluated in priority order (lower number = higher priority). First match wins.
All conditions reference **named signals from `TransactionSignals`**.
No condition references a derived score or a floating-point value.

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

---

## 8. 4-Day Execution Timeline

| Day | Focus | Key Deliverables |
|---|---|---|
| **Day 1** | Local complete workflow | All backend services (mock adapters), all API endpoints, frontend scaffolding, 3 demo scenarios pass locally |
| **Day 2** | AWS cloud deployment | S3 + DynamoDB + Bedrock live, Lambda deployment, all 3 scenarios work on AWS URL |
| **Day 3** | Auth + hardening + UI | Cognito JWT, audit chain verification, edge cases, Signal Breakdown UI, Audit Trail viewer |
| **Day 4** | Polish + demo + submit | Production hardening, demo rehearsal, documentation, submission |

**Cedar / AgentCore**: introduced in Day 4 if integration is clean. Python policy engine is never blocked by it.
**Textract**: activated in Day 3 only if Bedrock Vision proves insufficient for real invoice files.

---

## 9. Success Criteria (Hackathon Demo)

- [ ] Primary demo scenario (malicious agent interception) works reliably: DENY with explicit mismatch reasons
- [ ] Happy path works end-to-end to mock payment in < 30 seconds
- [ ] Human approval path shows side-by-side evidence comparison with approve/deny UX
- [ ] Tamper-evident audit trail shows chained hashes for every decision event
- [ ] Policy engine decisions can be explained by pointing at exactly which named signals triggered which rule
- [ ] Mock payment disclaimer is prominently visible — no misleading claims
- [ ] UI is visually impressive and demo-ready
- [ ] All 3 scenarios pass automated integration tests
