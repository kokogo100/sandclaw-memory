# ═══════════════════════════════════════════════════════════
# sandclaw-memory -- Self-Growing Tag-Dictionary RAG
#
# WHAT THIS LIBRARY DOES:
#   Gives your AI long-term memory that grows smarter over time.
#   No GPU, no vector database, no external dependencies.
#   Just pip install and go.
#
# QUICK START:
#   from sandclaw_memory import BrainMemory
#
#   brain = BrainMemory(tag_extractor=my_ai_func)
#   brain.save("User loves Python and React")
#   context = brain.recall("what does the user like?")
#   # -> Returns relevant memories as Markdown
#
# WHAT GETS EXPORTED:
#   BrainMemory   -- the main class you interact with
#   Depth         -- enum for search depth (CASUAL, STANDARD, DEEP)
#   MemoryEntry   -- dataclass representing one memory
#   SandclawError -- base exception (catch this for all errors)
#
# VERSION:
#   Reads from pyproject.toml automatically.
#   Check with: sandclaw_memory.__version__
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import logging

from sandclaw_memory.brain import BrainMemory
from sandclaw_memory.exceptions import SandclawError
from sandclaw_memory.types import Depth, MemoryEntry

# ─── NullHandler ───
# WHY: Libraries should NEVER configure logging for the developer.
# NullHandler means: "I produce log messages, but I won't print them
# unless YOU set up a handler." This prevents unwanted console spam.
#
# HOW TO SEE OUR LOGS (if you want to):
#   import logging
#   logging.basicConfig(level=logging.DEBUG)
#   # Now sandclaw-memory logs will appear in your console
# ───────────────────
logging.getLogger(__name__).addHandler(logging.NullHandler())

# ─── Version (single source of truth) ───
# WHY: The version is defined once in pyproject.toml.
# We read it at runtime so there's no risk of forgetting to
# update a hardcoded string.
# ─────────────────────────────────────────
try:
    from importlib.metadata import version

    __version__ = version("sandclaw-memory")
except Exception:
    # Not installed as a package (e.g. running from source)
    __version__ = "0.0.0-dev"

__all__ = [
    "BrainMemory",
    "Depth",
    "MemoryEntry",
    "SandclawError",
]
