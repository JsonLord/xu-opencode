from typing import Dict, Any, List, Optional, AsyncGenerator
import os
import json

from .provider import ModelInfo, Message, StreamChunk, ToolCall
from .openai import OpenAIProvider


class BlabladorProvider(OpenAIProvider):

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key=api_key or os.environ.get("BLABLADOR_API_KEY"))
        self._base_url = "https://api.helmholtz-blablador.fz-juelich.de/v1"

    @property
    def id(self) -> str:
        return "blablador"

    @property
    def name(self) -> str:
        return "Blablador"

    @property
    def models(self) -> Dict[str, ModelInfo]:
        return {
            "alias-large": ModelInfo(
                id="alias-large",
                name="Blablador Large",
                provider_id="blablador",
                context_limit=32768,
                output_limit=4096,
                supports_tools=True,
                supports_streaming=True,
                cost_input=0.0,
                cost_output=0.0,
            ),
            "alias-fast": ModelInfo(
                id="alias-fast",
                name="Blablador Fast",
                provider_id="blablador",
                context_limit=8192,
                output_limit=2048,
                supports_tools=True,
                supports_streaming=True,
                cost_input=0.0,
                cost_output=0.0,
            ),
        }

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
            except ImportError:
                raise ImportError("openai package is required. Install with: pip install openai")
        return self._client
