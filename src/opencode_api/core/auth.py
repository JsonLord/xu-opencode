from typing import Optional
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError

from .config import settings
from .supabase import get_client, is_enabled as supabase_enabled


security = HTTPBearer(auto_error=False)


class AuthUser(BaseModel):
    id: str
    email: Optional[str] = None
    role: Optional[str] = None


def decode_supabase_jwt(token: str) -> Optional[dict]:
    if not settings.supabase_jwt_secret:
        return None
    
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthUser]:
    if not supabase_enabled():
        return None
    
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = decode_supabase_jwt(token)
    
    if not payload:
        return None
    
    return AuthUser(
        id=payload.get("sub"),
        email=payload.get("email"),
        role=payload.get("role")
    )


async def require_auth(
    user: Optional[AuthUser] = Depends(get_current_user)
) -> AuthUser:
    if not supabase_enabled():
        raise HTTPException(status_code=503, detail="Authentication not configured")
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")
    
    return user


async def optional_auth(
    user: Optional[AuthUser] = Depends(get_current_user)
) -> Optional[AuthUser]:
    return user
