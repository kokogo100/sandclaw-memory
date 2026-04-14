# ═══════════════════════════════════════════════════════════
# brain.py -- BrainMemory (The Orchestrator)
#
# WHAT THIS MODULE DOES:
#   This is the MAIN CLASS you interact with.
#   It connects all three memory layers (L1, L2, L3),
#   the dispatcher, loader, and renderer into one simple API.
#
# ANALOGY:
#   BrainMemory = the receptionist at a 3-story building.
#   You say what you want, and they know which floor to go to.
#
#   brain.save("...")  -> routes to the right layer
#   brain.recall("..") -> figures out depth, loads, renders
#   brain.start_polling() -> background worker for tag extraction
#
# KEY DESIGN DECISIONS:
#   1. tag_extractor is REQUIRED (not optional)
#      -> Without it, the "self-growing" feature doesn't work
#      -> If you pass None, you get a clear ConfigurationError
#
#   2. Polling loop runs in a background thread
#      -> Processes tag_queue, promotes content, cleans up
#      -> Default: every 15 seconds
#      -> You can also call run_maintenance() manually
#
#   3. Context Manager support (with statement)
#      -> Automatically stops polling and closes DB on exit
#      -> Prevents resource leaks
#
# HOW TO CUSTOMIZE:
#   # Change polling interval:
#   brain = BrainMemory(tag_extractor=my_func, polling_interval=60)
#
#   # Manual maintenance (no polling):
#   brain = BrainMemory(tag_extractor=my_func)
#   brain.run_maintenance()  # call when you want
#
# DEPENDS ON:
#   All other modules (this is the top-level orchestrator)
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sandclaw_memory.dispatcher import IntentDispatcher
from sandclaw_memory.exceptions import ConfigurationError
from sandclaw_memory.loader import TieredLoader
from sandclaw_memory.permanent import ArchiveMemory
from sandclaw_memory.renderer import MarkdownRenderer
from sandclaw_memory.session import SessionMemory
from sandclaw_memory.summary import SummaryMemory
from sandclaw_memory.types import Depth, MemoryEntry
from sandclaw_memory.utils import HookRegistry, now_iso

__all__ = ["BrainMemory"]

logger = logging.getLogger(__name__)


class BrainMemory:
    """The main orchestrator -- connects all memory layers.

    This is the only class most users need to interact with.
    It manages L1 (session), L2 (summary), and L3 (archive),
    plus automatic depth detection, tag extraction, and more.

    Quick start:
        from sandclaw_memory import BrainMemory

        def my_tag_extractor(text):
            # Call your AI here (OpenAI, Claude, etc.)
            return ["tag1", "tag2"]

        with BrainMemory(tag_extractor=my_tag_extractor) as brain:
            brain.start_polling()
            brain.save("User likes Python and React")
            context = brain.recall("what does the user like?")
    """

    def __init__(
        self,
        db_path: str = "./memory",
        # --- Layer settings ---
        rolling_days: int = 3,
        summary_days: int = 30,
        max_context_chars: int = 15_000,
        content_truncate: int = 450,
        summary_truncate: int = 2500,
        # --- AI callbacks (tag_extractor is REQUIRED) ---
        tag_extractor: Callable[[str], list[str]] | None = None,
        promote_checker: Callable[[str], bool] | None = None,
        depth_detector: Callable[[str], str] | None = None,
        duplicate_checker: Callable[[str, str], bool] | None = None,
        conflict_resolver: Callable[[str, str], str] | None = None,
        # --- Polling ---
        polling_interval: int = 15,
        # --- Security ---
        encryption_key: str | None = None,
    ) -> None:
        """Initialize BrainMemory.

        Args:
            db_path: Base directory for all memory files.
            rolling_days: L1 session log retention (default 3 days).
            summary_days: L2 summary period (default 30 days).
            max_context_chars: Context budget for LLM injection (default 15KB).
            content_truncate: Max chars per memory in render (default 450).
            summary_truncate: Max chars for summary render (default 2500).
            tag_extractor: REQUIRED. Function that extracts tags from text.
                Must return list[str]. This is the core of self-growing tags.
            promote_checker: Optional. Decides if L1 content should be
                promoted to L3. Returns True to promote. Default: length > 200.
            depth_detector: Optional. AI-based depth detection.
                Returns "casual", "standard", or "deep". Default: keywords.
            duplicate_checker: Optional. Returns True if two texts are duplicates.
                Default: difflib > 0.85 similarity.
            conflict_resolver: Optional. Returns resolved text when conflict detected.
                Default: keep the newer text.
            polling_interval: Seconds between maintenance cycles (default 15).
            encryption_key: Optional SQLCipher key for L3 database.

        Raises:
            ConfigurationError: If tag_extractor is None.

        HOW TO CUSTOMIZE:
            # Minimal setup (just tag_extractor):
            brain = BrainMemory(tag_extractor=my_func)

            # Full customization:
            brain = BrainMemory(
                db_path="./my_memory",
                rolling_days=7,
                tag_extractor=my_tagger,
                promote_checker=my_promoter,
                polling_interval=60,
            )
        """
        # ─── Validate required callback ───
        if tag_extractor is None:
            raise ConfigurationError(
                "tag_extractor is required but got None. "
                "Provide a callable that extracts tags from text: "
                "BrainMemory(tag_extractor=my_func). "
                "See examples/basic_usage.py for reference."
            )

        self._db_path = db_path
        self._polling_interval = polling_interval
        self._promote_checker = promote_checker or self._default_promote_checker
        self._hooks = HookRegistry()

        # ─── Initialize layers ───
        # L1: Session (Markdown logs)
        self._session = SessionMemory(
            base_path=db_path,
            rolling_days=rolling_days,
            max_context_chars=max_context_chars,
        )

        # L3: Archive (SQLite + FTS5)
        archive_db = str(Path(db_path) / "archive.db")
        self._archive = ArchiveMemory(
            db_path=archive_db,
            tag_extractor=tag_extractor,
            duplicate_checker=duplicate_checker,
            conflict_resolver=conflict_resolver,
            encryption_key=encryption_key,
        )

        # L2: Summary
        self._summary = SummaryMemory(summary_days=summary_days)

        # Dispatcher + Loader + Renderer
        self._dispatcher = IntentDispatcher(depth_detector=depth_detector)
        self._loader = TieredLoader(max_context_chars=max_context_chars)
        self._renderer = MarkdownRenderer(
            content_truncate=content_truncate,
            summary_truncate=summary_truncate,
        )

        # ─── Polling state ───
        self._polling_timer: threading.Timer | None = None
        self._polling_active = False

        logger.info("BrainMemory initialized at %s", db_path)

    # ═══════════════════════════════════════════════════════════
    # Context Manager (with statement)
    # ═══════════════════════════════════════════════════════════

    def __enter__(self) -> BrainMemory:
        """Enable 'with BrainMemory(...) as brain:' usage."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Auto-cleanup: stop polling, close database.

        WHY THIS MATTERS:
            Without this, forgetting to call close() would leave
            the polling thread running forever and the database
            connection open. The 'with' statement prevents this.
        """
        self.close()
        return False  # don't suppress exceptions

    # ═══════════════════════════════════════════════════════════
    # Core API
    # ═══════════════════════════════════════════════════════════

    def save(
        self,
        content: str,
        source: str = "chat",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save content to the appropriate memory layer.

        Args:
            content: The text to save.
            source: Where it came from.
                "chat" -> L1 only (conversation log)
                "archive" -> L1 + L3 (permanent storage)
                Any other value -> L1 only
            tags: Optional pre-defined tags (for L3).
            metadata: Optional extra data dict.

        HOW IT WORKS:
            1. Fire "before_save" hook
            2. Save to L1 (always -- it's a conversation log)
            3. If source="archive" or content passes promote_checker:
               Also save to L3 (permanent, with tag extraction)
            4. Fire "after_save" hook

        HOW TO CUSTOMIZE:
            # Save a regular conversation:
            brain.save("User: Hi\\nAI: Hello!")

            # Force permanent storage:
            brain.save("Important decision: use React", source="archive")

            # With explicit tags:
            brain.save("Python tutorial", source="archive", tags=["python"])
        """
        self._hooks.fire("before_save", content, source)

        # ─── Always save to L1 (conversation log) ───
        self._session.save_entry(content, entry_type=source)

        # ─── Promote to L3 if appropriate ───
        if source == "archive" or self._should_promote(content):
            self._hooks.fire("before_promote", content)
            mem_id = self._archive.save(
                content=content,
                tags=tags,
                metadata=metadata,
            )
            self._hooks.fire("after_promote", content, mem_id)

        self._hooks.fire("after_save", content, source)

    def recall(self, query: str = "", depth: str | None = None) -> str:
        """Recall relevant memories for a query.

        Args:
            query: The user's question or search text.
            depth: Optional manual depth override ("casual", "standard", "deep").
                If None, the dispatcher auto-detects from the query.

        Returns:
            Markdown string with relevant memories, ready for LLM injection.

        HOW IT WORKS:
            1. Detect depth (auto or manual)
            2. Load memories from appropriate layers
            3. Fire "after_recall" hook
            4. Return assembled Markdown

        Example:
            context = brain.recall("what did I decide about the project?")
            # Dispatcher detects DEEP -> loads L1 + L2 + L3
            # Returns: Markdown with session + summary + archive results
        """
        # ─── Detect depth ───
        detected = Depth(depth.lower()) if depth is not None else self._dispatcher.detect(query)

        # ─── Load from layers ───
        result = self._loader.load(
            depth=detected,
            query=query,
            session=self._session,
            summary=self._summary,
            archive=self._archive,
        )

        self._hooks.fire("after_recall", query, detected.value, result)
        return result

    def promote(self, content: str, tags: list[str] | None = None) -> int:
        """Manually promote content to L3 permanent storage.

        Args:
            content: The text to save permanently.
            tags: Optional tags.

        Returns:
            The memory ID in L3 (-1 if duplicate).
        """
        self._hooks.fire("before_promote", content)
        mem_id = self._archive.save(content=content, tags=tags)
        self._hooks.fire("after_promote", content, mem_id)
        return mem_id

    def summarize(self, llm_callback: Callable[[str], str] | None = None) -> str:
        """Generate a 30-day summary.

        Args:
            llm_callback: AI function to generate the summary.
                If None, uses a simple fallback concatenation.

        Returns:
            The generated summary text.
        """
        data = self._summary.collect_data(self._session, self._archive)
        return self._summary.generate(data, llm_callback=llm_callback)

    def search(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        """Search L3 permanent memories.

        Args:
            query: Search text.
            limit: Max results.

        Returns:
            List of MemoryEntry objects.
        """
        return self._archive.search(query, limit=limit)

    # ═══════════════════════════════════════════════════════════
    # Polling Loop
    # ═══════════════════════════════════════════════════════════

    def start_polling(self) -> None:
        """Start the background maintenance loop.

        The loop runs every polling_interval seconds and:
        1. Processes tag_queue (AI tag extraction)
        2. Promotes important L1 content to L3
        3. Cleans up old L1 logs
        4. Fires "after_cycle" event

        HOW TO CUSTOMIZE:
            # Change interval at creation:
            brain = BrainMemory(tag_extractor=..., polling_interval=60)

            # Or don't use polling at all:
            brain = BrainMemory(tag_extractor=...)
            brain.run_maintenance()  # call manually when needed
        """
        if self._polling_active:
            return

        self._polling_active = True
        self._schedule_next_cycle()
        logger.info("Polling started (interval: %ds)", self._polling_interval)

    def stop_polling(self) -> None:
        """Stop the background maintenance loop."""
        self._polling_active = False
        if self._polling_timer is not None:
            self._polling_timer.cancel()
            self._polling_timer = None
        logger.info("Polling stopped")

    @property
    def is_polling(self) -> bool:
        """Check if the polling loop is active."""
        return self._polling_active

    def _schedule_next_cycle(self) -> None:
        """Schedule the next polling cycle."""
        if not self._polling_active:
            return

        self._polling_timer = threading.Timer(
            self._polling_interval, self._run_cycle
        )
        self._polling_timer.daemon = True
        self._polling_timer.start()

    def _run_cycle(self) -> None:
        """Execute one maintenance cycle."""
        stats: dict[str, Any] = {
            "tags_processed": 0,
            "promoted": 0,
            "cleaned": 0,
        }

        try:
            # 1. Process tag queue (AI extraction)
            stats["tags_processed"] = self._archive.process_tag_queue()

            # 2. Cleanup old L1 logs
            stats["cleaned"] = self._session.cleanup()

        except Exception:
            logger.exception("Polling cycle failed")

        self._hooks.fire("after_cycle", stats)

        # Schedule next cycle
        self._schedule_next_cycle()

    # ═══════════════════════════════════════════════════════════
    # Maintenance (manual)
    # ═══════════════════════════════════════════════════════════

    def cleanup(self, older_than_days: int | None = None) -> int:
        """Manually clean up old L1 logs.

        Args:
            older_than_days: Override for rolling_days.

        Returns:
            Number of files deleted.
        """
        return self._session.cleanup(keep_days=older_than_days)

    def process_tag_queue(self) -> int:
        """Manually process the L3 tag extraction queue.

        Returns:
            Number of items processed.
        """
        return self._archive.process_tag_queue()

    def run_maintenance(self, older_than_days: int | None = None) -> dict[str, Any]:
        """Run a full maintenance cycle manually.

        Returns:
            Dict with stats about what was done.
        """
        return {
            "tags_processed": self._archive.process_tag_queue(),
            "cleaned": self._session.cleanup(keep_days=older_than_days),
        }

    # ═══════════════════════════════════════════════════════════
    # Stats
    # ═══════════════════════════════════════════════════════════

    def get_stats(self) -> dict[str, Any]:
        """Get statistics from all memory layers."""
        return {
            "session": self._session.get_stats(),
            "archive": self._archive.get_stats(),
            "is_polling": self._polling_active,
            "polling_interval": self._polling_interval,
        }

    def get_tag_stats(self) -> dict[str, int]:
        """Get tag usage counts from L3."""
        return self._archive.get_tag_stats()

    # ═══════════════════════════════════════════════════════════
    # Event Hooks
    # ═══════════════════════════════════════════════════════════

    def on(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for an event.

        Args:
            event: Event name.
            callback: Function to call when the event fires.

        Supported events:
            before_save    -- (content, source)
            after_save     -- (content, source)
            after_recall   -- (query, depth, result)
            before_promote -- (content,)
            after_promote  -- (content, memory_id)
            after_cycle    -- (stats_dict,)

        Example:
            def on_save(content, source):
                print(f"Saved from {source}: {content[:50]}")

            brain.on("after_save", on_save)
        """
        self._hooks.register(event, callback)

    # ═══════════════════════════════════════════════════════════
    # Export / Import
    # ═══════════════════════════════════════════════════════════

    def export_json(self, path: str | None = None) -> dict[str, Any]:
        """Export all memory data as a JSON-serializable dict.

        Args:
            path: Optional file path to write JSON to.

        Returns:
            The complete memory data as a dict.

        HOW IT WORKS:
            Exports session data (L1) + archive entries (L3).
            Use import_json() to restore from this export.
        """
        # Export L3 archive entries as list of dicts
        archive_entries = self._archive.get_all(limit=10000)
        archive_data = [
            {
                "id": e.id,
                "content": e.content,
                "content_type": e.content_type,
                "tags": e.tags,
                "source": e.source,
                "metadata": e.metadata,
                "created_at": e.created_at,
            }
            for e in archive_entries
        ]

        data = {
            "version": "0.1.0",
            "exported_at": now_iso(),
            "session": self._session.export(),
            "archive": archive_data,
            "archive_stats": self._archive.get_stats(),
        }

        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return data

    def export_jsonl(self, path: str) -> int:
        """Export L3 archive as JSONL (one JSON object per line).

        Args:
            path: File path to write JSONL to.

        Returns:
            Number of entries exported.
        """
        entries = self._archive.get_all(limit=10000)
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                line = json.dumps(
                    {
                        "id": entry.id,
                        "content": entry.content,
                        "tags": entry.tags,
                        "content_type": entry.content_type,
                        "created_at": entry.created_at,
                    },
                    ensure_ascii=False,
                )
                f.write(line + "\n")
        return len(entries)

    def import_json(self, data: dict[str, Any] | str) -> int:
        """Import data from an export dict or file path.

        Args:
            data: Either a dict (from export_json) or a file path string.

        Returns:
            Number of items imported.

        HOW IT WORKS:
            Restores session data (L1) and archive entries (L3)
            from a previous export_json() output.
        """
        parsed: dict[str, Any]
        if isinstance(data, str):
            text = Path(data).read_text(encoding="utf-8")
            parsed = json.loads(text)
        else:
            parsed = data

        count = 0

        # Import session data (L1)
        if "session" in parsed:
            self._session.import_data(parsed["session"])
            count += 1

        # Import archive entries (L3)
        if "archive" in parsed:
            for entry in parsed["archive"]:
                mem_id = self._archive.save(
                    content=entry.get("content", ""),
                    content_type=entry.get("content_type", "general"),
                    tags=entry.get("tags"),
                    metadata=entry.get("metadata"),
                )
                if mem_id > 0:
                    count += 1

        return count

    # ═══════════════════════════════════════════════════════════
    # Close
    # ═══════════════════════════════════════════════════════════

    def close(self) -> None:
        """Stop polling and release all resources.

        Always call this when you're done, or use the 'with' statement.
        """
        self.stop_polling()
        self._archive.close()
        logger.info("BrainMemory closed")

    # ═══════════════════════════════════════════════════════════
    # Internal Helpers
    # ═══════════════════════════════════════════════════════════

    def _should_promote(self, content: str) -> bool:
        """Decide if L1 content should be auto-promoted to L3.

        Uses the promote_checker callback. Default: content > 200 chars.
        """
        try:
            return self._promote_checker(content)
        except Exception:
            logger.warning("promote_checker callback failed")
            return False

    @staticmethod
    def _default_promote_checker(content: str) -> bool:
        """Default promotion rule: content longer than 200 characters.

        HOW TO CUSTOMIZE:
            def my_promoter(content):
                # Promote if it mentions decisions or rules
                keywords = ["decided", "rule", "important", "remember"]
                return any(k in content.lower() for k in keywords)

            brain = BrainMemory(tag_extractor=..., promote_checker=my_promoter)
        """
        return len(content) > 200
