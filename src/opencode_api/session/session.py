from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from ..core.storage import Storage, NotFoundError
from ..core.bus import Bus, SESSION_CREATED, SESSION_UPDATED, SESSION_DELETED, SessionPayload
from ..core.identifier import Identifier
from ..core.supabase import get_client, is_enabled as supabase_enabled


class SessionInfo(BaseModel):
    id: str
    user_id: Optional[str] = None
    title: str
    created_at: datetime
    updated_at: datetime
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    agent_id: Optional[str] = None
    
    
class SessionCreate(BaseModel):
    title: Optional[str] = None
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    agent_id: Optional[str] = None


class Session:
    
    @staticmethod
    async def create(data: Optional[SessionCreate] = None, user_id: Optional[str] = None) -> SessionInfo:
        session_id = Identifier.generate("session")
        now = datetime.utcnow()
        
        info = SessionInfo(
            id=session_id,
            user_id=user_id,
            title=data.title if data and data.title else f"Session {now.isoformat()}",
            created_at=now,
            updated_at=now,
            provider_id=data.provider_id if data else None,
            model_id=data.model_id if data else None,
            agent_id=data.agent_id if data else "build",
        )
        
        if supabase_enabled() and user_id:
            client = get_client()
            client.table("opencode_sessions").insert({
                "id": session_id,
                "user_id": user_id,
                "title": info.title,
                "agent_id": info.agent_id,
                "provider_id": info.provider_id,
                "model_id": info.model_id,
            }).execute()
        else:
            await Storage.write(["session", session_id], info)
        
        await Bus.publish(SESSION_CREATED, SessionPayload(id=session_id, title=info.title))
        return info
    
    @staticmethod
    async def get(session_id: str, user_id: Optional[str] = None) -> SessionInfo:
        if supabase_enabled() and user_id:
            client = get_client()
            result = client.table("opencode_sessions").select("*").eq("id", session_id).eq("user_id", user_id).single().execute()
            if not result.data:
                raise NotFoundError(["session", session_id])
            return SessionInfo(
                id=result.data["id"],
                user_id=result.data["user_id"],
                title=result.data["title"],
                created_at=result.data["created_at"],
                updated_at=result.data["updated_at"],
                provider_id=result.data.get("provider_id"),
                model_id=result.data.get("model_id"),
                agent_id=result.data.get("agent_id"),
            )
        
        data = await Storage.read(["session", session_id])
        if not data:
            raise NotFoundError(["session", session_id])
        return SessionInfo(**data)
    
    @staticmethod
    async def update(session_id: str, updates: Dict[str, Any], user_id: Optional[str] = None) -> SessionInfo:
        updates["updated_at"] = datetime.utcnow().isoformat()
        
        if supabase_enabled() and user_id:
            client = get_client()
            result = client.table("opencode_sessions").update(updates).eq("id", session_id).eq("user_id", user_id).execute()
            if not result.data:
                raise NotFoundError(["session", session_id])
            return await Session.get(session_id, user_id)
        
        def updater(data: Dict[str, Any]):
            data.update(updates)
        
        data = await Storage.update(["session", session_id], updater)
        info = SessionInfo(**data)
        await Bus.publish(SESSION_UPDATED, SessionPayload(id=session_id, title=info.title))
        return info
    
    @staticmethod
    async def delete(session_id: str, user_id: Optional[str] = None) -> bool:
        if supabase_enabled() and user_id:
            client = get_client()
            client.table("opencode_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
            await Bus.publish(SESSION_DELETED, SessionPayload(id=session_id, title=""))
            return True
        
        info = await Session.get(session_id)
        message_keys = await Storage.list(["message", session_id])
        for key in message_keys:
            await Storage.remove(key)
        
        await Storage.remove(["session", session_id])
        await Bus.publish(SESSION_DELETED, SessionPayload(id=session_id, title=info.title))
        return True
    
    @staticmethod
    async def list(limit: Optional[int] = None, user_id: Optional[str] = None) -> List[SessionInfo]:
        if supabase_enabled() and user_id:
            client = get_client()
            query = client.table("opencode_sessions").select("*").eq("user_id", user_id).order("updated_at", desc=True)
            if limit:
                query = query.limit(limit)
            result = query.execute()
            return [
                SessionInfo(
                    id=row["id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    provider_id=row.get("provider_id"),
                    model_id=row.get("model_id"),
                    agent_id=row.get("agent_id"),
                )
                for row in result.data
            ]
        
        session_keys = await Storage.list(["session"])
        sessions = []
        
        for key in session_keys:
            if limit and len(sessions) >= limit:
                break
            data = await Storage.read(key)
            if data:
                sessions.append(SessionInfo(**data))
        
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions
    
    @staticmethod
    async def touch(session_id: str, user_id: Optional[str] = None) -> None:
        await Session.update(session_id, {}, user_id)
