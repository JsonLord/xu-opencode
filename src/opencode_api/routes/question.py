"""Question API routes."""
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..tool import (
    reply_to_question, 
    reject_question, 
    get_pending_questions,
    QuestionReply,
)


router = APIRouter(prefix="/question", tags=["question"])


class QuestionAnswerRequest(BaseModel):
    """Request to answer a question."""
    answers: List[List[str]] = Field(..., description="Answers in order (each is array of selected labels)")


@router.get("")
@router.get("/")
async def list_pending_questions(session_id: str = None):
    """List all pending questions."""
    pending = get_pending_questions(session_id)
    return {"pending": pending}


@router.post("/{request_id}/reply")
async def answer_question(request_id: str, request: QuestionAnswerRequest):
    """Submit answers to a pending question."""
    success = await reply_to_question(request_id, request.answers)
    
    if not success:
        raise HTTPException(
            status_code=404, 
            detail=f"Question request '{request_id}' not found or already answered"
        )
    
    return {"status": "answered", "request_id": request_id}


@router.post("/{request_id}/reject")
async def dismiss_question(request_id: str):
    """Dismiss/reject a pending question without answering."""
    success = await reject_question(request_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Question request '{request_id}' not found or already handled"
        )
    
    return {"status": "rejected", "request_id": request_id}
