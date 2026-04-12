# ═══════════════════════════════════════════════════════════
# permanent.py -- L3 ArchiveMemory (Long-term, SQLite + FTS5)
#
# WHAT THIS MODULE DOES:
#   This is the "long-term memory" of your AI.
#   Important memories get stored here permanently in SQLite.
#   You can search them using full-text search (like Google
#   but for your own memories).
#
# ANALOGY:
#   L1 (session.py) = sticky notes on your desk (3 days)
#   L2 (summary.py) = monthly summary report (30 days)
#   L3 (THIS FILE)  = filing cabinet (forever)
#
# KEY CONCEPT -- SELF-GROWING TAGS:
#   When you save "I like React and Python", the AI extracts
#   tags: ["react", "python", "preference"]. These tags go
#   into a keyword_map dictionary.
#
#   Next time someone mentions "React", the system instantly
#   matches it to "react" -- no AI needed!
#   The more you use it, the smarter it gets. That's self-growing.
#
# 2-STAGE TAG PIPELINE:
#   Stage 1: keyword_map lookup (instant, free, no AI call)
#   Stage 2: tag_extractor callback (AI, async via queue)
#   -> As keyword_map grows, Stage 1 catches more, Stage 2 is called less
#   -> Cost decreases over time!
#
# DATABASE TABLES:
#   memories      -- the actual stored content
#   memories_fts  -- FTS5 full-text search index
#   tag_index     -- tag-to-memory mapping
#   keyword_map   -- keyword-to-tag dictionary (self-growing)
#   tag_queue     -- pending items for AI tag extraction
#
# DEPENDS ON:
#   types.py (MemoryEntry)
#   exceptions.py (StorageError, TagExtractionError, CallbackError)
#   utils.py (now_iso, safe_json_loads, truncate)
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sandclaw_memory.exceptions import CallbackError, StorageError, TagExtractionError
from sandclaw_memory.types import MemoryEntry
from sandclaw_memory.utils import now_iso, safe_json_loads

__all__ = ["ArchiveMemory"]

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Default Groups -- flat tags (v0.1.0)
# ═══════════════════════════════════════════════════════════

# ─── WHAT ARE ROOT GROUPS? ───
# These are the top-level categories for organizing tags.
# In v0.1.0, they're flat (no sub-categories).
# In v0.2.0, they'll become a tree (technology/frontend/react).
#
# HOW TO CUSTOMIZE:
# You don't need to use these -- they're just defaults.
# Your AI will extract whatever tags make sense for YOUR domain.
# A doctor's tags: {"diagnosis", "prescription", "symptom"}
# A developer's tags: {"react", "api", "bugfix", "deploy"}
# ─────────────────────────────
DEFAULT_ROOT_GROUPS = [
    "technology",
    "business",
    "science",
    "health",
    "education",
    "creative",
    "daily",
    "communication",
]


# ═══════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════

_SCHEMA_SQL = """
-- Main memory storage
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    content_type TEXT DEFAULT 'general',
    tags TEXT,           -- JSON array of tag strings
    source TEXT,
    metadata TEXT,       -- JSON dict for arbitrary extra data
    created_at TEXT,
    updated_at TEXT
);

-- Tag-to-memory index (many-to-many)
CREATE TABLE IF NOT EXISTS tag_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL,
    memory_id INTEGER NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Self-growing keyword dictionary
-- tag_path is NULL in v0.1.0, reserved for v0.2.0 tree structure
CREATE TABLE IF NOT EXISTS keyword_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    tag TEXT NOT NULL,
    tag_path TEXT DEFAULT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'auto'
);

-- Queue for async AI tag extraction
CREATE TABLE IF NOT EXISTS tag_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_tag_index_tag ON tag_index(tag);
CREATE INDEX IF NOT EXISTS idx_keyword_map_keyword ON keyword_map(keyword);
CREATE INDEX IF NOT EXISTS idx_keyword_map_path ON keyword_map(tag_path);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(content_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_tag_queue_status ON tag_queue(status);
"""

_FTS_SQL = """
-- FTS5 full-text search (BM25 ranking, like Google)
-- content=memories means FTS5 reads from the memories table
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, tags, content=memories, content_rowid=id
);
"""

# FTS5 triggers: keep the search index in sync with the memories table
_FTS_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES('delete', old.id, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES('delete', old.id, old.content, old.tags);
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;
"""


class ArchiveMemory:
    """L3 permanent memory -- SQLite with FTS5 full-text search.

    This stores important memories forever. It has:
    - Full-text search (BM25 ranking)
    - Self-growing tag dictionary (keyword_map)
    - 2-stage tag pipeline (instant keyword match + async AI extraction)
    - Duplicate detection (difflib similarity)
    - Conflict detection (contradictory information)

    Usage:
        archive = ArchiveMemory(
            db_path="./memory/archive.db",
            tag_extractor=my_ai_func,
        )
        mem_id = archive.save("Python is great for data science")
        results = archive.search("python")
    """

    def __init__(
        self,
        db_path: str,
        tag_extractor: Callable[[str], list[str]],
        duplicate_checker: Callable[[str, str], bool] | None = None,
        conflict_resolver: Callable[[str, str], str] | None = None,
        encryption_key: str | None = None,
    ) -> None:
        """Initialize the archive with SQLite + FTS5.

        Args:
            db_path: Path to the SQLite database file.
            tag_extractor: REQUIRED callback that extracts tags from text.
                Must accept a string and return a list of tag strings.
                Example: lambda text: ["tag1", "tag2"]
            duplicate_checker: Optional callback to check if two texts are duplicates.
                Must accept (new_text, existing_text) and return True if duplicate.
                Default: difflib similarity > 0.85
            conflict_resolver: Optional callback to resolve conflicting information.
                Must accept (new_text, existing_text) and return the resolved text.
                Default: keep the newer text
            encryption_key: Optional SQLCipher encryption key.
                If provided, the database is encrypted with AES-256.
                Requires pysqlcipher3 to be installed.

        HOW TO CUSTOMIZE:
            # Custom duplicate threshold:
            def my_dup_checker(new, old):
                from difflib import SequenceMatcher
                return SequenceMatcher(None, new, old).ratio() > 0.9

            archive = ArchiveMemory(
                db_path="./memory.db",
                tag_extractor=my_ai_func,
                duplicate_checker=my_dup_checker,
            )
        """
        self._db_path = db_path
        self._tag_extractor = tag_extractor
        self._duplicate_checker = duplicate_checker or self._default_duplicate_checker
        self._conflict_resolver = conflict_resolver or self._default_conflict_resolver
        self._encryption_key = encryption_key
        self._lock = threading.Lock()

        # ─── Keyword cache (loaded from DB on first use) ───
        self._keyword_cache: dict[str, str] | None = None

        # ─── Initialize database ───
        self._init_db()

    # ═══════════════════════════════════════════════════════════
    # Database Setup
    # ═══════════════════════════════════════════════════════════

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new SQLite connection.

        WHY A NEW CONNECTION EACH TIME?
            SQLite connections are not thread-safe by default.
            Creating a new connection per operation is the safest
            approach when a polling thread and main thread both
            access the database.
        """
        # Ensure parent directory exists
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        if self._encryption_key:
            try:
                conn.execute(f"PRAGMA key='{self._encryption_key}'")
            except sqlite3.OperationalError:
                logger.warning("SQLCipher not available; database is unencrypted")

        return conn

    def _init_db(self) -> None:
        """Create tables, indexes, FTS5, and triggers."""
        try:
            conn = self._get_conn()
            try:
                conn.executescript(_SCHEMA_SQL)
                # FTS5 needs separate execution (some SQLite builds may not support it)
                try:
                    conn.executescript(_FTS_SQL)
                    conn.executescript(_FTS_TRIGGER_SQL)
                    self._fts_available = True
                except sqlite3.OperationalError:
                    logger.warning("FTS5 not available; falling back to LIKE search")
                    self._fts_available = False
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to initialize database at {self._db_path}: {e}") from e

    # ═══════════════════════════════════════════════════════════
    # Save
    # ═══════════════════════════════════════════════════════════

    def save(
        self,
        content: str,
        content_type: str = "general",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Save content to permanent memory.

        Args:
            content: The text to save permanently.
            content_type: Category (e.g. "general", "decision", "insight").
            tags: Optional pre-defined tags. If None, tags are extracted
                via the 2-stage pipeline (keyword_map + AI queue).
            metadata: Optional dict of extra data.

        Returns:
            The memory ID (integer) of the saved entry.

        HOW IT WORKS:
            1. Check for duplicates (skip if too similar to existing)
            2. Run Stage 1 tag extraction (keyword_map, instant)
            3. Save to SQLite
            4. Index tags in tag_index table
            5. Queue for Stage 2 AI extraction (async, via polling loop)

        HOW TO CUSTOMIZE:
            # Save with explicit tags (skips auto-extraction):
            archive.save("React is a frontend library", tags=["react", "frontend"])

            # Save with metadata:
            archive.save("Bug fixed", metadata={"jira": "PROJ-123"})
        """
        with self._lock:
            now = now_iso()
            tags_json = json.dumps(tags or [], ensure_ascii=False)
            metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

            # ─── Stage 1: keyword_map instant tagging ───
            if not tags:
                tags = self._extract_tags_stage1(content)
                tags_json = json.dumps(tags, ensure_ascii=False)

            try:
                conn = self._get_conn()
                try:
                    # ─── Duplicate check + conflict resolution ───
                    existing = self._find_duplicate(conn, content)
                    if existing is not None:
                        # A similar memory exists -> resolve the conflict
                        try:
                            resolved = self._conflict_resolver(existing["content"], content)
                        except Exception:
                            logger.warning("Conflict resolver failed, keeping newer text")
                            resolved = content

                        if resolved == existing["content"]:
                            # Resolver chose to keep old -> skip save
                            logger.debug("Duplicate detected, resolver kept existing")
                            return -1

                        # Update the existing memory with resolved content
                        conn.execute(
                            "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
                            (resolved, now, existing["id"]),
                        )
                        conn.commit()
                        logger.debug("Duplicate resolved, updated memory #%d", existing["id"])
                        return existing["id"]

                    # ─── Insert memory ───
                    cursor = conn.execute(
                        """INSERT INTO memories
                        (content, content_type, tags, source, metadata, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (content, content_type, tags_json, "archive", metadata_json, now, now),
                    )
                    memory_id = cursor.lastrowid
                    assert memory_id is not None

                    # ─── Index tags ───
                    for tag in tags:
                        conn.execute(
                            "INSERT INTO tag_index (tag, memory_id) VALUES (?, ?)",
                            (tag.lower(), memory_id),
                        )

                    # ─── Queue for Stage 2 AI extraction ───
                    conn.execute(
                        "INSERT INTO tag_queue (memory_id, content) VALUES (?, ?)",
                        (memory_id, content),
                    )

                    conn.commit()
                    logger.debug("Saved memory #%d with %d tags", memory_id, len(tags))
                    return memory_id
                finally:
                    conn.close()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to save memory: {e}") from e

    # ═══════════════════════════════════════════════════════════
    # Search
    # ═══════════════════════════════════════════════════════════

    def search(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        """Search memories using full-text search (FTS5 with BM25 ranking).

        Args:
            query: The search text.
            limit: Maximum number of results (default 20).

        Returns:
            List of MemoryEntry objects, ranked by relevance.

        HOW IT WORKS:
            If FTS5 is available, uses BM25 ranking (same algorithm as search engines).
            If FTS5 is not available, falls back to LIKE search.
        """
        try:
            conn = self._get_conn()
            try:
                if self._fts_available:
                    # ─── FTS5 search with BM25 ranking ───
                    # FTS5 has many special syntax characters:
                    #   - * ? " ^ ~ ( ) { } [ ] : → operators
                    #   - ' → string delimiter
                    #   - - → NOT operator (e.g., "follow-up" = follow NOT up)
                    # The safest approach: keep ONLY word characters + spaces.
                    sanitized = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)
                    sanitized = re.sub(r"\s+", " ", sanitized).strip()
                    if not sanitized:
                        return []
                    rows = conn.execute(
                        """SELECT m.* FROM memories m
                        JOIN memories_fts f ON m.id = f.rowid
                        WHERE memories_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?""",
                        (sanitized, limit),
                    ).fetchall()
                else:
                    # ─── Fallback: LIKE search ───
                    rows = conn.execute(
                        """SELECT * FROM memories
                        WHERE content LIKE ? OR tags LIKE ?
                        ORDER BY created_at DESC
                        LIMIT ?""",
                        (f"%{query}%", f"%{query}%", limit),
                    ).fetchall()
                return [self._row_to_entry(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Search failed: {e}") from e

    def search_by_tag(self, tag: str, limit: int = 10) -> list[MemoryEntry]:
        """Find memories with a specific tag.

        Args:
            tag: The tag to search for (case-insensitive).
            limit: Maximum number of results.

        Returns:
            List of MemoryEntry objects with the matching tag.
        """
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT m.* FROM memories m
                    JOIN tag_index t ON m.id = t.memory_id
                    WHERE t.tag = ?
                    ORDER BY m.created_at DESC
                    LIMIT ?""",
                    (tag.lower(), limit),
                ).fetchall()
                return [self._row_to_entry(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Tag search failed: {e}") from e

    def search_by_type(self, content_type: str, limit: int = 20) -> list[MemoryEntry]:
        """Find memories of a specific type."""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE content_type = ? ORDER BY created_at DESC LIMIT ?",
                    (content_type, limit),
                ).fetchall()
                return [self._row_to_entry(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Type search failed: {e}") from e

    def search_by_date(
        self, start: str, end: str, limit: int = 100
    ) -> list[MemoryEntry]:
        """Find memories within a date range.

        Args:
            start: Start date (ISO 8601, e.g. "2026-04-01").
            end: End date (ISO 8601, e.g. "2026-04-12").
            limit: Maximum results.
        """
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM memories
                    WHERE created_at >= ? AND created_at <= ?
                    ORDER BY created_at DESC LIMIT ?""",
                    (start, end, limit),
                ).fetchall()
                return [self._row_to_entry(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Date search failed: {e}") from e

    def get_all(self, limit: int = 10000) -> list[MemoryEntry]:
        """Retrieve all memories (for export/backup).

        Args:
            limit: Maximum number of entries (default 10000).

        Returns:
            List of all MemoryEntry objects, newest first.
        """
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [self._row_to_entry(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Get all failed: {e}") from e

    def get_by_id(self, memory_id: int) -> MemoryEntry | None:
        """Retrieve a single memory by its ID."""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ?", (memory_id,)
                ).fetchone()
                if row:
                    return self._row_to_entry(row)
                return None
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Get by ID failed: {e}") from e

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by its ID.

        Returns:
            True if the memory was deleted, False if not found.
        """
        try:
            conn = self._get_conn()
            try:
                # Delete tag index entries
                conn.execute("DELETE FROM tag_index WHERE memory_id = ?", (memory_id,))
                # Delete the memory itself
                cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Delete failed: {e}") from e

    # ═══════════════════════════════════════════════════════════
    # Tag System (Self-Growing)
    # ═══════════════════════════════════════════════════════════

    def _extract_tags_stage1(self, content: str) -> list[str]:
        """Stage 1: Instant tag extraction from keyword_map.

        HOW IT WORKS:
            Splits the content into words, looks each word up in
            the keyword_map dictionary. If found, adds the mapped tag.
            This is FREE (no AI call) and INSTANT.

        WHY THIS MATTERS:
            As keyword_map grows over time, more words get matched
            at Stage 1, and fewer need Stage 2 (AI).
            Day 1:  ~0% matched -> 100% go to AI  ($$$)
            Day 30: ~70% matched -> 30% go to AI  ($)
            Day 90: ~90% matched -> 10% go to AI  (cents)
        """
        cache = self._get_keyword_cache()
        if not cache:
            return []

        found_tags: set[str] = set()
        # Normalize content: lowercase, split into words
        words = content.lower().split()
        for word in words:
            # Strip punctuation
            clean = word.strip(".,!?;:()[]{}\"'")
            if clean in cache:
                found_tags.add(cache[clean])

        return list(found_tags)

    def _get_keyword_cache(self) -> dict[str, str]:
        """Load keyword_map into memory (cached).

        WHY CACHE?
            Reading from SQLite for every word in every save()
            would be slow. We cache the entire keyword_map in memory
            and refresh it when new keywords are added.
        """
        if self._keyword_cache is not None:
            return self._keyword_cache

        try:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT keyword, tag FROM keyword_map").fetchall()
                self._keyword_cache = {r["keyword"]: r["tag"] for r in rows}
                return self._keyword_cache
            finally:
                conn.close()
        except sqlite3.Error:
            return {}

    def process_tag_queue(self) -> int:
        """Stage 2: Process pending AI tag extractions.

        This is called by the polling loop (every N seconds).
        It takes items from the tag_queue, calls tag_extractor,
        and registers discovered tags into keyword_map.

        Returns:
            Number of items processed.

        HOW IT WORKS:
            1. Fetch up to 5 pending items from tag_queue
            2. For each: call tag_extractor callback (AI)
            3. Save extracted tags to tag_index
            4. Register new keywords in keyword_map (self-growing!)
            5. Mark queue item as 'done'
            6. On failure: increment retry_count, try again next cycle
        """
        processed = 0

        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM tag_queue
                    WHERE status = 'pending' AND retry_count < 3
                    ORDER BY created_at ASC LIMIT 5"""
                ).fetchall()

                for row in rows:
                    queue_id = row["id"]
                    memory_id = row["memory_id"]
                    content = row["content"]

                    try:
                        # ─── Call AI tag extractor ───
                        tags = self._tag_extractor(content)

                        if not isinstance(tags, list):
                            raise TagExtractionError(
                                f"tag_extractor must return list[str], got {type(tags).__name__}. "
                                "Check your callback function."
                            )

                        with self._lock:
                            # Save tags to tag_index
                            for tag in tags:
                                tag_lower = tag.lower().strip()
                                if not tag_lower:
                                    continue

                                conn.execute(
                                    """INSERT OR IGNORE INTO tag_index (tag, memory_id)
                                    VALUES (?, ?)""",
                                    (tag_lower, memory_id),
                                )

                                # ─── Self-growing: register new keywords ───
                                # This is where the magic happens!
                                # Each extracted tag becomes a keyword in the map.
                                # Next time this word appears, Stage 1 catches it instantly.
                                self._register_keyword(conn, tag_lower, tag_lower)

                            # Update the memory's tags column
                            existing = conn.execute(
                                "SELECT tags FROM memories WHERE id = ?", (memory_id,)
                            ).fetchone()
                            if existing:
                                old_tags = safe_json_loads(existing["tags"], default=[])
                                merged = list(set(old_tags + [t.lower().strip() for t in tags]))
                                conn.execute(
                                    "UPDATE memories SET tags = ?, updated_at = ? WHERE id = ?",
                                    (json.dumps(merged, ensure_ascii=False), now_iso(), memory_id),
                                )

                            # Mark as done
                            conn.execute(
                                "UPDATE tag_queue SET status = 'done' WHERE id = ?",
                                (queue_id,),
                            )

                        processed += 1

                    except (CallbackError, TagExtractionError):
                        raise
                    except Exception as e:
                        # Retry logic: increment count, try again next cycle
                        conn.execute(
                            """UPDATE tag_queue
                            SET retry_count = retry_count + 1, status = 'pending'
                            WHERE id = ?""",
                            (queue_id,),
                        )
                        logger.warning("Tag extraction failed for queue #%d: %s", queue_id, e)

                conn.commit()
            finally:
                conn.close()
        except (CallbackError, TagExtractionError):
            raise
        except sqlite3.Error as e:
            raise StorageError(f"Tag queue processing failed: {e}") from e

        if processed > 0:
            # Invalidate keyword cache so new keywords are picked up
            self._keyword_cache = None
            logger.debug("Processed %d tag queue items", processed)

        return processed

    def _register_keyword(self, conn: sqlite3.Connection, keyword: str, tag: str) -> None:
        """Register a keyword -> tag mapping (self-growing).

        This is the core of the self-growing tag system.
        Every time AI extracts a new tag, the keyword gets registered
        so next time it's matched instantly (Stage 1, no AI call).
        """
        existing = conn.execute(
            "SELECT id FROM keyword_map WHERE keyword = ?", (keyword,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO keyword_map (keyword, tag, source) VALUES (?, ?, 'auto')",
                (keyword, tag),
            )

    def extract_tags(self, content: str) -> list[str]:
        """Extract tags from content using Stage 1 (keyword_map).

        This is the PUBLIC version of _extract_tags_stage1().
        It only uses the keyword_map (instant, free, no AI call).
        For full AI extraction, save the content and let the
        polling loop process it via Stage 2.

        Args:
            content: The text to extract tags from.

        Returns:
            List of tags matched from the keyword_map.

        HOW TO CUSTOMIZE:
            # Pre-seed keywords, then extract:
            archive.add_keyword("react", "react")
            tags = archive.extract_tags("I love React")
            # -> ["react"]
        """
        return self._extract_tags_stage1(content)

    def enqueue_tag_extraction(self, memory_id: int, content: str) -> None:
        """Manually queue content for Stage 2 AI tag extraction.

        Use this when you want to re-extract tags for an existing memory,
        or when you add content outside of save() and still want AI tagging.

        Args:
            memory_id: The memory ID in the memories table.
            content: The text to extract tags from.

        HOW TO CUSTOMIZE:
            # Force re-extraction for an old memory:
            archive.enqueue_tag_extraction(42, "React Native app")
            archive.process_tag_queue()  # processes immediately
        """
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO tag_queue (memory_id, content) VALUES (?, ?)",
                    (memory_id, content),
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to enqueue tag extraction: {e}") from e

    def add_keyword(self, keyword: str, tag: str) -> None:
        """Manually register a keyword -> tag mapping.

        Args:
            keyword: The word to match (e.g. "react", "파이썬").
            tag: The tag it maps to (e.g. "react", "python").

        Use this to pre-seed the keyword dictionary:
            archive.add_keyword("리액트", "react")  # Korean -> English
            archive.add_keyword("JS", "javascript")  # Abbreviation
        """
        try:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT id FROM keyword_map WHERE keyword = ?", (keyword.lower(),)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO keyword_map (keyword, tag, source) VALUES (?, ?, 'manual')",
                        (keyword.lower(), tag.lower()),
                    )
                    conn.commit()
                    self._keyword_cache = None  # invalidate cache
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to add keyword: {e}") from e

    # ═══════════════════════════════════════════════════════════
    # Duplicate & Conflict Detection
    # ═══════════════════════════════════════════════════════════

    def _find_duplicate(self, conn: sqlite3.Connection, content: str) -> dict[str, Any] | None:
        """Find a duplicate memory if one exists.

        HOW IT WORKS:
            Fetches the last 10 memories and compares each one
            using the duplicate_checker callback.
            Default: difflib SequenceMatcher > 0.85 similarity.

        Returns:
            The matching row dict if a duplicate is found, None otherwise.

        WHY CHECK DUPLICATES?
            Without this, saving the same conversation turn multiple
            times would bloat the database with identical entries.
            When a duplicate IS found, the conflict_resolver callback
            decides how to merge the old and new content.
        """
        rows = conn.execute(
            "SELECT id, content FROM memories ORDER BY id DESC LIMIT 10"
        ).fetchall()

        for row in rows:
            try:
                if self._duplicate_checker(content, row["content"]):
                    return dict(row)
            except Exception:
                logger.warning("Duplicate checker callback failed")
                continue

        return None

    @staticmethod
    def _default_duplicate_checker(new_text: str, existing_text: str) -> bool:
        """Default duplicate detection: 85% text similarity.

        HOW TO CUSTOMIZE:
            Provide your own duplicate_checker callback:
                def strict_checker(new, old):
                    return new.strip() == old.strip()  # exact match only

                archive = ArchiveMemory(..., duplicate_checker=strict_checker)
        """
        return SequenceMatcher(None, new_text, existing_text).ratio() > 0.85

    @staticmethod
    def _default_conflict_resolver(new_text: str, existing_text: str) -> str:
        """Default conflict resolution: keep the newer text.

        HOW TO CUSTOMIZE:
            Provide your own conflict_resolver callback:
                def merge_resolver(new, old):
                    return f"{old}\\n[Updated]: {new}"

                archive = ArchiveMemory(..., conflict_resolver=merge_resolver)
        """
        return new_text

    # ═══════════════════════════════════════════════════════════
    # Stats
    # ═══════════════════════════════════════════════════════════

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the archive."""
        try:
            conn = self._get_conn()
            try:
                memory_count = conn.execute("SELECT COUNT(*) c FROM memories").fetchone()["c"]
                tag_count = conn.execute(
                    "SELECT COUNT(DISTINCT tag) c FROM tag_index"
                ).fetchone()["c"]
                keyword_count = conn.execute("SELECT COUNT(*) c FROM keyword_map").fetchone()["c"]
                pending = conn.execute(
                    "SELECT COUNT(*) c FROM tag_queue WHERE status = 'pending'"
                ).fetchone()["c"]

                return {
                    "total_memories": memory_count,
                    "unique_tags": tag_count,
                    "keyword_map_size": keyword_count,
                    "pending_tag_extractions": pending,
                    "fts5_available": self._fts_available,
                    "db_path": self._db_path,
                }
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Stats query failed: {e}") from e

    def get_tag_stats(self) -> dict[str, int]:
        """Get tag usage counts (how many memories per tag).

        Returns:
            Dict mapping tag names to their memory count.
            Example: {"python": 15, "react": 8, "bugfix": 3}
        """
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT tag, COUNT(*) as cnt FROM tag_index
                    GROUP BY tag ORDER BY cnt DESC"""
                ).fetchall()
                return {r["tag"]: r["cnt"] for r in rows}
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise StorageError(f"Tag stats query failed: {e}") from e

    # ═══════════════════════════════════════════════════════════
    # Close
    # ═══════════════════════════════════════════════════════════

    def close(self) -> None:
        """Clean up resources.

        Currently a no-op since we create connections per operation,
        but provided for forward compatibility and explicit resource management.
        """
        self._keyword_cache = None

    # ═══════════════════════════════════════════════════════════
    # Internal Helpers
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        """Convert a SQLite row to a MemoryEntry dataclass."""
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            content_type=row["content_type"] or "general",
            tags=safe_json_loads(row["tags"], default=[]),
            source=row["source"] or "",
            metadata=safe_json_loads(row["metadata"], default={}),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )
