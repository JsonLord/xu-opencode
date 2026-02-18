"""
Session processor for managing agentic loop execution.
"""

from typing import Optional, Dict, Any, AsyncIterator, List
from pydantic import BaseModel
from datetime import datetime
import asyncio

from ..provider.provider import StreamChunk


class DoomLoopDetector:
    """동일 도구 + 동일 인자 연속 호출을 감지하여 무한 루프 방지

    원본 opencode와 동일하게 도구 이름과 인자를 모두 비교합니다.
    같은 도구라도 인자가 다르면 정상적인 반복으로 판단합니다.
    """

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.history: List[tuple[str, str]] = []  # (tool_name, args_hash)

    def record(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> bool:
        """도구 호출을 기록하고 doom loop 감지 시 True 반환

        Args:
            tool_name: 도구 이름
            args: 도구 인자 (없으면 빈 dict로 처리)

        Returns:
            True if doom loop detected, False otherwise
        """
        import json
        import hashlib

        # 인자를 정규화하여 해시 생성 (원본처럼 JSON 비교)
        args_dict = args or {}
        args_str = json.dumps(args_dict, sort_keys=True, default=str)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]

        call_signature = (tool_name, args_hash)
        self.history.append(call_signature)

        # 최근 threshold개가 모두 같은 (도구 + 인자)인지 확인
        if len(self.history) >= self.threshold:
            recent = self.history[-self.threshold:]
            if len(set(recent)) == 1:  # 튜플 비교 (도구+인자)
                return True

        return False

    def reset(self):
        self.history = []


class RetryConfig(BaseModel):
    """재시도 설정"""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0
    exponential_base: float = 2.0


class StepInfo(BaseModel):
    """스텝 정보"""
    step: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    tool_calls: List[str] = []
    status: str = "running"  # running, completed, error, doom_loop


class SessionProcessor:
    """
    Agentic loop 실행을 관리하는 프로세서.

    Features:
    - Doom loop 방지 (동일 도구 연속 호출 감지)
    - 자동 재시도 (exponential backoff)
    - 스텝 추적 (step-start, step-finish 이벤트)
    """

    _processors: Dict[str, "SessionProcessor"] = {}

    def __init__(self, session_id: str, max_steps: int = 50, doom_threshold: int = 3):
        self.session_id = session_id
        self.max_steps = max_steps
        self.doom_detector = DoomLoopDetector(threshold=doom_threshold)
        self.retry_config = RetryConfig()
        self.steps: List[StepInfo] = []
        self.current_step: Optional[StepInfo] = None
        self.aborted = False

    @classmethod
    def get_or_create(cls, session_id: str, **kwargs) -> "SessionProcessor":
        if session_id not in cls._processors:
            cls._processors[session_id] = cls(session_id, **kwargs)
        return cls._processors[session_id]

    @classmethod
    def remove(cls, session_id: str) -> None:
        if session_id in cls._processors:
            del cls._processors[session_id]

    def start_step(self) -> StepInfo:
        """새 스텝 시작"""
        step_num = len(self.steps) + 1
        self.current_step = StepInfo(
            step=step_num,
            started_at=datetime.utcnow()
        )
        self.steps.append(self.current_step)
        return self.current_step

    def finish_step(self, status: str = "completed") -> StepInfo:
        """현재 스텝 완료"""
        if self.current_step:
            self.current_step.finished_at = datetime.utcnow()
            self.current_step.status = status
        return self.current_step

    def record_tool_call(self, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> bool:
        """도구 호출 기록, doom loop 감지 시 True 반환

        Args:
            tool_name: 도구 이름
            tool_args: 도구 인자 (doom loop 판별에 사용)

        Returns:
            True if doom loop detected, False otherwise
        """
        if self.current_step:
            self.current_step.tool_calls.append(tool_name)
        return self.doom_detector.record(tool_name, tool_args)

    def is_doom_loop(self) -> bool:
        """현재 doom loop 상태인지 확인"""
        return len(self.doom_detector.history) >= self.doom_detector.threshold and \
               len(set(self.doom_detector.history[-self.doom_detector.threshold:])) == 1

    def should_continue(self) -> bool:
        """루프 계속 여부"""
        if self.aborted:
            return False
        if len(self.steps) >= self.max_steps:
            return False
        if self.is_doom_loop():
            return False
        return True

    def abort(self) -> None:
        """프로세서 중단"""
        self.aborted = True

    async def calculate_retry_delay(self, attempt: int) -> float:
        """exponential backoff 딜레이 계산"""
        delay = self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt)
        return min(delay, self.retry_config.max_delay)

    async def retry_with_backoff(self, func, *args, **kwargs):
        """exponential backoff으로 함수 재시도"""
        last_error = None

        for attempt in range(self.retry_config.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.retry_config.max_retries - 1:
                    delay = await self.calculate_retry_delay(attempt)
                    await asyncio.sleep(delay)

        raise last_error

    def get_summary(self) -> Dict[str, Any]:
        """프로세서 상태 요약"""
        return {
            "session_id": self.session_id,
            "total_steps": len(self.steps),
            "max_steps": self.max_steps,
            "aborted": self.aborted,
            "doom_loop_detected": self.is_doom_loop(),
            "steps": [
                {
                    "step": s.step,
                    "status": s.status,
                    "tool_calls": s.tool_calls,
                    "duration": (s.finished_at - s.started_at).total_seconds() if s.finished_at else None
                }
                for s in self.steps
            ]
        }
