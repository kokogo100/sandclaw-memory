# ═══════════════════════════════════════════════════════════
# utils.py -- Shared Helpers
#
# WHAT THIS MODULE DOES:
#   Small utility functions and classes used by multiple modules.
#   This is the "toolbox" -- nothing here is specific to any
#   one layer of memory. Any module can import from here.
#
# WHAT'S INSIDE:
#   1. HookRegistry -- event system (before_save, after_recall, etc.)
#   2. now_iso()    -- get current time as ISO 8601 string
#   3. truncate()   -- safely shorten text with "..." marker
#   4. safe_json_loads() -- parse JSON without crashing
#
# DEPENDS ON:
#   Nothing (only Python standard library).
#   This module must NEVER import from other sandclaw_memory modules.
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

__all__ = ["HookRegistry", "now_iso", "truncate", "safe_json_loads"]

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# HookRegistry -- Event System
# ═══════════════════════════════════════════════════════════


class HookRegistry:
    """A simple event system for before/after hooks.

    HOW IT WORKS:
        You register a callback for an event name, and later
        when that event fires, all registered callbacks run.
        If a callback crashes, it gets logged but does NOT stop
        the main operation -- hooks should never break your app.

    EXAMPLE:
        hooks = HookRegistry()
        hooks.register("after_save", lambda content: print(f"Saved: {content}"))
        hooks.fire("after_save", "Hello world")
        # prints: Saved: Hello world

    SUPPORTED EVENTS (in BrainMemory):
        before_save    -- fires before content is saved
        after_save     -- fires after content is saved
        after_recall   -- fires after memories are recalled
        before_promote -- fires before L1 -> L3 promotion
        after_promote  -- fires after L1 -> L3 promotion
        after_cycle    -- fires after each polling loop cycle

    HOW TO CUSTOMIZE:
        You can use any event name you want -- the registry
        doesn't restrict names. Just make sure fire() and
        register() use the same string.
    """

    def __init__(self) -> None:
        # ─── HOW THIS WORKS ───
        # _hooks is a dict mapping event names to lists of callbacks.
        # Example: {"after_save": [fn1, fn2], "before_promote": [fn3]}
        # ───────────────────────
        self._hooks: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def register(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for an event.

        Args:
            event: Event name (e.g. "after_save").
            callback: Function to call when the event fires.
        """
        self._hooks[event].append(callback)

    def fire(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Fire an event, calling all registered callbacks.

        If a callback raises an exception, it is logged and
        skipped -- the remaining callbacks still run.
        This ensures hooks never break the main operation.

        Args:
            event: Event name to fire.
            *args: Positional arguments passed to each callback.
            **kwargs: Keyword arguments passed to each callback.
        """
        for callback in self._hooks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception:
                # ─── WHY WE SWALLOW EXCEPTIONS ───
                # Hooks are optional add-ons. If your hook crashes,
                # it should NOT prevent the core operation (save, recall, etc.)
                # from completing. We log the error so you can debug it.
                # ─────────────────────────────────
                logger.exception("Hook callback failed for event '%s'", event)


# ═══════════════════════════════════════════════════════════
# Timestamp Helper
# ═══════════════════════════════════════════════════════════


def now_iso() -> str:
    """Get the current UTC time as an ISO 8601 string.

    Returns:
        String like "2026-04-12T14:30:00+00:00"

    WHY UTC?
        Using UTC avoids timezone confusion when memories are
        created on different machines or in different timezones.
        The ISO 8601 format is universally parseable.
    """
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════
# Text Truncation
# ═══════════════════════════════════════════════════════════


def truncate(text: str, max_chars: int, suffix: str = "...") -> str:
    """Shorten text to max_chars, adding a suffix if truncated.

    Args:
        text: The text to potentially shorten.
        max_chars: Maximum character count (including suffix).
        suffix: What to append when truncated (default "...").

    Returns:
        Original text if short enough, or truncated with suffix.

    Examples:
        truncate("Hello World", 50)      -> "Hello World"
        truncate("Hello World", 8)       -> "Hello..."
        truncate("Hello World", 8, "[+]") -> "Hello[+]"

    HOW TO CUSTOMIZE:
        Change the suffix to match your needs:
          truncate(text, 100, " [read more]")
          truncate(text, 100, "")  # no suffix, just cut
    """
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix


# ═══════════════════════════════════════════════════════════
# Safe JSON Parser
# ═══════════════════════════════════════════════════════════


def safe_json_loads(text: str, default: Any = None) -> Any:
    """Parse a JSON string without raising exceptions.

    Args:
        text: The JSON string to parse.
        default: Value to return if parsing fails (default None).

    Returns:
        Parsed Python object, or default if parsing fails.

    WHY THIS EXISTS:
        AI callbacks often return JSON that might be malformed.
        Instead of crashing, we gracefully fall back to default.

    Examples:
        safe_json_loads('["react", "python"]')  -> ["react", "python"]
        safe_json_loads('not json')             -> None
        safe_json_loads('bad', default=[])      -> []
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default
