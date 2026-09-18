# AgentPay Sentinel — Deployment Guide

> **Phase 3.1 — AWS Foundation**
> Region: `ap-south-1` (Mumbai)
> Deployment tooling: AWS SAM CLI

---

## Architecture (What Gets Deployed)

```
   React SPA (Vite)                   Developer machine / localhost
          │ HTTPS
          ▼
   API Gateway (HTTP API)             AWS ap-south-1
          │ Lambda proxy
          ▼
   Lambda Function                    Python 3.12, 512MB, 30s timeout
   (sentinel-trust-gateway-production)
   Mangum → FastAPI → all services
          │         │         │
          ▼         ▼         ▼
   S3 (evidence) DynamoDB   CloudWatch
   private       sentinel-  /aws/lambda/...
   SSE-AES256    audit +    structured JSON
                 sessions   logs
```

**Key design decisions:**
- Single Lambda wraps the entire FastAPI application (not one Lambda per endpoint)
- Two DynamoDB tables: `sentinel-audit` (append-only) + `sentinel-sessions` (sessions + payee history + evidence metadata)
- S3 bucket is private — no presigned URLs — backend streams all file operations
- IAM role has exactly the permissions needed — no wildcards on resources

---

## Prerequisites

### Local Development (no AWS needed)

```powershell
# Python 3.12 required
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt  # includes pytest + moto (dev only)

# Run the local server
uvicorn app.main:app --reload

# Run all tests (including AWS adapter tests with moto)
python -m pytest ..\tests -v
```

### AWS Deployment

Install AWS tooling:

```powershell
# AWS CLI
# https://aws.amazon.com/cli/

# AWS SAM CLI
pip install aws-sam-cli
# or: winget install Amazon.SAM-CLI

# Verify
aws --version
sam --version
```

Configure AWS credentials:

```powershell
aws configure
# Region: ap-south-1
# Output: json
```

### Enable Bedrock Model Access (Required for Phase 3.2)

Bedrock models require explicit opt-in before they can be invoked.

1. Open [Bedrock → Model access](https://ap-south-1.console.aws.amazon.com/bedrock/home?region=ap-south-1#/modelaccess) in the AWS console
2. Click **Manage model access**
3. Enable: **Anthropic Claude 3.5 Sonnet v2** (model ID: `anthropic.claude-3-5-sonnet-20241022-v2:0`)
4. Submit request — approval is usually instant for Anthropic models

> **Note**: If Claude 3.5 Sonnet v2 is unavailable in `ap-south-1`, fall back to `anthropic.claude-3-sonnet-20240229-v1:0` by setting `BEDROCK_MODEL_ID` in the Lambda environment.

---

## Local Mode (Default)

Local mode uses in-memory adapters — no AWS credentials required.

```ini
# backend/.env (copy from .env.example)
ENVIRONMENT=local
USE_LOCAL_ADAPTERS=True
```

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

The frontend at `http://localhost:5173` (or `npm run dev`) points at this server by default.

---

## AWS Deployment (Phase 3.1)

> **IMPORTANT**: These commands create real AWS resources.
> Do NOT run them automatically. Proceed manually and deliberately.
> `sam deploy --guided` will prompt for confirmation before any resource is created.

### Step 1 — Install Lambda dependencies

```powershell
# From the repo root
pip install mangum -t backend/  # SAM picks up the backend/ directory
```

Actually, SAM handles dependency installation automatically during `sam build`:

```powershell
sam build
```

This creates `.aws-sam/build/SentinelFunction/` with all production dependencies from `backend/requirements.txt`. **`requirements-dev.txt` is NOT included in the build** — moto stays off Lambda.

### Step 2 — Validate the template

```powershell
sam validate --template template.yaml --lint
```

Expected output: `template.yaml is a valid SAM Template`

### Step 3 — First deployment (interactive)

```powershell
sam deploy --guided --region ap-south-1
```

You will be prompted for:
- **Stack name**: `agentpay-sentinel`
- **AWS Region**: `ap-south-1`
- **Environment**: `production`
- **ApiKeySalt**: Enter a strong random value (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
- **AllowedOrigins**: `http://localhost:5173` (update later to your frontend URL)
- **Confirm changeset**: `y`

This creates a `samconfig.toml` with your answers for subsequent deploys.

### Step 4 — Subsequent deploys

```powershell
sam deploy
# Prompts: "Confirm changeset: y"
```

### Step 5 — Note the API Gateway URL

After successful deployment, SAM prints the stack outputs:

```
Outputs:
  ApiBaseUrl = https://XXXX.execute-api.ap-south-1.amazonaws.com
  EvidenceBucketName = sentinel-evidence-{account_id}-ap-south-1
  AuditTableName = sentinel-audit
  SessionsTableName = sentinel-sessions
```

### Step 6 — Seed Demo Users (AWS mode only)

The DynamoDB adapter falls back to in-memory demo users if the DynamoDB items are missing. For a persistent hackathon demo without fallback dependency, seed them manually:

```python
# Run this once after first deployment
# From backend/ with AWS credentials active

import boto3
from app.adapters.dynamo import _DEMO_USERS, _API_KEYS

ddb = boto3.resource("dynamodb", region_name="ap-south-1")
table = ddb.Table("sentinel-sessions")

# Seed users
for user_id, user_data in _DEMO_USERS.items():
    table.put_item(Item={"pk": f"USER#{user_id}", "sk": f"USER#{user_id}", **user_data})

# Seed API key → user_id mappings
for api_key, user_id in _API_KEYS.items():
    table.put_item(Item={"pk": f"APIKEY#{api_key}", "sk": f"APIKEY#{api_key}", "user_id": user_id})

print("Seeded demo users into DynamoDB.")
```

### Step 7 — Update Frontend

Point the frontend at the deployed API Gateway:

```powershell
# frontend/.env
# (Or set at build time)
VITE_API_BASE_URL=https://XXXX.execute-api.ap-south-1.amazonaws.com
```

```powershell
cd frontend
npm run build
# dist/ is ready for S3 static hosting or local serve
```

---

## Validation Checklist (Post-Deploy)

```powershell
# Set your API Gateway URL
$API = "https://XXXX.execute-api.ap-south-1.amazonaws.com"

# 1. Health check
Invoke-WebRequest -Uri "$API/health" | Select-Object -ExpandProperty Content
# Expected: {"status":"ok","adapter_mode":"aws",...}

# 2. Auth
$token_resp = Invoke-WebRequest -Uri "$API/auth/session" -Method POST `
  -ContentType "application/json" `
  -Body '{"user_id":"usr_standard","api_key":"sk-dev-standard"}'
$token = ($token_resp.Content | ConvertFrom-Json).token

# 3. Payment evaluation (happy path)
Invoke-WebRequest -Uri "$API/payments/evaluate" -Method POST `
  -ContentType "application/json" `
  -Headers @{Authorization="Bearer $token"} `
  -Body '{"raw_input":"Pay 1850 to ABC Hardware."}'
# Expected: decision=ALLOW (without evidence — small amount may vary)

# 4. Audit chain verification
Invoke-WebRequest -Uri "$API/audit/verify" `
  -Headers @{Authorization="Bearer $token"}
# Expected: {"chain_valid":true,...}

# 5. Check S3 (after an evidence upload)
aws s3 ls s3://sentinel-evidence-{account_id}-ap-south-1/evidence/

# 6. Check DynamoDB audit events
aws dynamodb scan --table-name sentinel-audit --region ap-south-1
```

---

## CloudWatch Logging

Logs are at:
- Lambda: `/aws/lambda/sentinel-trust-gateway-production`
- API Gateway: `/aws/apigateway/sentinel-api-production`

Key log fields emitted for every authorization decision:
```json
{
  "event": "authorization_decision",
  "decision": "ALLOW",
  "matched_rule": "allow_full_match",
  "amount_band_inr": "1001-5000",
  "evidence_present": true,
  "payee_seen_before": false
}
```

Note: no exact amounts, no payee names, no credentials are logged.

---

## Teardown

To delete all deployed resources (stack, S3 bucket, DynamoDB tables, Lambda, API GW):

```powershell
# CAUTION: this permanently deletes all audit events and evidence files
sam delete --stack-name agentpay-sentinel --region ap-south-1
```

You may need to manually empty the S3 bucket first (versioned buckets cannot be auto-deleted):

```powershell
aws s3 rm s3://sentinel-evidence-{account_id}-ap-south-1 --recursive
```

---

## Cost Estimate (Free Tier / Hackathon Usage)

| Service | Free Tier | Estimated Usage |
|---|---|---|
| Lambda | 1M requests/month free | ~1,000 requests → $0.00 |
| API Gateway (HTTP) | 1M requests/month free | ~1,000 requests → $0.00 |
| DynamoDB | 25 GB + 200M requests/month free | < 1 MB → $0.00 |
| S3 | 5 GB + 20K GET free | < 10 files → $0.00 |
| CloudWatch | 5 GB logs free | < 1 MB → $0.00 |

**Estimated demo cost: $0.00** (well within free tier)

---

## Phase Roadmap

| Phase | Status | Description |
|---|---|---|
| **Phase 3.1** | ✅ Complete | AWS Foundation (API GW + Lambda + S3 + DynamoDB + CloudWatch) |
| **Phase 3.2** | ✅ Complete | Bedrock integration (Claude 3.5 Sonnet — real intent + evidence extraction) |
| **Phase 3.3** | Planned | AgentCore Gateway + Human approval loop |
