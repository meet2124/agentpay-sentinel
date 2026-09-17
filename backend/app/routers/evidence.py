"""
AgentPay Sentinel — Router: Evidence

POST /evidence/upload   — upload an invoice/receipt file and extract evidence
GET  /evidence/{id}     — retrieve extracted evidence by ID
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from ..dependencies import get_current_user, get_evidence_service
from ..models.evidence import Evidence
from ..models.user import User
from ..services.evidence_service import EvidenceService

router = APIRouter(prefix="/evidence", tags=["Evidence"])


@router.post(
    "/upload",
    response_model=Evidence,
    summary="Upload and extract evidence",
    description=(
        "Upload an invoice or receipt (PDF, JPEG, PNG). "
        "The file is stored and evidence is extracted server-side. "
        "Clients cannot inject pre-parsed evidence data. "
        "Returns the extracted Evidence object including extraction confidence."
    ),
)
async def upload_evidence(
    file: Annotated[UploadFile, File(description="Invoice PDF or image")],
    current_user: Annotated[User, Depends(get_current_user)],
    evidence_svc: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    return await evidence_svc.upload_and_extract(
        file=file,
        user_id=current_user.user_id,
    )


@router.get(
    "/{evidence_id}",
    response_model=Evidence,
    summary="Get evidence by ID",
)
async def get_evidence(
    evidence_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    evidence_svc: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    evidence = await evidence_svc.get_evidence(evidence_id)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' not found.",
        )
    if evidence.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this evidence.",
        )
    return evidence
