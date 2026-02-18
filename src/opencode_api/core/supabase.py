from typing import Optional
from supabase import create_client, Client
from .config import settings

_client: Optional[Client] = None


def get_client() -> Optional[Client]:
    global _client
    
    if _client is not None:
        return _client
    
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    
    _client = create_client(
        settings.supabase_url,
        settings.supabase_service_key
    )
    return _client


def is_enabled() -> bool:
    return settings.supabase_url is not None and settings.supabase_service_key is not None
