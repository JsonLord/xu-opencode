from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from ..session import Session, SessionInfo, SessionCreate, Message, SessionPrompt
from ..session.prompt import PromptInput
from ..core.storage import NotFoundError
from ..core.auth import AuthUser, optional_auth, require_auth
from ..core.quota import check_quota, increment_usage
from ..core.supabase import is_enabled as supabase_enabled
from ..provider import get_provider


router = APIRouter(prefix="/session", tags=["Session"])


class MessageRequest(BaseModel):
    content: str
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    system: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools_enabled: bool = True
    auto_continue: Optional[bool] = None
    max_steps: Optional[int] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = None


class GenerateTitleRequest(BaseModel):
    message: str
    model_id: Optional[str] = None


@router.get("/", response_model=List[SessionInfo])
async def list_sessions(
    limit: Optional[int] = Query(None, description="Maximum number of sessions to return"),
    user: Optional[AuthUser] = Depends(optional_auth)
):
    user_id = user.id if user else None
    return await Session.list(limit, user_id)


@router.post("/", response_model=SessionInfo)
async def create_session(
    data: Optional[SessionCreate] = None,
    user: Optional[AuthUser] = Depends(optional_auth)
):
    user_id = user.id if user else None
    return await Session.create(data, user_id)


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    user: Optional[AuthUser] = Depends(optional_auth)
):
    try:
        user_id = user.id if user else None
        return await Session.get(session_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.patch("/{session_id}", response_model=SessionInfo)
async def update_session(
    session_id: str,
    updates: SessionUpdate,
    user: Optional[AuthUser] = Depends(optional_auth)
):
    try:
        user_id = user.id if user else None
        update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
        return await Session.update(session_id, update_dict, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: Optional[AuthUser] = Depends(optional_auth)
):
    try:
        user_id = user.id if user else None
        await Session.delete(session_id, user_id)
        return {"success": True}
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.get("/{session_id}/message")
async def list_messages(
    session_id: str,
    limit: Optional[int] = Query(None, description="Maximum number of messages to return"),
    user: Optional[AuthUser] = Depends(optional_auth)
):
    try:
        user_id = user.id if user else None
        await Session.get(session_id, user_id)
        return await Message.list(session_id, limit, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.post("/{session_id}/message")
async def send_message(
    session_id: str,
    request: MessageRequest,
    user: AuthUser = Depends(check_quota) if supabase_enabled() else Depends(optional_auth)
):
    user_id = user.id if user else None
    
    try:
        await Session.get(session_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    
    prompt_input = PromptInput(
        content=request.content,
        provider_id=request.provider_id,
        model_id=request.model_id,
        system=request.system,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        tools_enabled=request.tools_enabled,
        auto_continue=request.auto_continue,
        max_steps=request.max_steps,
    )
    
    async def generate():
        total_input = 0
        total_output = 0
        
        async for chunk in SessionPrompt.prompt(session_id, prompt_input, user_id):
            if chunk.usage:
                total_input += chunk.usage.get("input_tokens", 0)
                total_output += chunk.usage.get("output_tokens", 0)
            yield f"data: {json.dumps(chunk.model_dump())}\n\n"
        
        if user_id and supabase_enabled():
            await increment_usage(user_id, total_input, total_output)
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/{session_id}/abort")
async def abort_session(session_id: str):
    cancelled = SessionPrompt.cancel(session_id)
    return {"cancelled": cancelled}


@router.post("/{session_id}/generate-title")
async def generate_title(
    session_id: str,
    request: GenerateTitleRequest,
    user: Optional[AuthUser] = Depends(optional_auth)
):
    """첫 메시지 기반으로 세션 제목 생성"""
    user_id = user.id if user else None

    # 세션 존재 확인
    try:
        await Session.get(session_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    # LiteLLM Provider로 제목 생성
    model_id = request.model_id or "gemini/gemini-2.0-flash"
    provider = get_provider("litellm")

    if not provider:
        raise HTTPException(status_code=503, detail="LiteLLM provider not available")

    prompt = f"""다음 사용자 메시지를 보고 짧은 제목을 생성해주세요.
제목은 10자 이내, 따옴표 없이 제목만 출력.

사용자 메시지: "{request.message[:200]}"

제목:"""

    try:
        result = await provider.complete(model_id, prompt, max_tokens=50)
        title = result.strip()[:30]

        # 세션 제목 업데이트
        await Session.update(session_id, {"title": title}, user_id)

        return {"title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate title: {str(e)}")
