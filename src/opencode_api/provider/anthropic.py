from typing import Dict, Any, List, Optional, AsyncGenerator
import os
import json

from .provider import BaseProvider, ModelInfo, Message, StreamChunk, ToolCall


MODELS_WITH_EXTENDED_THINKING = {"claude-sonnet-4-20250514", "claude-opus-4-20250514"}


class AnthropicProvider(BaseProvider):
    
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
    
    @property
    def id(self) -> str:
        return "anthropic"
    
    @property
    def name(self) -> str:
        return "Anthropic"
    
    @property
    def models(self) -> Dict[str, ModelInfo]:
        return {
            "claude-sonnet-4-20250514": ModelInfo(
                id="claude-sonnet-4-20250514",
                name="Claude Sonnet 4",
                provider_id="anthropic",
                context_limit=200000,
                output_limit=64000,
                supports_tools=True,
                supports_streaming=True,
                cost_input=3.0,
                cost_output=15.0,
            ),
            "claude-opus-4-20250514": ModelInfo(
                id="claude-opus-4-20250514",
                name="Claude Opus 4",
                provider_id="anthropic",
                context_limit=200000,
                output_limit=32000,
                supports_tools=True,
                supports_streaming=True,
                cost_input=15.0,
                cost_output=75.0,
            ),
            "claude-3-5-haiku-20241022": ModelInfo(
                id="claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku",
                provider_id="anthropic",
                context_limit=200000,
                output_limit=8192,
                supports_tools=True,
                supports_streaming=True,
                cost_input=0.8,
                cost_output=4.0,
            ),
        }
    
    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError("anthropic package is required. Install with: pip install anthropic")
        return self._client
    
    def _supports_extended_thinking(self, model_id: str) -> bool:
        return model_id in MODELS_WITH_EXTENDED_THINKING
    
    async def stream(
        self,
        model_id: str,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        client = self._get_client()
        
        anthropic_messages = []
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                anthropic_messages.append({"role": msg.role, "content": content})
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": [{"type": c.type, "text": c.text} for c in content if c.text]
                })
        
        kwargs: Dict[str, Any] = {
            "model": model_id,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or 16000,
        }
        
        if system:
            kwargs["system"] = system
        
        if temperature is not None:
            kwargs["temperature"] = temperature
        
        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", t.get("input_schema", {}))
                }
                for t in tools
            ]
        
        use_extended_thinking = self._supports_extended_thinking(model_id)
        
        async for chunk in self._stream_with_fallback(client, kwargs, use_extended_thinking):
            yield chunk
    
    async def _stream_with_fallback(
        self, client, kwargs: Dict[str, Any], use_extended_thinking: bool
    ):
        if use_extended_thinking:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 10000
            }
        
        try:
            async for chunk in self._do_stream(client, kwargs):
                yield chunk
        except Exception as e:
            error_str = str(e).lower()
            has_thinking = "thinking" in kwargs
            
            if has_thinking and ("thinking" in error_str or "unsupported" in error_str or "invalid" in error_str):
                del kwargs["thinking"]
                async for chunk in self._do_stream(client, kwargs):
                    yield chunk
            else:
                yield StreamChunk(type="error", error=str(e))
    
    async def _do_stream(self, client, kwargs: Dict[str, Any]):
        current_tool_call = None
        
        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event, "content_block"):
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool_call = {
                                "id": block.id,
                                "name": block.name,
                                "arguments_json": ""
                            }
                
                elif event.type == "content_block_delta":
                    if hasattr(event, "delta"):
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield StreamChunk(type="text", text=delta.text)
                        elif delta.type == "thinking_delta":
                            yield StreamChunk(type="reasoning", text=delta.thinking)
                        elif delta.type == "input_json_delta" and current_tool_call:
                            current_tool_call["arguments_json"] += delta.partial_json
                
                elif event.type == "content_block_stop":
                    if current_tool_call:
                        try:
                            args = json.loads(current_tool_call["arguments_json"]) if current_tool_call["arguments_json"] else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamChunk(
                            type="tool_call",
                            tool_call=ToolCall(
                                id=current_tool_call["id"],
                                name=current_tool_call["name"],
                                arguments=args
                            )
                        )
                        current_tool_call = None
                
                elif event.type == "message_stop":
                    final_message = await stream.get_final_message()
                    usage = {
                        "input_tokens": final_message.usage.input_tokens,
                        "output_tokens": final_message.usage.output_tokens,
                    }
                    stop_reason = self._map_stop_reason(final_message.stop_reason)
                    yield StreamChunk(type="done", usage=usage, stop_reason=stop_reason)
    
    def _map_stop_reason(self, anthropic_stop_reason: Optional[str]) -> str:
        mapping = {
            "end_turn": "end_turn",
            "tool_use": "tool_calls",
            "max_tokens": "max_tokens",
            "stop_sequence": "end_turn",
        }
        return mapping.get(anthropic_stop_reason or "", "end_turn")
