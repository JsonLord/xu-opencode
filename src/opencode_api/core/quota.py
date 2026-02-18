from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel

from .auth import AuthUser, require_auth
from .supabase import get_client, is_enabled as supabase_enabled
from .config import settings


class UsageInfo(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0


class QuotaLimits(BaseModel):
    daily_requests: int = 100
    daily_input_tokens: int = 1_000_000
    daily_output_tokens: int = 500_000


DEFAULT_LIMITS = QuotaLimits()


async def get_usage(user_id: str) -> UsageInfo:
    if not supabase_enabled():
        return UsageInfo()
    
    client = get_client()
    result = client.rpc("get_opencode_usage", {"p_user_id": user_id}).execute()
    
    if result.data and len(result.data) > 0:
        row = result.data[0]
        return UsageInfo(
            input_tokens=row.get("input_tokens", 0),
            output_tokens=row.get("output_tokens", 0),
            request_count=row.get("request_count", 0),
        )
    return UsageInfo()


async def increment_usage(user_id: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
    if not supabase_enabled():
        return
    
    client = get_client()
    client.rpc("increment_opencode_usage", {
        "p_user_id": user_id,
        "p_input_tokens": input_tokens,
        "p_output_tokens": output_tokens,
    }).execute()


async def check_quota(user: AuthUser = Depends(require_auth)) -> AuthUser:
    if not supabase_enabled():
        return user
    
    usage = await get_usage(user.id)
    limits = DEFAULT_LIMITS
    
    if usage.request_count >= limits.daily_requests:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Daily request limit reached",
                "usage": usage.model_dump(),
                "limits": limits.model_dump(),
            }
        )
    
    if usage.input_tokens >= limits.daily_input_tokens:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Daily input token limit reached",
                "usage": usage.model_dump(),
                "limits": limits.model_dump(),
            }
        )
    
    if usage.output_tokens >= limits.daily_output_tokens:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Daily output token limit reached",
                "usage": usage.model_dump(),
                "limits": limits.model_dump(),
            }
        )
    
    return user
