"""Authentication API routes for API key management."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.common import SuccessResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


class APIKeyCreate(BaseModel):
    """API key creation request."""

    name: str = Field(..., min_length=1, max_length=100, description="Key name/description")
    scopes: List[str] = Field(default=["read"], description="Permission scopes")
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000, description="Rate limit")
    expires_in_days: Optional[int] = Field(None, description="Days until expiration")


class APIKeyResponse(BaseModel):
    """API key response (without the actual key for security)."""

    id: int = Field(..., description="Key ID")
    name: str = Field(..., description="Key name")
    scopes: List[str] = Field(..., description="Permission scopes")
    rate_limit_per_minute: int = Field(..., description="Rate limit")
    is_active: bool = Field(..., description="Is key active")
    expires_at: Optional[datetime] = Field(None, description="Expiration time")
    created_at: datetime = Field(..., description="Created timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last used timestamp")


class APIKeyCreated(APIKeyResponse):
    """API key created response (includes the key - only shown once)."""

    key: str = Field(..., description="The API key (only shown once)")


@router.get("/keys")
async def list_api_keys(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
) -> List[APIKeyResponse]:
    """List all API keys (admin only)."""
    # TODO: Implement when APIKey model is added
    # For now, return empty list
    return []


@router.post("/keys")
async def create_api_key(
    key_data: APIKeyCreate,
    db: Session = Depends(get_db),
) -> APIKeyCreated:
    """Create a new API key (admin only)."""
    import secrets
    import hashlib
    from datetime import timedelta

    # Generate key
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # Calculate expiration
    expires_at = None
    if key_data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)

    # TODO: Store in database when APIKey model is added
    # For now, return mock response

    return APIKeyCreated(
        id=1,
        name=key_data.name,
        scopes=key_data.scopes,
        rate_limit_per_minute=key_data.rate_limit_per_minute,
        is_active=True,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
        last_used_at=None,
        key=f"sk_{raw_key}",  # Prefix for identification
    )


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
) -> SuccessResponse:
    """Revoke an API key (admin only)."""
    # TODO: Implement when APIKey model is added
    return SuccessResponse(message=f"API key {key_id} revoked")


@router.post("/keys/{key_id}/regenerate")
async def regenerate_api_key(
    key_id: int,
    db: Session = Depends(get_db),
) -> APIKeyCreated:
    """Regenerate an API key (admin only)."""
    import secrets

    # Generate new key
    raw_key = secrets.token_urlsafe(32)

    # TODO: Update in database when APIKey model is added
    return APIKeyCreated(
        id=key_id,
        name="Regenerated Key",
        scopes=["read"],
        rate_limit_per_minute=60,
        is_active=True,
        expires_at=None,
        created_at=datetime.utcnow(),
        last_used_at=None,
        key=f"sk_{raw_key}",
    )
