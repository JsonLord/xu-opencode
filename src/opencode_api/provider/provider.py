from typing import Dict, Any, List, Optional, AsyncIterator, AsyncGenerator, Protocol, runtime_checkable
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod


class ModelInfo(BaseModel):
    id: str
    name: str
    provider_id: str
    context_limit: int = 128000
    output_limit: int = 8192
    supports_tools: bool = True
    supports_streaming: bool = True
    cost_input: float = 0.0  # per 1M tokens
    cost_output: float = 0.0  # per 1M tokens


class ProviderInfo(BaseModel):
    id: str
    name: str
    models: Dict[str, ModelInfo] = Field(default_factory=dict)


class MessageContent(BaseModel):
    type: str = "text"
    text: Optional[str] = None
    
    
class Message(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str | List[MessageContent]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class ToolResult(BaseModel):
    tool_call_id: str
    output: str


class StreamChunk(BaseModel):
    type: str  # "text", "reasoning", "tool_call", "tool_result", "done", "error"
    text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    stop_reason: Optional[str] = None  # "end_turn", "tool_calls", "max_tokens", etc.


@runtime_checkable
class Provider(Protocol):
    
    @property
    def id(self) -> str: ...
    
    @property
    def name(self) -> str: ...
    
    @property
    def models(self) -> Dict[str, ModelInfo]: ...
    
    def stream(
        self,
        model_id: str,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]: ...


class BaseProvider(ABC):
    
    @property
    @abstractmethod
    def id(self) -> str:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def models(self) -> Dict[str, ModelInfo]:
        pass
    
    @abstractmethod
    def stream(
        self,
        model_id: str,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        pass
    
    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            name=self.name,
            models=self.models
        )


_providers: Dict[str, BaseProvider] = {}


def register_provider(provider: BaseProvider) -> None:
    _providers[provider.id] = provider


def get_provider(provider_id: str) -> Optional[BaseProvider]:
    return _providers.get(provider_id)


def list_providers() -> List[ProviderInfo]:
    return [p.get_info() for p in _providers.values()]


def get_model(provider_id: str, model_id: str) -> Optional[ModelInfo]:
    provider = get_provider(provider_id)
    if provider:
        return provider.models.get(model_id)
    return None
