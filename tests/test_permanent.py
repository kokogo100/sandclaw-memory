"""Tests for L3 ArchiveMemory (SQLite + FTS5 + Self-Growing Tags)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sandclaw_memory.permanent import ArchiveMemory
from sandclaw_memory.types import MemoryEntry


# ─── Mock tag extractor (no AI calls in tests) ───
def mock_tag_extractor(content: str) -> list[str]:
    """Simple keyword extraction for testing."""
    words = content.lower().split()
    return [w.strip(".,!?;:()") for w in words if len(w) > 3][:5]


@pytest.fixture
def archive(tmp_path: Path) -> ArchiveMemory:
    """Create an ArchiveMemory with a temp database."""
    db = str(tmp_path / "test_archive.db")
    return ArchiveMemory(db_path=db, tag_extractor=mock_tag_extractor)


class TestInit:
    """Verify database initialization."""

    def test_creates_database(self, archive: ArchiveMemory) -> None:
        assert Path(archive._db_path).exists()

    def test_stats_empty(self, archive: ArchiveMemory) -> None:
        stats = archive.get_stats()
        assert stats["total_memories"] == 0
        assert stats["unique_tags"] == 0
        assert stats["keyword_map_size"] == 0


class TestSave:
    """Verify saving memories."""

    def test_save_returns_id(self, archive: ArchiveMemory) -> None:
        mem_id = archive.save("Python is great for data science")
        assert mem_id > 0

    def test_save_increments_count(self, archive: ArchiveMemory) -> None:
        archive.save("First memory")
        archive.save("Second memory")
        stats = archive.get_stats()
        assert stats["total_memories"] == 2

    def test_save_with_explicit_tags(self, archive: ArchiveMemory) -> None:
        mem_id = archive.save("React component", tags=["react", "frontend"])
        entry = archive.get_by_id(mem_id)
        assert entry is not None
        assert "react" in entry.tags

    def test_save_with_metadata(self, archive: ArchiveMemory) -> None:
        mem_id = archive.save("Bug fix", metadata={"jira": "PROJ-123"})
        entry = archive.get_by_id(mem_id)
        assert entry is not None
        assert entry.metadata["jira"] == "PROJ-123"

    def test_duplicate_detection(self, archive: ArchiveMemory) -> None:
        archive.save("This is a unique sentence about programming")
        dup_id = archive.save("This is a unique sentence about programming")
        assert dup_id == -1  # duplicate rejected

    def test_save_queues_for_tag_extraction(self, archive: ArchiveMemory) -> None:
        archive.save("Something new")
        stats = archive.get_stats()
        assert stats["pending_tag_extractions"] >= 1


class TestSearch:
    """Verify search functionality."""

    def test_fts5_search(self, archive: ArchiveMemory) -> None:
        archive.save("Python is great for machine learning", tags=["python", "ml"])
        archive.save("React is a frontend library", tags=["react", "frontend"])
        results = archive.search("python")
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

    def test_search_no_results(self, archive: ArchiveMemory) -> None:
        archive.save("Hello world")
        results = archive.search("nonexistent_xyz_12345")
        assert len(results) == 0

    def test_search_by_tag(self, archive: ArchiveMemory) -> None:
        archive.save("React hooks tutorial", tags=["react"])
        archive.save("Python data analysis", tags=["python"])
        results = archive.search_by_tag("react")
        assert len(results) == 1
        assert "React" in results[0].content

    def test_search_by_type(self, archive: ArchiveMemory) -> None:
        archive.save("Important decision", content_type="decision")
        archive.save("General note", content_type="general")
        results = archive.search_by_type("decision")
        assert len(results) == 1

    def test_search_by_date(self, archive: ArchiveMemory) -> None:
        archive.save("Today's memory")
        results = archive.search_by_date("2000-01-01", "2099-12-31")
        assert len(results) >= 1


class TestGetAndDelete:
    """Verify get_by_id and delete."""

    def test_get_by_id(self, archive: ArchiveMemory) -> None:
        mem_id = archive.save("Specific memory")
        entry = archive.get_by_id(mem_id)
        assert entry is not None
        assert entry.content == "Specific memory"
        assert isinstance(entry, MemoryEntry)

    def test_get_nonexistent(self, archive: ArchiveMemory) -> None:
        assert archive.get_by_id(99999) is None

    def test_delete(self, archive: ArchiveMemory) -> None:
        mem_id = archive.save("To be deleted")
        assert archive.delete(mem_id) is True
        assert archive.get_by_id(mem_id) is None

    def test_delete_nonexistent(self, archive: ArchiveMemory) -> None:
        assert archive.delete(99999) is False


class TestSelfGrowingTags:
    """Verify the self-growing keyword_map system."""

    def test_process_tag_queue(self, archive: ArchiveMemory) -> None:
        archive.save("Python React JavaScript development")
        processed = archive.process_tag_queue()
        assert processed >= 1

    def test_keyword_map_grows(self, archive: ArchiveMemory) -> None:
        archive.save("Python programming language")
        archive.process_tag_queue()
        stats = archive.get_stats()
        assert stats["keyword_map_size"] > 0

    def test_stage1_matches_after_learning(self, archive: ArchiveMemory) -> None:
        """After AI extracts 'python', next save should match it at Stage 1."""
        # First save: "python" goes through AI (Stage 2)
        archive.save("Python programming is fun", tags=["python"])
        archive.process_tag_queue()

        # Manually add keyword mapping
        archive.add_keyword("python", "python")

        # Second save: "python" should be matched by keyword_map (Stage 1)
        archive._keyword_cache = None  # force cache refresh
        tags = archive._extract_tags_stage1("I love Python and coding")
        assert "python" in tags

    def test_add_keyword_manual(self, archive: ArchiveMemory) -> None:
        archive.add_keyword("리액트", "react")
        archive._keyword_cache = None
        tags = archive._extract_tags_stage1("리액트 컴포넌트 만들기")
        assert "react" in tags

    def test_tag_stats(self, archive: ArchiveMemory) -> None:
        archive.save("Python basics", tags=["python"])
        archive.save("Python advanced", tags=["python"])
        archive.save("React intro", tags=["react"])
        stats = archive.get_tag_stats()
        assert stats.get("python", 0) == 2
        assert stats.get("react", 0) == 1


class TestTagExtractorCallback:
    """Verify tag_extractor callback behavior."""

    def test_bad_return_type_raises(self, tmp_path: Path) -> None:
        """tag_extractor returning wrong type should raise TagExtractionError."""

        def bad_extractor(content: str) -> str:  # type: ignore[return-value]
            return "not a list"  # wrong type!

        archive = ArchiveMemory(
            db_path=str(tmp_path / "bad.db"),
            tag_extractor=bad_extractor,  # type: ignore[arg-type]
        )
        archive.save("Test content")
        with pytest.raises(Exception):
            archive.process_tag_queue()


class TestClose:
    """Verify cleanup."""

    def test_close_clears_cache(self, archive: ArchiveMemory) -> None:
        archive.add_keyword("test", "test")
        archive._keyword_cache = {"test": "test"}
        archive.close()
        assert archive._keyword_cache is None


class TestExtractTagsPublic:
    """Verify public extract_tags() method."""

    def test_returns_empty_when_no_keywords(self, archive: ArchiveMemory) -> None:
        tags = archive.extract_tags("hello world")
        assert tags == []

    def test_matches_registered_keywords(self, archive: ArchiveMemory) -> None:
        archive.add_keyword("python", "python")
        archive.add_keyword("react", "react")
        tags = archive.extract_tags("I use Python and React daily")
        assert "python" in tags
        assert "react" in tags


class TestEnqueueTagExtraction:
    """Verify public enqueue_tag_extraction() method."""

    def test_enqueues_and_processes(self, archive: ArchiveMemory) -> None:
        # Save a memory first
        mem_id = archive.save("Test content for queue")
        # Manually enqueue for re-extraction
        archive.enqueue_tag_extraction(mem_id, "React and Python tutorial")
        # Process the queue
        processed = archive.process_tag_queue()
        assert processed >= 1


class TestConflictResolver:
    """Verify conflict_resolver is actually called on duplicates."""

    def test_resolver_merges_content(self, tmp_path: Path) -> None:
        def merge_resolver(old_text: str, new_text: str) -> str:
            return f"{old_text} | {new_text}"

        db = str(tmp_path / "conflict.db")
        archive = ArchiveMemory(
            db_path=db,
            tag_extractor=mock_tag_extractor,
            conflict_resolver=merge_resolver,
        )
        # Save original
        mem_id = archive.save("I love Python")
        assert mem_id > 0
        # Save duplicate -> resolver should merge
        result_id = archive.save("I love Python")
        # Should return the existing ID (updated), not -1
        assert result_id == mem_id
        # Content should be merged
        entry = archive.get_by_id(mem_id)
        assert entry is not None
        assert "I love Python | I love Python" in entry.content

    def test_default_resolver_skips_exact_duplicate(self, archive: ArchiveMemory) -> None:
        archive.save("Version 1 of the content")
        # Save exact duplicate -> default resolver returns new_text which equals old_text
        # So the system correctly skips (no update needed for identical content)
        result = archive.save("Version 1 of the content")
        assert result == -1  # skipped, no change needed

    def test_custom_resolver_always_updates(self, tmp_path: Path) -> None:
        def append_resolver(old_text: str, new_text: str) -> str:
            return f"{old_text}\n[Updated]: {new_text}"

        db = str(tmp_path / "custom_conflict.db")
        archive = ArchiveMemory(
            db_path=db,
            tag_extractor=mock_tag_extractor,
            conflict_resolver=append_resolver,
        )
        mem_id = archive.save("Original content here")
        # Save duplicate -> custom resolver appends
        result = archive.save("Original content here")
        assert result == mem_id  # updated existing
        entry = archive.get_by_id(mem_id)
        assert entry is not None
        assert "[Updated]" in entry.content
