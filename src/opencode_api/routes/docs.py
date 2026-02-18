from fastapi import APIRouter
from typing import List, Dict, Any
from ..core.config import settings

router = APIRouter(prefix="/docs", tags=["Documentation"])

def get_api_info():
    token = settings.token or "ACCESS2026"
    return {
    "title": "OpenCode API Documentation",
    "description": "Human-readable summary of available endpoints, their jobs, and how to interact with them.",
    "auth": {
        "type": "Bearer Token",
        "header": f"Authorization: Bearer {token}",
        "description": "Most endpoints require this token for access."
    },
    "endpoints": [
        {
            "path": "/health",
            "method": "GET",
            "job": "Check system health and status.",
            "interaction": "Send a GET request. No auth required.",
            "example": "curl https://auxteam-opencode-api.hf.space/health"
        },
        {
            "path": "/provider",
            "method": "GET",
            "job": "List available LLM providers (e.g., blablador, openai, anthropic).",
            "interaction": "Send GET request with Bearer token.",
            "example": f"curl -H 'Authorization: Bearer {token}' https://auxteam-opencode-api.hf.space/provider"
        },
        {
            "path": "/session",
            "method": "POST",
            "job": "Create a new chat session.",
            "interaction": "Send POST request. Optional JSON body: {'title': 'My Session', 'model_id': 'alias-large'}.",
            "example": f"curl -X POST -H 'Authorization: Bearer {token}' https://auxteam-opencode-api.hf.space/session"
        },
        {
            "path": "/session",
            "method": "GET",
            "job": "List all active chat sessions.",
            "interaction": "Send GET request with Bearer token.",
            "example": f"curl -H 'Authorization: Bearer {token}' https://auxteam-opencode-api.hf.space/session"
        },
        {
            "path": "/session/{session_id}/message",
            "method": "POST",
            "job": "Send a message to the agent and receive a streaming response.",
            "interaction": "Send POST request with JSON body. Returns Server-Sent Events (SSE).",
            "payload": {
                "content": "Message string (required)",
                "model_id": "Optional model ID (defaults to alias-large)",
                "system": "Optional system prompt override"
            },
            "example": f"curl -X POST -H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' -d '{{\"content\": \"Hi\"}}' https://auxteam-opencode-api.hf.space/session/{{id}}/message"
        },
        {
            "path": "/session/{session_id}/abort",
            "method": "POST",
            "job": "Cancel an ongoing message generation.",
            "interaction": "Send POST request with Bearer token.",
            "example": f"curl -X POST -H 'Authorization: Bearer {token}' https://auxteam-opencode-api.hf.space/session/{{id}}/abort"
        },
        {
            "path": "/question",
            "method": "GET",
            "job": "List questions waiting for user input (used by QuestionTool).",
            "interaction": "Send GET request. Returns list of pending question requests.",
            "example": f"curl -H 'Authorization: Bearer {token}' https://auxteam-opencode-api.hf.space/question"
        },
        {
            "path": "/question/{request_id}/reply",
            "method": "POST",
            "job": "Answer a pending question from the agent.",
            "interaction": "Send POST request with JSON body: {'answers': [['Label1'], ['Label2']]}.",
            "example": f"curl -X POST -H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' -d '{{\"answers\": [[\"Yes\"]]}}' https://auxteam-opencode-api.hf.space/question/{{id}}/reply"
        },
        {
            "path": "/agent",
            "method": "GET",
            "job": "List available agent configurations.",
            "interaction": "Send GET request.",
            "example": f"curl -H 'Authorization: Bearer {token}' https://auxteam-opencode-api.hf.space/agent"
        }
    ]
}

@router.get("")
@router.get("/")
async def get_api_docs():
    """Return a human-readable summary of the API."""
    return get_api_info()
