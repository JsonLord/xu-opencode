from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from .tool import BaseTool, ToolContext, ToolResult
from ..core.storage import Storage


class TodoItem(BaseModel):
    id: str
    content: str
    status: str = "pending"  # pending, in_progress, completed, cancelled
    priority: str = "medium"  # high, medium, low


class TodoTool(BaseTool):
    
    @property
    def id(self) -> str:
        return "todo"
    
    @property
    def description(self) -> str:
        return (
            "Manage a todo list for tracking tasks. Use this to create, update, "
            "and track progress on multi-step tasks. Supports pending, in_progress, "
            "completed, and cancelled statuses."
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write"],
                    "description": "Action to perform: 'read' to get todos, 'write' to update todos"
                },
                "todos": {
                    "type": "array",
                    "description": "List of todos (required for 'write' action)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"]
                            },
                            "priority": {
                                "type": "string", 
                                "enum": ["high", "medium", "low"]
                            }
                        },
                        "required": ["id", "content", "status", "priority"]
                    }
                }
            },
            "required": ["action"]
        }
    
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = args["action"]
        session_id = ctx.session_id
        
        if action == "read":
            return await self._read_todos(session_id)
        elif action == "write":
            todos_data = args.get("todos", [])
            return await self._write_todos(session_id, todos_data)
        else:
            return ToolResult(
                title="Todo Error",
                output=f"Unknown action: {action}",
                metadata={"error": "invalid_action"}
            )
    
    async def _read_todos(self, session_id: str) -> ToolResult:
        todos = await Storage.read(["todo", session_id])
        
        if not todos:
            return ToolResult(
                title="Todo List",
                output="No todos found for this session.",
                metadata={"count": 0}
            )
        
        items = [TodoItem(**t) for t in todos]
        lines = self._format_todos(items)
        
        return ToolResult(
            title="Todo List",
            output="\n".join(lines),
            metadata={"count": len(items)}
        )
    
    async def _write_todos(self, session_id: str, todos_data: List[Dict]) -> ToolResult:
        items = [TodoItem(**t) for t in todos_data]
        await Storage.write(["todo", session_id], [t.model_dump() for t in items])
        
        lines = self._format_todos(items)
        
        return ToolResult(
            title="Todo List Updated",
            output="\n".join(lines),
            metadata={"count": len(items)}
        )
    
    def _format_todos(self, items: List[TodoItem]) -> List[str]:
        status_icons = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "completed": "[x]",
            "cancelled": "[-]"
        }
        priority_icons = {
            "high": "!!!",
            "medium": "!!",
            "low": "!"
        }
        
        lines = []
        for item in items:
            icon = status_icons.get(item.status, "[ ]")
            priority = priority_icons.get(item.priority, "")
            lines.append(f"{icon} {priority} {item.content} (id: {item.id})")
        
        return lines if lines else ["No todos."]
