from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from jose import jwt
from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)
settings = get_settings()

TOKEN_EXPIRE_HOURS = 24
ALGORITHM = "HS256"


class TokenRequest(BaseModel):
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = TOKEN_EXPIRE_HOURS * 3600


def create_access_token(tenant_id: str) -> str:
    payload = {
        "sub": tenant_id,
        "tenant_id": tenant_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


@router.post("/token", response_model=TokenResponse)
async def exchange_token(req: TokenRequest):
    """
    Exchange a valid API key for a short-lived JWT.
    The API key never leaves the server after this call.
    The frontend stores and sends the JWT; the raw key is not embedded in the bundle.
    """
    if req.api_key != settings.api_key:
        logger.warning("auth_failed_invalid_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    import hashlib
    tenant_id = hashlib.sha256(req.api_key.encode()).hexdigest()[:16]
    token = create_access_token(tenant_id)
    logger.info("token_issued", tenant_id=tenant_id)
    return TokenResponse(access_token=token)
