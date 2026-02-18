from typing import Dict, Any, List, Optional, Callable, Awaitable, Protocol, runtime_checkable
from pydantic import BaseModel
from abc import ABC, abstractmethod
from datetime import datetime


class ToolContext(BaseModel):
    session_id: str
    message_id: str
    tool_call_id: Optional[str] = None
    agent: str = "default"


class ToolResult(BaseModel):
    title: str
    output: str
    metadata: Dict[str, Any] = {}
    truncated: bool = False
    original_length: int = 0


@runtime_checkable
class Tool(Protocol):
    
    @property
    def id(self) -> str: ...
    
    @property
    def description(self) -> str: ...
    
    @property
    def parameters(self) -> Dict[str, Any]: ...
    
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult: ...


class BaseTool(ABC):
    MAX_OUTPUT_LENGTH = 50000

    def __init__(self):
        self.status: str = "pending"
        self.time_start: Optional[datetime] = None
        self.time_end: Optional[datetime] = None

    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        pass

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.id,
            "description": self.description,
            "parameters": self.parameters
        }

    def truncate_output(self, output: str) -> str:
        """출력이 MAX_OUTPUT_LENGTH를 초과하면 자르고 메시지 추가"""
        if len(output) <= self.MAX_OUTPUT_LENGTH:
            return output

        truncated = output[:self.MAX_OUTPUT_LENGTH]
        truncated += "\n\n[Output truncated...]"
        return truncated

    def update_status(self, status: str) -> None:
        """도구 상태 업데이트 (pending, running, completed, error)"""
        self.status = status
        if status == "running" and self.time_start is None:
            self.time_start = datetime.now()
        elif status in ("completed", "error") and self.time_end is None:
            self.time_end = datetime.now()


from .registry import get_registry


def register_tool(tool: BaseTool) -> None:
    """도구 등록 (호환성 함수 - ToolRegistry 사용)"""
    get_registry().register(tool)


def get_tool(tool_id: str) -> Optional[BaseTool]:
    """도구 조회 (호환성 함수 - ToolRegistry 사용)"""
    return get_registry().get(tool_id)


def list_tools() -> List[BaseTool]:
    """도구 목록 (호환성 함수 - ToolRegistry 사용)"""
    return get_registry().list()


def get_tools_schema() -> List[Dict[str, Any]]:
    """도구 스키마 목록 (호환성 함수 - ToolRegistry 사용)"""
    return get_registry().get_schema()
