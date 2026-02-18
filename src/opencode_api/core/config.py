"""Configuration management for OpenCode API"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import os


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider"""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    provider_id: str = "blablador"
    model_id: str = "alias-large"


class Settings(BaseSettings):
    """Application settings loaded from environment"""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 7860
    debug: bool = False
    
    # Default model
    default_provider: str = "blablador"
    default_model: str = "alias-large"
    
    # API Keys (loaded from environment)
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    blablador_api_key: Optional[str] = Field(default=None, alias="BLABLADOR_API_KEY")
    
    # Storage
    storage_path: str = Field(default="/app", alias="OPENCODE_STORAGE_PATH")
    
    # Security
    server_password: Optional[str] = Field(default=None, alias="OPENCODE_SERVER_PASSWORD")
    token: Optional[str] = Field(default=None, alias="TOKEN")
    
    # Supabase
    supabase_url: Optional[str] = Field(default=None, alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_anon_key: Optional[str] = Field(default=None, alias="NEXT_PUBLIC_SUPABASE_ANON_KEY")
    supabase_service_key: Optional[str] = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: Optional[str] = Field(default=None, alias="SUPABASE_JWT_SECRET")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class Config(BaseModel):
    """Runtime configuration"""
    
    model: ModelConfig = Field(default_factory=ModelConfig)
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    disabled_providers: List[str] = Field(default_factory=list)
    enabled_providers: Optional[List[str]] = None
    
    @classmethod
    def get(cls) -> "Config":
        """Get the current configuration"""
        return _config
    
    @classmethod
    def update(cls, updates: Dict[str, Any]) -> "Config":
        """Update configuration"""
        global _config
        data = _config.model_dump()
        data.update(updates)
        _config = Config(**data)
        return _config


# Global instances
settings = Settings()
_config = Config()


def get_api_key(provider_id: str) -> Optional[str]:
    """Get API key for a provider from settings or config"""
    # Check environment-based settings first
    key_map = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "google": settings.google_api_key,
        "blablador": settings.blablador_api_key,
    }
    
    if provider_id in key_map:
        return key_map[provider_id]
    
    # Check provider config
    provider_config = _config.providers.get(provider_id)
    if provider_config:
        return provider_config.api_key
    
    return None
