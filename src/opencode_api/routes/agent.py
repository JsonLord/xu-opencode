"""
Agent routes - manage agent configurations.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List

from ..agent import (
    AgentInfo,
    get,
    list_agents,
    default_agent,
    register,
    unregister,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("", response_model=List[AgentInfo])
async def get_agents(
    mode: Optional[str] = None,
    include_hidden: bool = False
):
    """List all available agents."""
    return list_agents(mode=mode, include_hidden=include_hidden)


@router.get("/default", response_model=AgentInfo)
async def get_default_agent():
    """Get the default agent configuration."""
    return default_agent()


@router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    """Get a specific agent by ID."""
    agent = get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent


@router.post("", response_model=AgentInfo)
async def create_agent(agent: AgentInfo):
    """Register a custom agent."""
    existing = get(agent.id)
    if existing and existing.native:
        raise HTTPException(status_code=400, detail=f"Cannot override native agent: {agent.id}")
    
    register(agent)
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Unregister a custom agent."""
    agent = get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    
    if agent.native:
        raise HTTPException(status_code=400, detail=f"Cannot delete native agent: {agent_id}")
    
    unregister(agent_id)
    return {"deleted": agent_id}
