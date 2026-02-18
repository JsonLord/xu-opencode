"""
Session prompt handling with agentic loop support.
"""

from typing import Optional, List, Dict, Any, AsyncIterator, Literal
from pydantic import BaseModel
import asyncio
import json

from .session import Session
from .message import Message, MessagePart, AssistantMessage
from .processor import SessionProcessor
from ..provider import get_provider, list_providers
from ..provider.provider import Message as ProviderMessage, StreamChunk, ToolCall
from ..tool import get_tool, get_tools_schema, ToolContext, get_registry
from ..core.config import settings
from ..core.bus import Bus, PART_UPDATED, PartPayload, STEP_STARTED, STEP_FINISHED, StepPayload, TOOL_STATE_CHANGED, ToolStatePayload
from ..agent import get as get_agent, default_agent, get_system_prompt, is_tool_allowed, AgentInfo, get_prompt_for_provider


class PromptInput(BaseModel):
    content: str
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    system: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools_enabled: bool = True
    # Agentic loop options
    auto_continue: Optional[bool] = None  # None = use agent default
    max_steps: Optional[int] = None  # None = use agent default


class LoopState(BaseModel):
    step: int = 0
    max_steps: int = 50
    auto_continue: bool = True
    stop_reason: Optional[str] = None
    paused: bool = False
    pause_reason: Optional[str] = None


import re
FAKE_TOOL_CALL_PATTERN = re.compile(
    r'\[Called\s+tool:\s*(\w+)\s*\(\s*(\{[^}]*\}|\{[^)]*\}|[^)]*)\s*\)\]',
    re.IGNORECASE
)


class SessionPrompt:
    
    _active_sessions: Dict[str, asyncio.Task] = {}
    _loop_states: Dict[str, LoopState] = {}
    
    @classmethod
    async def prompt(
        cls,
        session_id: str,
        input: PromptInput,
        user_id: Optional[str] = None
    ) -> AsyncIterator[StreamChunk]:
        session = await Session.get(session_id, user_id)
        
        # Get agent configuration
        agent_id = session.agent_id or "build"
        agent = get_agent(agent_id) or default_agent()
        
        # Determine loop settings
        auto_continue = input.auto_continue if input.auto_continue is not None else agent.auto_continue
        max_steps = input.max_steps if input.max_steps is not None else agent.max_steps
        
        if auto_continue:
            async for chunk in cls._agentic_loop(session_id, input, agent, max_steps, user_id):
                yield chunk
        else:
            async for chunk in cls._single_turn(session_id, input, agent, user_id=user_id):
                yield chunk
    
    @classmethod
    async def _agentic_loop(
        cls,
        session_id: str,
        input: PromptInput,
        agent: AgentInfo,
        max_steps: int,
        user_id: Optional[str] = None
    ) -> AsyncIterator[StreamChunk]:
        state = LoopState(step=0, max_steps=max_steps, auto_continue=True)
        cls._loop_states[session_id] = state

        # SessionProcessor 가져오기
        processor = SessionProcessor.get_or_create(session_id, max_steps=max_steps)

        try:
            while processor.should_continue() and not state.paused:
                state.step += 1

                # 스텝 시작
                step_info = processor.start_step()
                await Bus.publish(STEP_STARTED, StepPayload(
                    session_id=session_id,
                    step=state.step,
                    max_steps=max_steps
                ))

                print(f"[AGENTIC LOOP] Starting step {state.step}, stop_reason={state.stop_reason}", flush=True)

                turn_input = input if state.step == 1 else PromptInput(
                    content="",
                    provider_id=input.provider_id,
                    model_id=input.model_id,
                    temperature=input.temperature,
                    max_tokens=input.max_tokens,
                    tools_enabled=input.tools_enabled,
                    auto_continue=False,
                )

                if state.step > 1:
                    yield StreamChunk(type="step", text=f"Step {state.step}")

                # Track tool calls in this turn
                has_tool_calls_this_turn = False

                async for chunk in cls._single_turn(
                    session_id,
                    turn_input,
                    agent,
                    is_continuation=(state.step > 1),
                    user_id=user_id
                ):
                    yield chunk

                    if chunk.type == "tool_call" and chunk.tool_call:
                        has_tool_calls_this_turn = True
                        print(f"[AGENTIC LOOP] tool_call: {chunk.tool_call.name}", flush=True)

                        if chunk.tool_call.name == "question" and agent.pause_on_question:
                            state.paused = True
                            state.pause_reason = "question"

                    # question tool이 완료되면 (답변 받음) pause 해제
                    elif chunk.type == "tool_result":
                        if state.paused and state.pause_reason == "question":
                            state.paused = False
                            state.pause_reason = None

                    elif chunk.type == "done":
                        state.stop_reason = chunk.stop_reason
                        print(f"[AGENTIC LOOP] done: stop_reason={chunk.stop_reason}", flush=True)

                # 스텝 완료
                step_status = "completed"
                if processor.is_doom_loop():
                    step_status = "doom_loop"
                    print(f"[AGENTIC LOOP] Doom loop detected! Stopping execution.", flush=True)
                    yield StreamChunk(type="text", text=f"\n[경고: 동일 도구 반복 호출 감지, 루프를 중단합니다]\n")

                processor.finish_step(status=step_status)
                await Bus.publish(STEP_FINISHED, StepPayload(
                    session_id=session_id,
                    step=state.step,
                    max_steps=max_steps
                ))

                print(f"[AGENTIC LOOP] End of step {state.step}: stop_reason={state.stop_reason}, has_tool_calls={has_tool_calls_this_turn}", flush=True)

                # Doom loop 감지 시 중단
                if processor.is_doom_loop():
                    break

                # If this turn had no new tool calls (just text response), we're done
                if state.stop_reason != "tool_calls":
                    print(f"[AGENTIC LOOP] Breaking: stop_reason != tool_calls", flush=True)
                    break

            # Loop 종료 후 상태 메시지만 출력 (summary LLM 호출 없음!)
            if state.paused:
                yield StreamChunk(type="text", text=f"\n[Paused: {state.pause_reason}]\n")
            elif state.step >= state.max_steps:
                yield StreamChunk(type="text", text=f"\n[Max steps ({state.max_steps}) reached]\n")
            # else: 자연스럽게 종료 (추가 출력 없음)

        finally:
            if session_id in cls._loop_states:
                del cls._loop_states[session_id]
            # SessionProcessor 정리
            SessionProcessor.remove(session_id)
    
    @classmethod
    def _infer_provider_from_model(cls, model_id: str) -> str:
        """model_id에서 provider_id를 추론"""
        # LiteLLM prefix 기반 모델은 litellm provider 사용
        litellm_prefixes = ["gemini/", "groq/", "deepseek/", "openrouter/", "zai/"]
        for prefix in litellm_prefixes:
            if model_id.startswith(prefix):
                return "litellm"

        # Claude 모델
        if model_id.startswith("claude-"):
            return "litellm"

        # GPT/O1 모델
        if model_id.startswith("gpt-") or model_id.startswith("o1"):
            return "litellm"

        # 기본값
        return settings.default_provider

    @classmethod
    async def _single_turn(
        cls,
        session_id: str,
        input: PromptInput,
        agent: AgentInfo,
        is_continuation: bool = False,
        user_id: Optional[str] = None
    ) -> AsyncIterator[StreamChunk]:
        session = await Session.get(session_id, user_id)

        model_id = input.model_id or session.model_id or settings.default_model

        # provider_id가 명시되지 않으면 model_id에서 추론
        if input.provider_id:
            provider_id = input.provider_id
        elif session.provider_id:
            provider_id = session.provider_id
        else:
            provider_id = cls._infer_provider_from_model(model_id)

        print(f"[Prompt DEBUG] input.provider_id={input.provider_id}, session.provider_id={session.provider_id}", flush=True)
        print(f"[Prompt DEBUG] Final provider_id={provider_id}, model_id={model_id}", flush=True)

        provider = get_provider(provider_id)
        print(f"[Prompt DEBUG] Got provider: {provider}", flush=True)
        if not provider:
            yield StreamChunk(type="error", error=f"Provider not found: {provider_id}")
            return
        
        # Only create user message if there's content (not a continuation)
        if input.content and not is_continuation:
            user_msg = await Message.create_user(session_id, input.content, user_id)
        
        assistant_msg = await Message.create_assistant(session_id, provider_id, model_id, user_id)
        
        # Build message history
        history = await Message.list(session_id, user_id=user_id)
        messages = cls._build_messages(history[:-1], include_tool_results=True)
        
        # Build system prompt with provider-specific optimization
        system_prompt = cls._build_system_prompt(agent, provider_id, input.system)
        
        # Get tools schema
        tools_schema = get_tools_schema() if input.tools_enabled else None
        
        current_text_part: Optional[MessagePart] = None
        accumulated_text = ""

        # reasoning 저장을 위한 변수
        current_reasoning_part: Optional[MessagePart] = None
        accumulated_reasoning = ""
        
        try:
            async for chunk in provider.stream(
                model_id=model_id,
                messages=messages,
                tools=tools_schema,
                system=system_prompt,
                temperature=input.temperature or agent.temperature,
                max_tokens=input.max_tokens or agent.max_tokens,
            ):
                if chunk.type == "text":
                    accumulated_text += chunk.text or ""
                    
                    if current_text_part is None:
                        current_text_part = await Message.add_part(
                            assistant_msg.id,
                            session_id,
                            MessagePart(
                                id="",
                                session_id=session_id,
                                message_id=assistant_msg.id,
                                type="text",
                                content=accumulated_text
                            ),
                            user_id
                        )
                    else:
                        await Message.update_part(
                            session_id,
                            assistant_msg.id,
                            current_text_part.id,
                            {"content": accumulated_text},
                            user_id
                        )
                    
                    yield chunk
                
                elif chunk.type == "tool_call":
                    tc = chunk.tool_call
                    if tc:
                        # Check permission
                        permission = is_tool_allowed(agent, tc.name)
                        if permission == "deny":
                            yield StreamChunk(
                                type="tool_result",
                                text=f"Error: Tool '{tc.name}' is not allowed for this agent"
                            )
                            continue

                        tool_part = await Message.add_part(
                            assistant_msg.id,
                            session_id,
                            MessagePart(
                                id="",
                                session_id=session_id,
                                message_id=assistant_msg.id,
                                type="tool_call",
                                tool_call_id=tc.id,
                                tool_name=tc.name,
                                tool_args=tc.arguments,
                                tool_status="running"  # 실행 중 상태
                            ),
                            user_id
                        )

                        # IMPORTANT: Yield tool_call FIRST so frontend can show UI
                        # This is critical for interactive tools like 'question'
                        yield chunk

                        # 도구 실행 시작 이벤트 발행
                        await Bus.publish(TOOL_STATE_CHANGED, ToolStatePayload(
                            session_id=session_id,
                            message_id=assistant_msg.id,
                            part_id=tool_part.id,
                            tool_name=tc.name,
                            status="running"
                        ))

                        # Execute tool (may block for user input, e.g., question tool)
                        tool_result, tool_status = await cls._execute_tool(
                            session_id,
                            assistant_msg.id,
                            tc.id,
                            tc.name,
                            tc.arguments,
                            user_id
                        )

                        # tool_call 파트의 status를 completed/error로 업데이트
                        await Message.update_part(
                            session_id,
                            assistant_msg.id,
                            tool_part.id,
                            {"tool_status": tool_status},
                            user_id
                        )

                        # 도구 완료 이벤트 발행
                        await Bus.publish(TOOL_STATE_CHANGED, ToolStatePayload(
                            session_id=session_id,
                            message_id=assistant_msg.id,
                            part_id=tool_part.id,
                            tool_name=tc.name,
                            status=tool_status
                        ))

                        yield StreamChunk(
                            type="tool_result",
                            text=tool_result
                        )
                    else:
                        yield chunk
                
                elif chunk.type == "reasoning":
                    # reasoning 저장 (기존에는 yield만 했음)
                    accumulated_reasoning += chunk.text or ""

                    if current_reasoning_part is None:
                        current_reasoning_part = await Message.add_part(
                            assistant_msg.id,
                            session_id,
                            MessagePart(
                                id="",
                                session_id=session_id,
                                message_id=assistant_msg.id,
                                type="reasoning",
                                content=accumulated_reasoning
                            ),
                            user_id
                        )
                    else:
                        await Message.update_part(
                            session_id,
                            assistant_msg.id,
                            current_reasoning_part.id,
                            {"content": accumulated_reasoning},
                            user_id
                        )

                    yield chunk
                
                elif chunk.type == "done":
                    if chunk.usage:
                        await Message.set_usage(session_id, assistant_msg.id, chunk.usage, user_id)
                    yield chunk
                
                elif chunk.type == "error":
                    await Message.set_error(session_id, assistant_msg.id, chunk.error or "Unknown error", user_id)
                    yield chunk
            
            await Session.touch(session_id)
            
        except Exception as e:
            error_msg = str(e)
            await Message.set_error(session_id, assistant_msg.id, error_msg, user_id)
            yield StreamChunk(type="error", error=error_msg)
    
    @classmethod
    def _detect_fake_tool_call(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the model wrote a fake tool call as text instead of using actual tool calling.
        Returns parsed tool call info if detected, None otherwise.
        
        Patterns detected:
        - [Called tool: toolname({...})]
        - [Called tool: toolname({'key': 'value'})]
        """
        if not text:
            return None
        
        match = FAKE_TOOL_CALL_PATTERN.search(text)
        if match:
            tool_name = match.group(1)
            args_str = match.group(2).strip()
            
            # Try to parse arguments
            args = {}
            if args_str:
                try:
                    # Handle both JSON and Python dict formats
                    args_str = args_str.replace("'", '"')  # Convert Python dict to JSON
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    # Try to extract key-value pairs manually
                    # Pattern: 'key': 'value' or "key": "value"
                    kv_pattern = re.compile(r'["\']?(\w+)["\']?\s*:\s*["\']([^"\']+)["\']')
                    for kv_match in kv_pattern.finditer(args_str):
                        args[kv_match.group(1)] = kv_match.group(2)
            
            return {
                "name": tool_name,
                "arguments": args
            }
        
        return None
    
    @classmethod
    def _build_system_prompt(
        cls,
        agent: AgentInfo,
        provider_id: str,
        custom_system: Optional[str] = None
    ) -> Optional[str]:
        """Build the complete system prompt.

        Args:
            agent: The agent configuration
            provider_id: The provider identifier for selecting optimized prompt
            custom_system: Optional custom system prompt to append

        Returns:
            The complete system prompt, or None if empty
        """
        parts = []

        # Add provider-specific system prompt (optimized for Claude/Gemini/etc.)
        provider_prompt = get_prompt_for_provider(provider_id)
        if provider_prompt:
            parts.append(provider_prompt)

        # Add agent-specific prompt (if defined and different from provider prompt)
        agent_prompt = get_system_prompt(agent)
        if agent_prompt and agent_prompt != provider_prompt:
            parts.append(agent_prompt)

        # Add custom system prompt
        if custom_system:
            parts.append(custom_system)

        return "\n\n".join(parts) if parts else None
    
    @classmethod
    def _build_messages(
        cls,
        history: List,
        include_tool_results: bool = True
    ) -> List[ProviderMessage]:
        """Build message list for LLM including tool calls and results.
        
        Proper tool calling flow:
        1. User message
        2. Assistant message (may include tool calls)
        3. Tool results (as user message with tool context)
        4. Assistant continues
        """
        messages = []
        
        for msg in history:
            if msg.role == "user":
                # Skip empty user messages (continuations)
                if msg.content:
                    messages.append(ProviderMessage(role="user", content=msg.content))
            
            elif msg.role == "assistant":
                # Collect all parts
                text_parts = []
                tool_calls = []
                tool_results = []
                
                for part in getattr(msg, "parts", []):
                    if part.type == "text" and part.content:
                        text_parts.append(part.content)
                    elif part.type == "tool_call" and include_tool_results:
                        tool_calls.append({
                            "id": part.tool_call_id,
                            "name": part.tool_name,
                            "arguments": part.tool_args or {}
                        })
                    elif part.type == "tool_result" and include_tool_results:
                        tool_results.append({
                            "tool_call_id": part.tool_call_id,
                            "output": part.tool_output or ""
                        })
                
                # Build assistant content - only text, NO tool call summaries
                # IMPORTANT: Do NOT include "[Called tool: ...]" patterns as this causes
                # models like Gemini to mimic the pattern instead of using actual tool calls
                assistant_content_parts = []
                
                if text_parts:
                    assistant_content_parts.append("".join(text_parts))
                
                if assistant_content_parts:
                    messages.append(ProviderMessage(
                        role="assistant", 
                        content="\n".join(assistant_content_parts)
                    ))
                
                # Add tool results as user message (simulating tool response)
                if tool_results:
                    result_content = []
                    for result in tool_results:
                        result_content.append(f"Tool result:\n{result['output']}")
                    messages.append(ProviderMessage(
                        role="user",
                        content="\n\n".join(result_content)
                    ))
        
        return messages
    
    @classmethod
    async def _execute_tool(
        cls,
        session_id: str,
        message_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> tuple[str, str]:
        """Execute a tool and store the result. Returns (output, status)."""
        # SessionProcessor를 통한 doom loop 감지
        # tool_args도 전달하여 같은 도구 + 같은 인자일 때만 doom loop으로 판단
        processor = SessionProcessor.get_or_create(session_id)
        is_doom_loop = processor.record_tool_call(tool_name, tool_args)

        if is_doom_loop:
            error_output = f"Error: Doom loop detected - tool '{tool_name}' called repeatedly"
            await Message.add_part(
                message_id,
                session_id,
                MessagePart(
                    id="",
                    session_id=session_id,
                    message_id=message_id,
                    type="tool_result",
                    tool_call_id=tool_call_id,
                    tool_output=error_output
                ),
                user_id
            )
            return error_output, "error"

        # Registry에서 도구 가져오기
        registry = get_registry()
        tool = registry.get(tool_name)

        if not tool:
            error_output = f"Error: Tool '{tool_name}' not found"
            await Message.add_part(
                message_id,
                session_id,
                MessagePart(
                    id="",
                    session_id=session_id,
                    message_id=message_id,
                    type="tool_result",
                    tool_call_id=tool_call_id,
                    tool_output=error_output
                ),
                user_id
            )
            return error_output, "error"

        ctx = ToolContext(
            session_id=session_id,
            message_id=message_id,
            tool_call_id=tool_call_id,
        )

        try:
            result = await tool.execute(tool_args, ctx)

            # 출력 길이 제한 적용
            truncated_output = tool.truncate_output(result.output)
            output = f"[{result.title}]\n{truncated_output}"
            status = "completed"
        except Exception as e:
            output = f"Error executing tool: {str(e)}"
            status = "error"

        await Message.add_part(
            message_id,
            session_id,
            MessagePart(
                id="",
                session_id=session_id,
                message_id=message_id,
                type="tool_result",
                tool_call_id=tool_call_id,
                tool_output=output
            ),
            user_id
        )

        return output, status
    
    @classmethod
    def cancel(cls, session_id: str) -> bool:
        """Cancel an active session."""
        cancelled = False
        
        if session_id in cls._active_sessions:
            cls._active_sessions[session_id].cancel()
            del cls._active_sessions[session_id]
            cancelled = True
        
        if session_id in cls._loop_states:
            cls._loop_states[session_id].paused = True
            cls._loop_states[session_id].pause_reason = "cancelled"
            del cls._loop_states[session_id]
            cancelled = True
        
        return cancelled
    
    @classmethod
    def get_loop_state(cls, session_id: str) -> Optional[LoopState]:
        """Get the current loop state for a session."""
        return cls._loop_states.get(session_id)
    
    @classmethod
    async def resume(cls, session_id: str) -> AsyncIterator[StreamChunk]:
        state = cls._loop_states.get(session_id)
        if not state or not state.paused:
            yield StreamChunk(type="error", error="No paused loop to resume")
            return
        
        state.paused = False
        state.pause_reason = None
        
        session = await Session.get(session_id)
        agent_id = session.agent_id or "build"
        agent = get_agent(agent_id) or default_agent()
        
        continue_input = PromptInput(content="")
        
        while state.stop_reason == "tool_calls" and not state.paused and state.step < state.max_steps:
            state.step += 1
            
            yield StreamChunk(type="text", text=f"\n[Resuming... step {state.step}/{state.max_steps}]\n")
            
            async for chunk in cls._single_turn(session_id, continue_input, agent, is_continuation=True):
                yield chunk
                
                if chunk.type == "tool_call" and chunk.tool_call:
                    if chunk.tool_call.name == "question" and agent.pause_on_question:
                        state.paused = True
                        state.pause_reason = "question"
                
                elif chunk.type == "done":
                    state.stop_reason = chunk.stop_reason
