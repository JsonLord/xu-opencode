"""
Agent module - defines agent configurations and system prompts.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from pathlib import Path
import os

# Load prompts
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    prompt_path = PROMPTS_DIR / f"{name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


# Cache loaded prompts - provider-specific prompts
PROMPTS = {
    "anthropic": load_prompt("anthropic"),
    "gemini": load_prompt("gemini"),
    "openai": load_prompt("beast"),  # OpenAI uses default beast prompt
    "default": load_prompt("beast"),
}

# Keep for backward compatibility
BEAST_PROMPT = PROMPTS["default"]


def get_prompt_for_provider(provider_id: str) -> str:
    """Get the appropriate system prompt for a provider.

    Args:
        provider_id: The provider identifier (e.g., 'anthropic', 'gemini', 'openai')

    Returns:
        The system prompt optimized for the given provider.
    """
    return PROMPTS.get(provider_id, PROMPTS["default"])


class AgentModel(BaseModel):
    """Model configuration for an agent."""
    provider_id: str
    model_id: str


class AgentPermission(BaseModel):
    """Permission configuration for tool execution."""
    tool_name: str
    action: Literal["allow", "deny", "ask"] = "allow"
    patterns: List[str] = Field(default_factory=list)


class AgentInfo(BaseModel):
    """Agent configuration schema."""
    id: str
    name: str
    description: Optional[str] = None
    mode: Literal["primary", "subagent", "all"] = "primary"
    hidden: bool = False
    native: bool = True
    
    # Model settings
    model: Optional[AgentModel] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    
    # Prompt
    prompt: Optional[str] = None
    
    # Behavior
    tools: List[str] = Field(default_factory=list, description="Allowed tools, empty = all")
    permissions: List[AgentPermission] = Field(default_factory=list)
    
    # Agentic loop settings
    auto_continue: bool = True
    max_steps: int = 50
    pause_on_question: bool = True
    
    # Extra options
    options: Dict[str, Any] = Field(default_factory=dict)


# Default agents
DEFAULT_AGENTS: Dict[str, AgentInfo] = {
    "build": AgentInfo(
        id="build",
        name="build",
        description="Default agent with full capabilities. Continues working until task is complete.",
        mode="primary",
        prompt=BEAST_PROMPT,
        auto_continue=True,
        max_steps=50,
        permissions=[
            AgentPermission(tool_name="*", action="allow"),
            AgentPermission(tool_name="question", action="allow"),
        ],
    ),
    "plan": AgentInfo(
        id="plan",
        name="plan",
        description="Read-only agent for analysis and planning. Does not modify files.",
        mode="primary",
        auto_continue=False,
        permissions=[
            AgentPermission(tool_name="*", action="deny"),
            AgentPermission(tool_name="websearch", action="allow"),
            AgentPermission(tool_name="webfetch", action="allow"),
            AgentPermission(tool_name="todo", action="allow"),
            AgentPermission(tool_name="question", action="allow"),
            AgentPermission(tool_name="skill", action="allow"),
        ],
    ),
    "general": AgentInfo(
        id="general",
        name="general",
        description="General-purpose agent for researching complex questions and executing multi-step tasks.",
        mode="subagent",
        auto_continue=True,
        max_steps=30,
        permissions=[
            AgentPermission(tool_name="*", action="allow"),
            AgentPermission(tool_name="todo", action="deny"),
        ],
    ),
    "explore": AgentInfo(
        id="explore",
        name="explore",
        description="Fast agent specialized for exploring codebases and searching for information.",
        mode="subagent",
        auto_continue=False,
        permissions=[
            AgentPermission(tool_name="*", action="deny"),
            AgentPermission(tool_name="websearch", action="allow"),
            AgentPermission(tool_name="webfetch", action="allow"),
        ],
    ),
}

# Custom agents loaded from config
_custom_agents: Dict[str, AgentInfo] = {}


def get(agent_id: str) -> Optional[AgentInfo]:
    """Get an agent by ID."""
    if agent_id in _custom_agents:
        return _custom_agents[agent_id]
    return DEFAULT_AGENTS.get(agent_id)


def list_agents(mode: Optional[str] = None, include_hidden: bool = False) -> List[AgentInfo]:
    """List all agents, optionally filtered by mode."""
    all_agents = {**DEFAULT_AGENTS, **_custom_agents}
    agents = []
    
    for agent in all_agents.values():
        if agent.hidden and not include_hidden:
            continue
        if mode and agent.mode != mode:
            continue
        agents.append(agent)
    
    # Sort by name, with 'build' first
    agents.sort(key=lambda a: (a.name != "build", a.name))
    return agents


def default_agent() -> AgentInfo:
    """Get the default agent (build)."""
    return DEFAULT_AGENTS["build"]


def register(agent: AgentInfo) -> None:
    """Register a custom agent."""
    _custom_agents[agent.id] = agent


def unregister(agent_id: str) -> bool:
    """Unregister a custom agent."""
    if agent_id in _custom_agents:
        del _custom_agents[agent_id]
        return True
    return False


def is_tool_allowed(agent: AgentInfo, tool_name: str) -> Literal["allow", "deny", "ask"]:
    """Check if a tool is allowed for an agent."""
    result: Literal["allow", "deny", "ask"] = "allow"
    
    for perm in agent.permissions:
        if perm.tool_name == "*" or perm.tool_name == tool_name:
            result = perm.action
    
    return result


def get_system_prompt(agent: AgentInfo) -> str:
    """Get the system prompt for an agent."""
    parts = []
    
    # Add beast mode prompt for agents with auto_continue
    if agent.auto_continue and agent.prompt:
        parts.append(agent.prompt)
    
    # Add agent description
    if agent.description:
        parts.append(f"You are the '{agent.name}' agent: {agent.description}")
    
    return "\n\n".join(parts)
