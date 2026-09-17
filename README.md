# AgentPay Sentinel

> **An Evidence-Aware Trust Gateway for AI-Initiated Payments**

[![Hackathon](https://img.shields.io/badge/Hackathon-First%20Commit-blueviolet)](.)
[![Track](https://img.shields.io/badge/AWS-Ship%20It%20Track-FF9900)](.)
[![Status](https://img.shields.io/badge/Status-MVP%20Development-green)](.)
[![License](https://img.shields.io/badge/License-MIT-blue)](.)

---

## What is AgentPay Sentinel?

As AI agents begin performing consequential actions — including financial transactions — we need a **deterministic trust boundary** between "the agent proposes a payment" and "the payment is executed."

AgentPay Sentinel is that boundary.

It is a **Trust Gateway** that verifies:
- 🔐 **Identity** — who is initiating this action?
- 📋 **Intent** — what exactly is being requested?
- 🧾 **Evidence** — does supporting documentation match the intent?
- ⚠️ **Risk** — how risky is this transaction in context?
- ⚖️ **Policy** — do deterministic authorization rules approve it?

Only after all five checks pass does it allow (a simulated) payment to proceed.

---

## Core Design Principle

```
LLM → understands intent, evidence, and context
Policy Engine → makes the final authorization decision (deterministic)
```

The LLM is never the final authority. It is an evidence extractor and intent interpreter. The policy engine — running deterministic, auditable rules — decides ALLOW, DENY, or REQUIRE_HUMAN_APPROVAL.

---

## MVP Demo Scenario

```
User: "Pay ₹1,850 to ABC Hardware for electrical fittings"
[Uploads: invoice_abc_hardware.pdf]

Trust Gateway:
  ✅ Intent extracted:  payee=ABC Hardware, amount=₹1,850, purpose=electrical fittings
  ✅ Evidence parsed:   vendor=ABC Hardware Co., amount=₹1,850.00, invoice=INV-042
  ✅ Evidence matches:  amount_delta=₹0, payee_similarity=94%
  ✅ Risk assessed:     score=18/100, level=LOW
  ✅ Policy evaluated:  ALLOW (all checks pass, within spending limit)
  ✅ Audit logged:      event_id=audit_mno678, checksum=sha256:abc123...

[SANDBOX] Payment simulated: MOCK-20260917-001
⚠️  This is a sandbox simulation. No real payment was made.
```

---

## Architecture Overview

```
User/Agent → Frontend (React+Vite+TS) → API Gateway
                                               ↓
                              ┌────────────────────────────────┐
                              │        Trust Gateway Core       │
                              │         (FastAPI)               │
                              │                                 │
                              │  1. Auth (Cognito)              │
                              │  2. Intent Extraction (Bedrock) │
                              │  3. Evidence Parsing (Bedrock)  │
                              │  4. Intent ↔ Evidence Compare  │
                              │  5. Risk Assessment             │
                              │  6. Policy Evaluation (Cedar)   │
                              │  7. Authorization Decision       │
                              │  8. Audit Logging (DynamoDB)    │
                              │  9. Mock Payment Simulator      │
                              └────────────────────────────────┘
```

**Full architecture**: see [architecture.md](./architecture.md)
**API contracts & data models**: see [product-spec.md](./product-spec.md)

---

## Tech Stack

### Frontend
- **React 18** + **Vite** + **TypeScript**
- **Zustand** for state management
- **Framer Motion** for animations
- Custom CSS design system (dark mode, glassmorphism)

### Backend
- **Python 3.11** + **FastAPI**
- **Pydantic v2** for data validation
- **Amazon Bedrock** (Claude) for LLM-based extraction
- Deterministic policy engine (Cedar-compatible rules)

### AWS Services
| Service | Purpose |
|---|---|
| S3 | Invoice/evidence storage |
| API Gateway | HTTP entry point |
| Lambda | Serverless service handlers |
| DynamoDB | Audit log + user data |
| Amazon Bedrock | Intent + evidence extraction |
| Cognito | Authentication |
| CloudWatch | Monitoring + metrics |
| Cedar / AgentCore | Policy authorization |

---

## Project Structure

```
AgentPay-Sentinel/
├── architecture.md          # System architecture document
├── product-spec.md          # Product spec, API contracts, data models
├── README.md                # This file
│
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── config.py        # Settings
│   │   ├── models/          # Pydantic data models
│   │   ├── routers/         # API route handlers
│   │   ├── services/        # Business logic services
│   │   ├── policies/        # Deterministic policy rules
│   │   └── utils/           # Helpers (AWS, fuzzy match, crypto)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                # React + Vite + TypeScript frontend
│   ├── src/
│   │   ├── components/      # UI components
│   │   ├── pages/           # App pages
│   │   ├── api/             # API client
│   │   ├── types/           # TypeScript type definitions
│   │   └── stores/          # Zustand state stores
│   ├── package.json
│   └── vite.config.ts
│
├── tests/                   # Test suite
│   ├── unit/                # Policy, risk, comparison unit tests
│   ├── integration/         # End-to-end workflow tests
│   └── fixtures/            # Test data
│
└── docs/                    # Additional documentation
    ├── DECISIONS.md         # Architecture decision records
    └── DEPLOYMENT.md        # AWS deployment guide
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- AWS CLI configured (for full cloud features)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend API: http://localhost:8000
API Docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

---

## Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/session` | Create/validate session |
| `POST` | `/evidence/upload` | Upload invoice document |
| `POST` | `/evidence/extract` | Extract structured evidence |
| `POST` | `/payments/initiate` | Run full trust gateway workflow |
| `POST` | `/payments/{id}/approve` | Human approval for flagged payments |
| `GET` | `/audit/events` | Query audit log |
| `GET` | `/policies/rules` | View active policy rules |

---

## Authorization Decisions

| Decision | Meaning |
|---|---|
| ✅ `ALLOW` | All checks passed — mock payment executed |
| ❌ `DENY` | Policy rules blocked the transaction |
| 👤 `REQUIRE_HUMAN_APPROVAL` | Ambiguous — human must review before proceeding |

---

## Important Disclaimer

> ⚠️ **SANDBOX MODE ONLY**
> 
> AgentPay Sentinel does not connect to any real payment network, UPI system, or banking infrastructure.
> All payment execution is a clearly-labeled sandbox simulation for demonstration purposes only.
> No real money is transferred under any circumstances.

---

## Hackathon Context

**Hackathon**: First Commit  
**Track**: AWS Ship It  
**Team**: AgentPay Sentinel  
**Stage**: MVP Development  
**Focus**: One complete, reliable workflow over many incomplete features

---

## License

MIT — see LICENSE file.
