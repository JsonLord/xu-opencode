from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os

from src.opencode_api.routes import session_router, provider_router, event_router, question_router, agent_router, mcp_router, settings_router
from src.opencode_api.provider import register_provider, AnthropicProvider, OpenAIProvider, LiteLLMProvider, GeminiProvider
from src.opencode_api.tool import register_tool, WebSearchTool, WebFetchTool, TodoTool, QuestionTool, SkillTool
from src.opencode_api.core.config import settings
from src.opencode_api.core.auth import verify_access_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_provider(LiteLLMProvider())
    register_provider(AnthropicProvider())
    register_provider(OpenAIProvider())
    register_provider(GeminiProvider(api_key=settings.google_api_key))
    
    # Register tools
    register_tool(WebSearchTool())
    register_tool(WebFetchTool())
    register_tool(TodoTool())
    register_tool(QuestionTool())
    register_tool(SkillTool())
    
    yield


app = FastAPI(
    title="OpenCode API",
    description="LLM Agent API Server - ported from TypeScript opencode",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS settings for aicampus frontend
ALLOWED_ORIGINS = [
    "https://aicampus.kr",
    "https://www.aicampus.kr",
    "https://aicampus.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__}
    )


app.include_router(session_router, dependencies=[Depends(verify_access_token)])
app.include_router(provider_router, dependencies=[Depends(verify_access_token)])
app.include_router(event_router, dependencies=[Depends(verify_access_token)])
app.include_router(question_router, dependencies=[Depends(verify_access_token)])
app.include_router(agent_router, dependencies=[Depends(verify_access_token)])
app.include_router(mcp_router, dependencies=[Depends(verify_access_token)])
app.include_router(settings_router, dependencies=[Depends(verify_access_token)])


@app.get("/")
async def root():
    return {
        "name": "OpenCode API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api-docs", include_in_schema=False)
async def api_docs():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url=app.openapi_url, title="docs")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
