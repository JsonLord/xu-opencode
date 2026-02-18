from typing import Dict, Any, List, Optional, AsyncGenerator
import os
import json

from .provider import BaseProvider, ModelInfo, Message, StreamChunk, ToolCall


class OpenAIProvider(BaseProvider):
    
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = None
    
    @property
    def id(self) -> str:
        return "openai"
    
    @property
    def name(self) -> str:
        return "OpenAI"
    
    @property
    def models(self) -> Dict[str, ModelInfo]:
        return {
            "gpt-4o": ModelInfo(
                id="gpt-4o",
                name="GPT-4o",
                provider_id="openai",
                context_limit=128000,
                output_limit=16384,
                supports_tools=True,
                supports_streaming=True,
                cost_input=2.5,
                cost_output=10.0,
            ),
            "gpt-4o-mini": ModelInfo(
                id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider_id="openai",
                context_limit=128000,
                output_limit=16384,
                supports_tools=True,
                supports_streaming=True,
                cost_input=0.15,
                cost_output=0.6,
            ),
            "o1": ModelInfo(
                id="o1",
                name="o1",
                provider_id="openai",
                context_limit=200000,
                output_limit=100000,
                supports_tools=True,
                supports_streaming=True,
                cost_input=15.0,
                cost_output=60.0,
            ),
        }
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self._api_key)
            except ImportError:
                raise ImportError("openai package is required. Install with: pip install openai")
        return self._client
    
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
        
        openai_messages = []
        
        if system:
            openai_messages.append({"role": "system", "content": system})
        
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                openai_messages.append({"role": msg.role, "content": content})
            else:
                openai_messages.append({
                    "role": msg.role,
                    "content": [{"type": c.type, "text": c.text} for c in content if c.text]
                })
        
        kwargs: Dict[str, Any] = {
            "model": model_id,
            "messages": openai_messages,
            "stream": True,
        }
        
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        
        if temperature is not None:
            kwargs["temperature"] = temperature
        
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", t.get("input_schema", {}))
                    }
                }
                for t in tools
            ]
        
        tool_calls: Dict[int, Dict[str, Any]] = {}
        usage_data = None
        finish_reason = None
        
        async for chunk in await client.chat.completions.create(**kwargs):
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                
                if delta.content:
                    yield StreamChunk(type="text", text=delta.content)
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                        
                        if tc.id:
                            tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["arguments"] += tc.function.arguments
            
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            
            if chunk.usage:
                usage_data = {
                    "input_tokens": chunk.usage.prompt_tokens,
                    "output_tokens": chunk.usage.completion_tokens,
                }
        
        for tc_data in tool_calls.values():
            try:
                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            yield StreamChunk(
                type="tool_call",
                tool_call=ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=args
                )
            )
        
        stop_reason = self._map_stop_reason(finish_reason)
        yield StreamChunk(type="done", usage=usage_data, stop_reason=stop_reason)
    
    def _map_stop_reason(self, openai_finish_reason: Optional[str]) -> str:
        mapping = {
            "stop": "end_turn",
            "tool_calls": "tool_calls",
            "length": "max_tokens",
            "content_filter": "end_turn",
        }
        return mapping.get(openai_finish_reason or "", "end_turn")
