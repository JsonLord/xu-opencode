from typing import Dict, Any, List, Optional, AsyncGenerator
import os
import logging

from .provider import BaseProvider, ModelInfo, Message, StreamChunk, ToolCall

logger = logging.getLogger(__name__)


GEMINI3_MODELS = {
    "gemini-3-flash-preview",
}


class GeminiProvider(BaseProvider):

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._client = None

    @property
    def id(self) -> str:
        return "gemini"

    @property
    def name(self) -> str:
        return "Google Gemini"

    @property
    def models(self) -> Dict[str, ModelInfo]:
        return {
            "gemini-3-flash-preview": ModelInfo(
                id="gemini-3-flash-preview",
                name="Gemini 3.0 Flash",
                provider_id="gemini",
                context_limit=1048576,
                output_limit=65536,
                supports_tools=True,
                supports_streaming=True,
                cost_input=0.5,
                cost_output=3.0,
            ),
        }

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except ImportError:
                raise ImportError("google-genai package is required. Install with: pip install google-genai")
        return self._client

    def _is_gemini3(self, model_id: str) -> bool:
        return model_id in GEMINI3_MODELS

    async def stream(
        self,
        model_id: str,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        from google.genai import types

        client = self._get_client()

        contents = []
        print(f"[Gemini DEBUG] Building contents from {len(messages)} messages", flush=True)
        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            content = msg.content
            print(f"[Gemini DEBUG] msg.role={msg.role}, content type={type(content)}, content={repr(content)[:100]}", flush=True)

            if isinstance(content, str) and content:
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=content)]
                ))
            elif content:
                parts = [types.Part(text=c.text) for c in content if c.text]
                if parts:
                    contents.append(types.Content(role=role, parts=parts))

        print(f"[Gemini DEBUG] Built {len(contents)} contents", flush=True)

        config_kwargs: Dict[str, Any] = {}

        if system:
            config_kwargs["system_instruction"] = system

        if temperature is not None:
            config_kwargs["temperature"] = temperature

        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        if self._is_gemini3(model_id):
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                include_thoughts=True
            )
            # thinking_level 미설정 → 기본값 "high" (동적 reasoning)

        if tools:
            gemini_tools = []
            for t in tools:
                func_decl = types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("parameters", t.get("input_schema", {}))
                )
                gemini_tools.append(types.Tool(function_declarations=[func_decl]))
            config_kwargs["tools"] = gemini_tools

        config = types.GenerateContentConfig(**config_kwargs)

        async for chunk in self._stream_with_fallback(
            client, model_id, contents, config, config_kwargs, types
        ):
            yield chunk

    async def _stream_with_fallback(
        self, client, model_id: str, contents, config, config_kwargs: Dict[str, Any], types
    ):
        try:
            async for chunk in self._do_stream(client, model_id, contents, config):
                yield chunk
        except Exception as e:
            error_str = str(e).lower()
            has_thinking = "thinking_config" in config_kwargs

            if has_thinking and ("thinking" in error_str or "budget" in error_str or "level" in error_str or "unsupported" in error_str):
                logger.warning(f"Thinking not supported for {model_id}, retrying without thinking config")
                del config_kwargs["thinking_config"]
                fallback_config = types.GenerateContentConfig(**config_kwargs)

                async for chunk in self._do_stream(client, model_id, contents, fallback_config):
                    yield chunk
            else:
                logger.error(f"Gemini stream error: {e}")
                yield StreamChunk(type="error", error=str(e))

    async def _do_stream(self, client, model_id: str, contents, config):
        response_stream = await client.aio.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=config,
        )

        pending_tool_calls = []

        async for chunk in response_stream:
            if not chunk.candidates:
                continue

            candidate = chunk.candidates[0]

            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        if part.text:
                            yield StreamChunk(type="reasoning", text=part.text)
                    elif hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        tool_call = ToolCall(
                            id=f"call_{fc.name}_{len(pending_tool_calls)}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {}
                        )
                        pending_tool_calls.append(tool_call)
                    elif part.text:
                        yield StreamChunk(type="text", text=part.text)

            finish_reason = getattr(candidate, 'finish_reason', None)
            if finish_reason:
                print(f"[Gemini] finish_reason: {finish_reason}, pending_tool_calls: {len(pending_tool_calls)}", flush=True)
                for tc in pending_tool_calls:
                    yield StreamChunk(type="tool_call", tool_call=tc)

                # IMPORTANT: If there are pending tool calls, ALWAYS return "tool_calls"
                # regardless of Gemini's finish_reason (which is often STOP even with tool calls)
                if pending_tool_calls:
                    stop_reason = "tool_calls"
                else:
                    stop_reason = self._map_stop_reason(finish_reason)
                print(f"[Gemini] Mapped stop_reason: {stop_reason}", flush=True)

                usage = None
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    usage = {
                        "input_tokens": getattr(chunk.usage_metadata, 'prompt_token_count', 0),
                        "output_tokens": getattr(chunk.usage_metadata, 'candidates_token_count', 0),
                    }
                    if hasattr(chunk.usage_metadata, 'thoughts_token_count'):
                        usage["thinking_tokens"] = chunk.usage_metadata.thoughts_token_count

                yield StreamChunk(type="done", usage=usage, stop_reason=stop_reason)
                return

        yield StreamChunk(type="done", stop_reason="end_turn")

    def _map_stop_reason(self, gemini_finish_reason) -> str:
        reason_name = str(gemini_finish_reason).lower() if gemini_finish_reason else ""

        if "stop" in reason_name or "end" in reason_name:
            return "end_turn"
        elif "tool" in reason_name or "function" in reason_name:
            return "tool_calls"
        elif "max" in reason_name or "length" in reason_name:
            return "max_tokens"
        elif "safety" in reason_name:
            return "safety"
        return "end_turn"
