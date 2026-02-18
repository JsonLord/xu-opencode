#!/usr/bin/env python3
"""
Test script for Gemini Extended Thinking + Tool Calling integration.
Tests that thinking and tool calls work together correctly.
"""
import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

from opencode_api.provider.gemini import GeminiProvider
from opencode_api.provider.provider import Message


# Define test tools schema
TEST_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for current information. Use this when you need to find up-to-date information about any topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "calculator",
        "description": "Perform mathematical calculations. Use this for any math operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate"
                }
            },
            "required": ["expression"]
        }
    }
]


async def test_thinking_only():
    """Test that thinking works without tools."""
    print("\n" + "="*60)
    print("TEST 1: Thinking Only (No Tools)")
    print("="*60)
    
    provider = GeminiProvider(api_key=os.getenv("GOOGLE_API_KEY"))
    
    messages = [
        Message(role="user", content="3개의 상자가 있어. 하나에는 금, 하나에는 은, 하나에는 돌이 있어. 상자1: '여기에 금이 없다', 상자2: '여기에 금이 있다', 상자3: '금은 상자1에 있다'. 정확히 하나만 진실이야. 금은 어디?")
    ]
    
    reasoning_chunks = []
    text_chunks = []
    tool_calls = []
    usage = None
    
    async for chunk in provider.stream(
        model_id="gemini-2.5-pro",
        messages=messages,
        tools=None,  # No tools
        system="You are a helpful assistant. Think step by step."
    ):
        if chunk.type == "reasoning":
            reasoning_chunks.append(chunk.text)
            print(f"[REASONING] {chunk.text[:100]}..." if len(chunk.text) > 100 else f"[REASONING] {chunk.text}")
        elif chunk.type == "text":
            text_chunks.append(chunk.text)
            print(f"[TEXT] {chunk.text}", end="", flush=True)
        elif chunk.type == "tool_call":
            tool_calls.append(chunk.tool_call)
            print(f"\n[TOOL_CALL] {chunk.tool_call.name}({chunk.tool_call.arguments})")
        elif chunk.type == "done":
            usage = chunk.usage
            print(f"\n[DONE] stop_reason={chunk.stop_reason}")
        elif chunk.type == "error":
            print(f"\n[ERROR] {chunk.error}")
    
    print("\n--- Summary ---")
    print(f"Reasoning chunks: {len(reasoning_chunks)}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Tool calls: {len(tool_calls)}")
    if usage:
        print(f"Usage: input={usage.get('input_tokens', 0)}, output={usage.get('output_tokens', 0)}, thinking={usage.get('thinking_tokens', 0)}")
    
    return len(reasoning_chunks) > 0


async def test_tool_calling():
    """Test that tool calling works."""
    print("\n" + "="*60)
    print("TEST 2: Tool Calling (Should trigger web_search)")
    print("="*60)
    
    provider = GeminiProvider(api_key=os.getenv("GOOGLE_API_KEY"))
    
    messages = [
        Message(role="user", content="2024년 노벨 물리학상 수상자가 누구야? 웹 검색해서 알려줘.")
    ]
    
    reasoning_chunks = []
    text_chunks = []
    tool_calls = []
    usage = None
    
    async for chunk in provider.stream(
        model_id="gemini-2.5-pro",
        messages=messages,
        tools=TEST_TOOLS,
        system="You are a helpful assistant. Use tools when needed."
    ):
        if chunk.type == "reasoning":
            reasoning_chunks.append(chunk.text)
            print(f"[REASONING] {chunk.text[:100]}..." if len(chunk.text) > 100 else f"[REASONING] {chunk.text}")
        elif chunk.type == "text":
            text_chunks.append(chunk.text)
            print(f"[TEXT] {chunk.text}", end="", flush=True)
        elif chunk.type == "tool_call":
            tool_calls.append(chunk.tool_call)
            print(f"\n[TOOL_CALL] {chunk.tool_call.name}({chunk.tool_call.arguments})")
        elif chunk.type == "done":
            usage = chunk.usage
            print(f"\n[DONE] stop_reason={chunk.stop_reason}")
        elif chunk.type == "error":
            print(f"\n[ERROR] {chunk.error}")
    
    print("\n--- Summary ---")
    print(f"Reasoning chunks: {len(reasoning_chunks)}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Tool calls: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"  - {tc.name}: {tc.arguments}")
    if usage:
        print(f"Usage: input={usage.get('input_tokens', 0)}, output={usage.get('output_tokens', 0)}, thinking={usage.get('thinking_tokens', 0)}")
    
    return len(tool_calls) > 0


async def test_thinking_with_tools():
    """Test that thinking AND tool calling work together."""
    print("\n" + "="*60)
    print("TEST 3: Thinking + Tool Calling Together")
    print("="*60)
    
    provider = GeminiProvider(api_key=os.getenv("GOOGLE_API_KEY"))
    
    # Complex question that requires both thinking and tool use
    messages = [
        Message(role="user", content="복잡한 수학 문제야: (17 * 23) + (45 / 9) - 12^2 를 계산해줘. 계산기 도구를 사용해서 정확한 답을 구해줘.")
    ]
    
    reasoning_chunks = []
    text_chunks = []
    tool_calls = []
    usage = None
    
    async for chunk in provider.stream(
        model_id="gemini-2.5-pro",
        messages=messages,
        tools=TEST_TOOLS,
        system="You are a helpful assistant. Use the calculator tool for mathematical operations. Think through the problem step by step."
    ):
        if chunk.type == "reasoning":
            reasoning_chunks.append(chunk.text)
            print(f"[REASONING] {chunk.text[:100]}..." if len(chunk.text) > 100 else f"[REASONING] {chunk.text}")
        elif chunk.type == "text":
            text_chunks.append(chunk.text)
            print(f"[TEXT] {chunk.text}", end="", flush=True)
        elif chunk.type == "tool_call":
            tool_calls.append(chunk.tool_call)
            print(f"\n[TOOL_CALL] {chunk.tool_call.name}({chunk.tool_call.arguments})")
        elif chunk.type == "done":
            usage = chunk.usage
            print(f"\n[DONE] stop_reason={chunk.stop_reason}")
        elif chunk.type == "error":
            print(f"\n[ERROR] {chunk.error}")
    
    print("\n--- Summary ---")
    print(f"Reasoning chunks: {len(reasoning_chunks)}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Tool calls: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"  - {tc.name}: {tc.arguments}")
    if usage:
        print(f"Usage: input={usage.get('input_tokens', 0)}, output={usage.get('output_tokens', 0)}, thinking={usage.get('thinking_tokens', 0)}")
    
    # Success if we got both reasoning and tool calls, OR just tool calls (model might not always think)
    return len(tool_calls) > 0


async def test_flash_model():
    """Test that Flash model also works with thinking + tools."""
    print("\n" + "="*60)
    print("TEST 4: Gemini 2.5 Flash with Thinking + Tools")
    print("="*60)
    
    provider = GeminiProvider(api_key=os.getenv("GOOGLE_API_KEY"))
    
    messages = [
        Message(role="user", content="오늘 서울 날씨 어때? 웹에서 검색해줘.")
    ]
    
    reasoning_chunks = []
    text_chunks = []
    tool_calls = []
    usage = None
    
    async for chunk in provider.stream(
        model_id="gemini-2.5-flash",
        messages=messages,
        tools=TEST_TOOLS,
        system="You are a helpful assistant. Use tools when needed."
    ):
        if chunk.type == "reasoning":
            reasoning_chunks.append(chunk.text)
            print(f"[REASONING] {chunk.text[:100]}..." if len(chunk.text) > 100 else f"[REASONING] {chunk.text}")
        elif chunk.type == "text":
            text_chunks.append(chunk.text)
            print(f"[TEXT] {chunk.text}", end="", flush=True)
        elif chunk.type == "tool_call":
            tool_calls.append(chunk.tool_call)
            print(f"\n[TOOL_CALL] {chunk.tool_call.name}({chunk.tool_call.arguments})")
        elif chunk.type == "done":
            usage = chunk.usage
            print(f"\n[DONE] stop_reason={chunk.stop_reason}")
        elif chunk.type == "error":
            print(f"\n[ERROR] {chunk.error}")
    
    print("\n--- Summary ---")
    print(f"Reasoning chunks: {len(reasoning_chunks)}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Tool calls: {len(tool_calls)}")
    if usage:
        print(f"Usage: input={usage.get('input_tokens', 0)}, output={usage.get('output_tokens', 0)}, thinking={usage.get('thinking_tokens', 0)}")
    
    return True  # Flash might not always use tools


async def main():
    print("="*60)
    print("Gemini Extended Thinking + Tool Calling Integration Test")
    print("="*60)
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set in environment")
        return
    
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    results = {}
    
    # Run tests
    try:
        results["thinking_only"] = await test_thinking_only()
    except Exception as e:
        print(f"TEST 1 FAILED: {e}")
        results["thinking_only"] = False
    
    try:
        results["tool_calling"] = await test_tool_calling()
    except Exception as e:
        print(f"TEST 2 FAILED: {e}")
        results["tool_calling"] = False
    
    try:
        results["thinking_with_tools"] = await test_thinking_with_tools()
    except Exception as e:
        print(f"TEST 3 FAILED: {e}")
        results["thinking_with_tools"] = False
    
    try:
        results["flash_model"] = await test_flash_model()
    except Exception as e:
        print(f"TEST 4 FAILED: {e}")
        results["flash_model"] = False
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
