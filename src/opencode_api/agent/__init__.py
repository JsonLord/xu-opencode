"""
Agent module - agent configurations and system prompts.
"""

from .agent import (
    AgentInfo,
    AgentModel,
    AgentPermission,
    get,
    list_agents,
    default_agent,
    register,
    unregister,
    is_tool_allowed,
    get_system_prompt,
    get_prompt_for_provider,
    DEFAULT_AGENTS,
    PROMPTS,
)

__all__ = [
    "AgentInfo",
    "AgentModel",
    "AgentPermission",
    "get",
    "list_agents",
    "default_agent",
    "register",
    "unregister",
    "is_tool_allowed",
    "get_system_prompt",
    "get_prompt_for_provider",
    "DEFAULT_AGENTS",
    "PROMPTS",
]
