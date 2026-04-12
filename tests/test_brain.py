"""Tests for BrainMemory (orchestrator)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sandclaw_memory import BrainMemory, Depth, SandclawError
from sandclaw_memory.exceptions import ConfigurationError


# ─── Mock tag extractor ───
def mock_tag_extractor(content: str) -> list[str]:
    words = content.lower().split()
    return [w.strip(".,!?") for w in words if len(w) > 3][:5]


@pytest.fixture
def brain(tmp_path: Path) -> BrainMemory:
    b = BrainMemory(
        db_path=str(tmp_path / "memory"),
        tag_extractor=mock_tag_extractor,
        polling_interval=1,  # fast for tests
    )
    yield b
    b.close()


class TestInit:
    """Verify initialization."""

    def test_requires_tag_extractor(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="tag_extractor is required"):
            BrainMemory(db_path=str(tmp_path / "mem"), tag_extractor=None)

    def test_configuration_error_is_sandclaw(self, tmp_path: Path) -> None:
        with pytest.raises(SandclawError):
            BrainMemory(db_path=str(tmp_path / "mem"), tag_extractor=None)

    def test_creates_directory(self, brain: BrainMemory) -> None:
        assert Path(brain._db_path).exists()


class TestContextManager:
    """Verify with-statement support."""

    def test_with_statement(self, tmp_path: Path) -> None:
        with BrainMemory(
            db_path=str(tmp_path / "mem"),
            tag_extractor=mock_tag_extractor,
        ) as brain:
            brain.save("test content")
        # Should not raise after exiting

    def test_close_stops_polling(self, tmp_path: Path) -> None:
        brain = BrainMemory(
            db_path=str(tmp_path / "mem"),
            tag_extractor=mock_tag_extractor,
        )
        brain.start_polling()
        assert brain.is_polling is True
        brain.close()
        assert brain.is_polling is False


class TestSave:
    """Verify save routing."""

    def test_save_to_l1(self, brain: BrainMemory) -> None:
        brain.save("Hello world")
        context = brain.recall()
        assert "Hello" in context or "hello" in context.lower()

    def test_save_to_archive(self, brain: BrainMemory) -> None:
        brain.save("Important decision about Python", source="archive")
        stats = brain.get_stats()
        assert stats["archive"]["total_memories"] >= 1

    def test_auto_promote_long_content(self, brain: BrainMemory) -> None:
        long_content = "A" * 250  # > 200 chars -> auto-promote
        brain.save(long_content)
        stats = brain.get_stats()
        assert stats["archive"]["total_memories"] >= 1


class TestRecall:
    """Verify recall with depth detection."""

    def test_recall_empty(self, brain: BrainMemory) -> None:
        result = brain.recall("hello")
        assert isinstance(result, str)

    def test_recall_manual_depth(self, brain: BrainMemory) -> None:
        brain.save("Test data", source="archive")
        result = brain.recall("test", depth="deep")
        assert isinstance(result, str)

    def test_recall_auto_depth(self, brain: BrainMemory) -> None:
        brain.save("Some data")
        result = brain.recall("what happened 3 months ago?")
        # Should auto-detect DEEP (keyword: "months ago")
        assert isinstance(result, str)


class TestSearch:
    """Verify L3 search."""

    def test_search_returns_list(self, brain: BrainMemory) -> None:
        brain.save("Python tutorial", source="archive", tags=["python"])
        results = brain.search("python")
        assert len(results) >= 1

    def test_search_empty(self, brain: BrainMemory) -> None:
        results = brain.search("nonexistent_xyz")
        assert results == []


class TestPromote:
    """Verify manual promotion."""

    def test_promote_returns_id(self, brain: BrainMemory) -> None:
        mem_id = brain.promote("Manually promoted content")
        assert mem_id > 0


class TestPolling:
    """Verify polling loop."""

    def test_start_stop(self, brain: BrainMemory) -> None:
        brain.start_polling()
        assert brain.is_polling is True
        brain.stop_polling()
        assert brain.is_polling is False

    def test_double_start_is_safe(self, brain: BrainMemory) -> None:
        brain.start_polling()
        brain.start_polling()  # should not crash
        assert brain.is_polling is True
        brain.stop_polling()

    def test_polling_processes_queue(self, brain: BrainMemory) -> None:
        brain.save("Python React programming", source="archive")
        brain.start_polling()
        time.sleep(2)  # wait for one cycle
        brain.stop_polling()
        stats = brain.get_stats()
        # Queue should have been processed
        assert stats["archive"]["pending_tag_extractions"] == 0


class TestMaintenance:
    """Verify manual maintenance."""

    def test_run_maintenance(self, brain: BrainMemory) -> None:
        result = brain.run_maintenance()
        assert "tags_processed" in result
        assert "cleaned" in result

    def test_process_tag_queue(self, brain: BrainMemory) -> None:
        brain.save("Test content for queue", source="archive")
        processed = brain.process_tag_queue()
        assert processed >= 0


class TestHooks:
    """Verify event hooks."""

    def test_after_save_hook(self, brain: BrainMemory) -> None:
        events: list[str] = []
        brain.on("after_save", lambda content, source: events.append(source))
        brain.save("test", source="chat")
        assert "chat" in events

    def test_after_cycle_hook(self, brain: BrainMemory) -> None:
        stats_list: list[dict] = []
        brain.on("after_cycle", lambda stats: stats_list.append(stats))
        brain.start_polling()
        time.sleep(2)
        brain.stop_polling()
        assert len(stats_list) >= 1


class TestExportImport:
    """Verify data export."""

    def test_export_json(self, brain: BrainMemory) -> None:
        brain.save("Export test")
        data = brain.export_json()
        assert data["version"] == "0.1.0"
        assert "session" in data
        assert "archive" in data

    def test_export_json_includes_archive(self, brain: BrainMemory) -> None:
        brain.save("Archive export test", source="archive", tags=["test"])
        data = brain.export_json()
        assert len(data["archive"]) >= 1
        assert data["archive"][0]["content"] == "Archive export test"

    def test_export_json_to_file(self, brain: BrainMemory, tmp_path: Path) -> None:
        brain.save("File export test")
        path = str(tmp_path / "export.json")
        brain.export_json(path=path)
        assert Path(path).exists()

    def test_import_json_with_archive(self, brain: BrainMemory) -> None:
        brain.save("Memory to export", source="archive", tags=["python"])
        data = brain.export_json()
        # Create a fresh brain and import
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            brain2 = BrainMemory(
                db_path=str(Path(td) / "import_test"),
                tag_extractor=mock_tag_extractor,
            )
            count = brain2.import_json(data)
            assert count >= 2  # session + at least 1 archive entry
            # Verify archive was imported
            stats = brain2.get_stats()
            assert stats["archive"]["total_memories"] >= 1
            brain2.close()

    def test_import_json_from_file(self, brain: BrainMemory, tmp_path: Path) -> None:
        brain.save("File import content", source="archive", tags=["test"])
        path = str(tmp_path / "import_test.json")
        brain.export_json(path=path)
        # Import from file path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            brain2 = BrainMemory(
                db_path=str(Path(td) / "import_test2"),
                tag_extractor=mock_tag_extractor,
            )
            count = brain2.import_json(path)
            assert count >= 1
            brain2.close()


class TestStats:
    """Verify stats reporting."""

    def test_stats_structure(self, brain: BrainMemory) -> None:
        stats = brain.get_stats()
        assert "session" in stats
        assert "archive" in stats
        assert "is_polling" in stats

    def test_tag_stats(self, brain: BrainMemory) -> None:
        brain.save("Python tutorial", source="archive", tags=["python"])
        stats = brain.get_tag_stats()
        assert isinstance(stats, dict)
