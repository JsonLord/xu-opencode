from typing import Dict, Any, List, Optional
from .tool import BaseTool
import os
import importlib.util


class ToolRegistry:
    """도구 레지스트리 - 도구 등록 및 관리"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """도구 등록"""
        self._tools[tool.id] = tool

    def get(self, tool_id: str) -> Optional[BaseTool]:
        """도구 ID로 조회"""
        return self._tools.get(tool_id)

    def list(self) -> List[BaseTool]:
        """등록된 모든 도구 목록 반환"""
        return list(self._tools.values())

    def get_schema(self) -> List[Dict[str, Any]]:
        """모든 도구의 스키마 반환"""
        return [tool.get_schema() for tool in self._tools.values()]

    def load_from_directory(self, path: str) -> None:
        """
        디렉토리에서 도구를 동적으로 로드
        (나중에 구현 가능 - 플러그인 시스템)
        """
        if not os.path.exists(path):
            raise ValueError(f"Directory not found: {path}")

        # 향후 구현: .py 파일을 스캔하고 BaseTool 서브클래스를 찾아 자동 등록
        # 현재는 placeholder
        pass


# 전역 싱글톤 인스턴스
_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """전역 레지스트리 인스턴스 반환"""
    return _registry
