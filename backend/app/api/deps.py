from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.db.session import get_db

settings = get_settings()


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return x_api_key


def get_tenant_id(x_api_key: str = Depends(verify_api_key)) -> str:
    """
    In a real multi-tenant system this would decode a JWT and return the org ID.
    For this demo we derive the tenant from the API key (single-tenant mode).
    """
    import hashlib
    return hashlib.sha256(x_api_key.encode()).hexdigest()[:16]
