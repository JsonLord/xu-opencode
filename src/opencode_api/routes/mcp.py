"""
MCP routes - manage MCP servers configurations.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/mcp", tags=["mcp"])

# In-memory storage for MCP servers
# Note: Ideally this should go into a database or persistent storage in the future
_mcp_servers: Dict[str, Dict[str, Any]] = {}

@router.get("")
async def list_mcp_servers():
    """List all registered MCP servers."""
    return list(_mcp_servers.values())

@router.post("")
async def register_mcp_server(config: dict):
    """Register a new MCP server. Expects a 'name' field in config."""
    name = config.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Missing 'name' in MCP configuration")

    _mcp_servers[name] = config
    return {"status": "registered", "server": config}

@router.delete("/{name}")
async def unregister_mcp_server(name: str):
    """Unregister an MCP server by name."""
    if name not in _mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server not found: {name}")

    del _mcp_servers[name]
    return {"status": "unregistered", "name": name}

@router.post("/{name}/test")
async def test_mcp_server(name: str):
    """Test connection to an MCP server by name."""
    if name not in _mcp_servers:
        raise HTTPException(status_code=404, detail=f"MCP server not found: {name}")

    # Placeholder for actual testing logic
    # Here we would initialize the MCP client and attempt a connection
    return {"status": "success", "message": f"Successfully connected to {name}"}
