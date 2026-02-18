from typing import List, Dict
from fastapi import APIRouter, HTTPException
import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

from ..provider import list_providers, get_provider
from ..provider.provider import ProviderInfo, ModelInfo


router = APIRouter(prefix="/provider", tags=["Provider"])


# Provider별 필요 환경변수 매핑
PROVIDER_API_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "litellm": None,  # LiteLLM은 개별 모델별로 체크
}

# LiteLLM 모델별 필요 환경변수
LITELLM_MODEL_KEYS = {
    "claude-": "ANTHROPIC_API_KEY",
    "gpt-": "OPENAI_API_KEY",
    "o1": "OPENAI_API_KEY",
    "gemini/": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "groq/": "GROQ_API_KEY",
    "deepseek/": "DEEPSEEK_API_KEY",
    "openrouter/": "OPENROUTER_API_KEY",
    "zai/": "ZAI_API_KEY",
}


def has_api_key(provider_id: str) -> bool:
    """Check if provider has required API key configured"""
    keys = PROVIDER_API_KEYS.get(provider_id)
    if keys is None:
        return True  # No key required (like litellm container)
    if isinstance(keys, list):
        return any(os.environ.get(k) for k in keys)
    return bool(os.environ.get(keys))


def filter_litellm_models(models: Dict[str, ModelInfo]) -> Dict[str, ModelInfo]:
    """Filter LiteLLM models based on available API keys"""
    filtered = {}
    for model_id, model_info in models.items():
        for prefix, env_key in LITELLM_MODEL_KEYS.items():
            if model_id.startswith(prefix):
                if isinstance(env_key, list):
                    if any(os.environ.get(k) for k in env_key):
                        filtered[model_id] = model_info
                elif os.environ.get(env_key):
                    filtered[model_id] = model_info
                break
    return filtered


@router.get("/", response_model=List[ProviderInfo])
async def get_providers():
    """Get available providers (filtered by API key availability)"""
    all_providers = list_providers()
    available = []

    for provider in all_providers:
        if provider.id == "litellm":
            # LiteLLM: 개별 모델별 필터링
            filtered_models = filter_litellm_models(provider.models)
            if filtered_models:
                provider.models = filtered_models
                available.append(provider)
        elif has_api_key(provider.id):
            available.append(provider)

    return available


@router.get("/{provider_id}", response_model=ProviderInfo)
async def get_provider_info(provider_id: str):
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    return provider.get_info()


@router.get("/{provider_id}/model", response_model=List[ModelInfo])
async def get_provider_models(provider_id: str):
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
    return list(provider.models.values())


@router.get("/{provider_id}/model/{model_id}", response_model=ModelInfo)
async def get_model_info(provider_id: str, model_id: str):
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    model = provider.models.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")

    return model
