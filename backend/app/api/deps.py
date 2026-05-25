from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db

settings = get_settings()
logger = get_logger(__name__)

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


def _decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as e:
        logger.warning("jwt_decode_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. POST /api/v1/auth/token to get a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Validate Bearer JWT and return decoded claims.
    The raw API key never travels over the wire after the initial /auth/token exchange.
    Tenant ID is embedded in signed JWT claims, not derived client-side.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing. POST /api/v1/auth/token first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_jwt(credentials.credentials)


def get_tenant_id(claims: dict = Depends(get_current_claims)) -> str:
    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="tenant_id missing from token")
    return tenant_id


# Backward-compatible alias used across routes
verify_token = get_current_claims
