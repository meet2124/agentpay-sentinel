"""
AgentPay Sentinel — AWS Lambda Entry Point

Wraps the existing FastAPI application with Mangum so that API Gateway
can invoke it as a standard Lambda function.

Architecture:
    API Gateway (HTTP API)
          ↓ Lambda Proxy integration
    Mangum (ASGI ↔ Lambda event/context adapter)
          ↓
    FastAPI application (app/main.py)
          ↓
    Existing routers, services, adapters

No routers are rewritten. No API contracts change.
The adapter_mode in /health will report "aws" when USE_LOCAL_ADAPTERS=False.

Lambda configuration (set via SAM template / environment variables):
    USE_LOCAL_ADAPTERS=False
    AWS_REGION=ap-south-1
    S3_BUCKET_NAME=<bucket-name>
    DYNAMODB_TABLE_AUDIT=sentinel-audit
    DYNAMODB_TABLE_SESSIONS=sentinel-sessions
    ENVIRONMENT=production
"""

from __future__ import annotations

from mangum import Mangum

from app.main import app

# lifespan="off" — FastAPI startup/shutdown events are not used.
# api_gateway_base_path is derived from LAMBDA_STAGE env var at runtime
# via the FastAPI app's root_path (Mangum handles this automatically for HTTP APIs).
handler = Mangum(app, lifespan="off")
