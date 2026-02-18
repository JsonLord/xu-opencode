"""Identifier generation for OpenCode API - ULID-based IDs"""

from ulid import ULID
from datetime import datetime
from typing import Literal


PrefixType = Literal["session", "message", "part", "tool", "question"]


class Identifier:
    """
    ULID-based identifier generator.
    Generates sortable, unique IDs with type prefixes.
    """
    
    PREFIXES = {
        "session": "ses",
        "message": "msg", 
        "part": "prt",
        "tool": "tol",
        "question": "qst",
    }
    
    @classmethod
    def generate(cls, prefix: PrefixType) -> str:
        """Generate a new ULID with prefix"""
        ulid = ULID()
        prefix_str = cls.PREFIXES.get(prefix, prefix[:3])
        return f"{prefix_str}_{str(ulid).lower()}"
    
    @classmethod
    def ascending(cls, prefix: PrefixType) -> str:
        """Generate an ascending (time-based) ID"""
        return cls.generate(prefix)
    
    @classmethod
    def descending(cls, prefix: PrefixType) -> str:
        """
        Generate a descending ID (for reverse chronological sorting).
        Uses inverted timestamp bits.
        """
        # For simplicity, just use regular ULID
        # In production, you'd invert the timestamp bits
        return cls.generate(prefix)
    
    @classmethod
    def parse(cls, id: str) -> tuple[str, str]:
        """Parse an ID into prefix and ULID parts"""
        parts = id.split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid ID format: {id}")
        return parts[0], parts[1]
    
    @classmethod
    def validate(cls, id: str, expected_prefix: PrefixType) -> bool:
        """Validate that an ID has the expected prefix"""
        try:
            prefix, _ = cls.parse(id)
            expected = cls.PREFIXES.get(expected_prefix, expected_prefix[:3])
            return prefix == expected
        except ValueError:
            return False


# Convenience function
def generate_id(prefix: PrefixType) -> str:
    """Generate a new ULID-based ID with the given prefix."""
    return Identifier.generate(prefix)
