"""Storage module for OpenCode API - In-memory with optional file persistence"""

from typing import TypeVar, Generic, Optional, Dict, Any, List, AsyncIterator
from pydantic import BaseModel
import json
import os
from pathlib import Path
import asyncio
from .config import settings

T = TypeVar("T", bound=BaseModel)


class NotFoundError(Exception):
    """Raised when a storage item is not found"""
    def __init__(self, key: List[str]):
        self.key = key
        super().__init__(f"Not found: {'/'.join(key)}")


class Storage:
    """
    Simple storage system using in-memory dict with optional file persistence.
    Keys are lists of strings that form a path (e.g., ["session", "project1", "ses_123"])
    """
    
    _data: Dict[str, Any] = {}
    _lock = asyncio.Lock()
    
    @classmethod
    def _key_to_path(cls, key: List[str]) -> str:
        """Convert key list to storage path"""
        return "/".join(key)
    
    @classmethod
    def _file_path(cls, key: List[str]) -> Path:
        """Get file path for persistent storage"""
        return Path(settings.storage_path) / "/".join(key[:-1]) / f"{key[-1]}.json"
    
    @classmethod
    async def write(cls, key: List[str], data: BaseModel | Dict[str, Any]) -> None:
        """Write data to storage"""
        path = cls._key_to_path(key)
        
        if isinstance(data, BaseModel):
            value = data.model_dump()
        else:
            value = data
        
        async with cls._lock:
            cls._data[path] = value
            
            # Persist to file
            file_path = cls._file_path(key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(value, default=str))
    
    @classmethod
    async def read(cls, key: List[str], model: type[T] = None) -> Optional[T | Dict[str, Any]]:
        """Read data from storage"""
        path = cls._key_to_path(key)
        
        async with cls._lock:
            # Check in-memory first
            if path in cls._data:
                data = cls._data[path]
                if model:
                    return model(**data)
                return data
            
            # Check file
            file_path = cls._file_path(key)
            if file_path.exists():
                data = json.loads(file_path.read_text())
                cls._data[path] = data
                if model:
                    return model(**data)
                return data
        
        return None
    
    @classmethod
    async def read_or_raise(cls, key: List[str], model: type[T] = None) -> T | Dict[str, Any]:
        """Read data from storage or raise NotFoundError"""
        result = await cls.read(key, model)
        if result is None:
            raise NotFoundError(key)
        return result
    
    @classmethod
    async def update(cls, key: List[str], updater: callable, model: type[T] = None) -> T | Dict[str, Any]:
        """Update data in storage using an updater function"""
        data = await cls.read_or_raise(key, model)
        
        if isinstance(data, BaseModel):
            data_dict = data.model_dump()
            updater(data_dict)
            await cls.write(key, data_dict)
            if model:
                return model(**data_dict)
            return data_dict
        else:
            updater(data)
            await cls.write(key, data)
            return data
    
    @classmethod
    async def remove(cls, key: List[str]) -> None:
        """Remove data from storage"""
        path = cls._key_to_path(key)
        
        async with cls._lock:
            cls._data.pop(path, None)
            
            file_path = cls._file_path(key)
            if file_path.exists():
                file_path.unlink()
    
    @classmethod
    async def list(cls, prefix: List[str]) -> List[List[str]]:
        """List all keys under a prefix"""
        prefix_path = cls._key_to_path(prefix)
        results = []
        
        async with cls._lock:
            # Check in-memory
            for key in cls._data.keys():
                if key.startswith(prefix_path + "/"):
                    results.append(key.split("/"))
            
            # Check files
            dir_path = Path(settings.storage_path) / "/".join(prefix)
            if dir_path.exists():
                for file_path in dir_path.glob("*.json"):
                    key = prefix + [file_path.stem]
                    if key not in results:
                        results.append(key)
        
        return results
    
    @classmethod
    async def clear(cls) -> None:
        """Clear all storage"""
        async with cls._lock:
            cls._data.clear()
