"""Event bus for OpenCode API - Pub/Sub system for real-time events"""

from typing import TypeVar, Generic, Callable, Dict, List, Any, Optional, Awaitable
from pydantic import BaseModel
import asyncio
from dataclasses import dataclass, field
import uuid


T = TypeVar("T", bound=BaseModel)


@dataclass
class Event(Generic[T]):
    """Event definition with type and payload schema"""
    type: str
    payload_type: type[T]
    
    def create(self, payload: T) -> "EventInstance":
        """Create an event instance"""
        return EventInstance(
            type=self.type,
            payload=payload.model_dump() if isinstance(payload, BaseModel) else payload
        )


@dataclass
class EventInstance:
    """An actual event instance with data"""
    type: str
    payload: Dict[str, Any]


class Bus:
    """
    Simple pub/sub event bus for real-time updates.
    Supports both sync and async subscribers.
    """
    
    _subscribers: Dict[str, List[Callable]] = {}
    _all_subscribers: List[Callable] = []
    _lock = asyncio.Lock()
    
    @classmethod
    async def publish(cls, event: Event | str, payload: BaseModel | Dict[str, Any]) -> None:
        """Publish an event to all subscribers. Event can be Event object or string type."""
        if isinstance(payload, BaseModel):
            payload_dict = payload.model_dump()
        else:
            payload_dict = payload
        
        event_type = event.type if isinstance(event, Event) else event
        instance = EventInstance(type=event_type, payload=payload_dict)
        
        async with cls._lock:
            # Notify type-specific subscribers
            for callback in cls._subscribers.get(event_type, []):
                try:
                    result = callback(instance)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    print(f"Error in event subscriber: {e}")
            
            # Notify all-event subscribers
            for callback in cls._all_subscribers:
                try:
                    result = callback(instance)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    print(f"Error in all-event subscriber: {e}")
    
    @classmethod
    def subscribe(cls, event_type: str, callback: Callable) -> Callable[[], None]:
        """Subscribe to a specific event type. Returns unsubscribe function."""
        if event_type not in cls._subscribers:
            cls._subscribers[event_type] = []
        cls._subscribers[event_type].append(callback)
        
        def unsubscribe():
            cls._subscribers[event_type].remove(callback)
        
        return unsubscribe
    
    @classmethod
    def subscribe_all(cls, callback: Callable) -> Callable[[], None]:
        """Subscribe to all events. Returns unsubscribe function."""
        cls._all_subscribers.append(callback)
        
        def unsubscribe():
            cls._all_subscribers.remove(callback)
        
        return unsubscribe
    
    @classmethod
    async def clear(cls) -> None:
        """Clear all subscribers"""
        async with cls._lock:
            cls._subscribers.clear()
            cls._all_subscribers.clear()


# Pre-defined events (matching TypeScript opencode events)
class SessionPayload(BaseModel):
    """Payload for session events"""
    id: str
    title: Optional[str] = None
    
class MessagePayload(BaseModel):
    """Payload for message events"""
    session_id: str
    message_id: str
    
class PartPayload(BaseModel):
    """Payload for message part events"""
    session_id: str
    message_id: str
    part_id: str
    delta: Optional[str] = None

class StepPayload(BaseModel):
    """Payload for agentic loop step events"""
    session_id: str
    step: int
    max_steps: int

class ToolStatePayload(BaseModel):
    """Payload for tool state change events"""
    session_id: str
    message_id: str
    part_id: str
    tool_name: str
    status: str  # "pending", "running", "completed", "error"
    time_start: Optional[str] = None
    time_end: Optional[str] = None


# Event definitions
SESSION_CREATED = Event(type="session.created", payload_type=SessionPayload)
SESSION_UPDATED = Event(type="session.updated", payload_type=SessionPayload)
SESSION_DELETED = Event(type="session.deleted", payload_type=SessionPayload)

MESSAGE_UPDATED = Event(type="message.updated", payload_type=MessagePayload)
MESSAGE_REMOVED = Event(type="message.removed", payload_type=MessagePayload)

PART_UPDATED = Event(type="part.updated", payload_type=PartPayload)
PART_REMOVED = Event(type="part.removed", payload_type=PartPayload)

STEP_STARTED = Event(type="step.started", payload_type=StepPayload)
STEP_FINISHED = Event(type="step.finished", payload_type=StepPayload)

TOOL_STATE_CHANGED = Event(type="tool.state.changed", payload_type=ToolStatePayload)
