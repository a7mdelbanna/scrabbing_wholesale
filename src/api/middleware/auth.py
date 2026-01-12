"""API key authentication middleware."""
import hashlib
from datetime import datetime
from typing import Optional, List

from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.models.database import APIKey

# API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIKeyAuth:
    """API key authentication handler."""

    def __init__(self, required_scopes: Optional[List[str]] = None):
        self.required_scopes = required_scopes or []

    async def __call__(
        self,
        request: Request,
        api_key: Optional[str] = Depends(api_key_header),
        db: Session = Depends(get_db),
    ) -> Optional[APIKey]:
        """Validate API key and return the key record."""
        # Allow unauthenticated access to certain endpoints
        if not api_key:
            # Check if endpoint requires auth
            if self.required_scopes:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "AUTHENTICATION_ERROR",
                        "message": "Missing API key. Include X-API-Key header.",
                    },
                )
            return None

        # Hash the key for lookup
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Look up the key
        key_record = (
            db.query(APIKey)
            .filter(APIKey.key_hash == key_hash)
            .first()
        )

        if not key_record:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "AUTHENTICATION_ERROR",
                    "message": "Invalid API key.",
                },
            )

        # Check if key is active
        if not key_record.is_active:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "AUTHENTICATION_ERROR",
                    "message": "API key has been revoked.",
                },
            )

        # Check expiration
        if key_record.expires_at and key_record.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "AUTHENTICATION_ERROR",
                    "message": "API key has expired.",
                },
            )

        # Check scopes
        if self.required_scopes:
            key_scopes = set(key_record.scopes or [])
            # Admin scope has access to everything
            if "admin" not in key_scopes:
                for scope in self.required_scopes:
                    if scope not in key_scopes:
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "code": "AUTHORIZATION_ERROR",
                                "message": f"Missing required scope: {scope}",
                            },
                        )

        # Update last used timestamp
        key_record.last_used_at = datetime.utcnow()
        db.commit()

        # Store key info in request state for rate limiting
        request.state.api_key = key_record

        return key_record


# Dependency instances for different access levels
require_read = APIKeyAuth(required_scopes=["read"])
require_write = APIKeyAuth(required_scopes=["write"])
require_admin = APIKeyAuth(required_scopes=["admin"])
optional_auth = APIKeyAuth(required_scopes=[])


def get_current_api_key(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> Optional[APIKey]:
    """Get current API key from request (optional auth)."""
    if not api_key:
        return None

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
