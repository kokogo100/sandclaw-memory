# ═══════════════════════════════════════════════════════════
# types.py -- Core Data Types
#
# WHAT THIS MODULE DOES:
#   Defines the shared data structures used across all modules.
#   Think of this as the "vocabulary" of the library -- every
#   module speaks in these types.
#
# TWO MAIN TYPES:
#   1. Depth (enum) -- how deep to search memories
#      CASUAL   = only recent stuff (L1)
#      STANDARD = recent + summaries (L1 + L2)
#      DEEP     = everything (L1 + L2 + L3)
#
#   2. MemoryEntry (dataclass) -- one piece of memory
#      Contains: id, content, tags, source, timestamps, etc.
#
# HOW TO CUSTOMIZE:
#   You can extend Depth with your own levels if needed,
#   but the built-in three cover most use cases.
#   MemoryEntry fields are designed to be flexible --
#   use the metadata dict for any custom data.
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Depth", "MemoryEntry"]


class Depth(enum.Enum):
    """How deep the memory search should go.

    Think of it like searching a building:
      CASUAL   = check the lobby (quick, recent stuff only)
      STANDARD = check lobby + library (recent + summaries)
      DEEP     = check lobby + library + vault (everything)

    The deeper you go, the more complete the results -- but
    also the more tokens/time it costs.

    Usage:
        # Automatic detection (recommended):
        context = brain.recall("what did I do today?")  # auto-detects CASUAL

        # Manual override:
        context = brain.recall("3-month history", depth="deep")
    """

    CASUAL = "casual"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class MemoryEntry:
    """One piece of stored memory.

    This is what you get back when you search or recall memories.
    Every memory has content (the actual text), optional tags,
    and timestamps.

    Fields:
        id:           Unique identifier (from SQLite autoincrement)
        content:      The actual text content of the memory
        content_type: Category like "general", "decision", "insight"
        tags:         List of tags (e.g. ["python", "react", "bugfix"])
        source:       Where it came from ("chat", "archive", "system")
        metadata:     Any extra data you want to attach (flexible dict)
        created_at:   When this memory was first saved (ISO 8601)
        updated_at:   When this memory was last modified (ISO 8601)

    HOW TO CUSTOMIZE:
        Use the metadata dict for any domain-specific data:

            entry = MemoryEntry(
                content="Fixed login bug",
                tags=["bugfix", "auth"],
                metadata={"jira": "PROJ-123", "severity": "high"}
            )
    """

    id: int = 0
    content: str = ""
    content_type: str = "general"
    tags: list[str] = field(default_factory=list)
    source: str = "chat"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
