"""Tests for L1 SessionMemory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sandclaw_memory.session import SessionMemory


@pytest.fixture
def session(tmp_path: Path) -> SessionMemory:
    """Create a SessionMemory with a temporary directory."""
    return SessionMemory(base_path=str(tmp_path / "memory"))


class TestInit:
    """Verify initialization creates the expected structure."""

    def test_creates_directories(self, session: SessionMemory) -> None:
        assert session.logs_path.exists()
        assert session.logs_path.is_dir()

    def test_creates_profile(self, session: SessionMemory) -> None:
        assert session.profile_path.exists()
        content = session.profile_path.read_text(encoding="utf-8")
        assert "# User Profile" in content

    def test_custom_profile_template(self, tmp_path: Path) -> None:
        custom = "# My Custom Profile\n\n## Custom Section\n"
        s = SessionMemory(base_path=str(tmp_path / "mem"), profile_template=custom)
        content = s.profile_path.read_text(encoding="utf-8")
        assert "Custom Section" in content


class TestSaveConversation:
    """Verify conversation saving."""

    def test_saves_to_today_log(self, session: SessionMemory) -> None:
        session.save_conversation("Hello", "Hi there!")
        log = session.get_today_log()
        assert "**User**: Hello" in log
        assert "**AI**: Hi there!" in log

    def test_multiple_conversations(self, session: SessionMemory) -> None:
        session.save_conversation("First", "Response 1")
        session.save_conversation("Second", "Response 2")
        log = session.get_today_log()
        assert "First" in log
        assert "Second" in log

    def test_metadata_stored(self, session: SessionMemory) -> None:
        session.save_conversation("Hi", "Hello", metadata={"mood": "happy"})
        log = session.get_today_log()
        assert "happy" in log


class TestSaveEntry:
    """Verify freeform entry saving."""

    def test_saves_note(self, session: SessionMemory) -> None:
        session.save_entry("Deployed v2.0", entry_type="action")
        log = session.get_today_log()
        assert "Deployed v2.0" in log
        assert "Action" in log

    def test_default_type_is_note(self, session: SessionMemory) -> None:
        session.save_entry("Some note")
        log = session.get_today_log()
        assert "Note" in log


class TestProfile:
    """Verify profile management."""

    def test_update_existing_section(self, session: SessionMemory) -> None:
        session.update_profile("Preferences", "Language: Python")
        profile = session.get_profile()
        assert "- Language: Python" in profile

    def test_create_new_section(self, session: SessionMemory) -> None:
        session.update_profile("Custom Section", "My custom data")
        profile = session.get_profile()
        assert "## Custom Section" in profile
        assert "- My custom data" in profile

    def test_get_profile_empty(self, tmp_path: Path) -> None:
        s = SessionMemory(base_path=str(tmp_path / "mem"))
        # Delete the profile to test empty case
        s.profile_path.unlink()
        assert s.get_profile() == ""


class TestGetContext:
    """Verify context loading for LLM injection."""

    def test_includes_profile(self, session: SessionMemory) -> None:
        context = session.get_context()
        assert "User Profile" in context

    def test_includes_today_log(self, session: SessionMemory) -> None:
        session.save_conversation("test question", "test answer")
        context = session.get_context()
        assert "test question" in context

    def test_respects_max_chars(self, tmp_path: Path) -> None:
        s = SessionMemory(base_path=str(tmp_path / "mem"), max_context_chars=200)
        # Save a long conversation
        s.save_conversation("A" * 300, "B" * 300)
        context = s.get_context()
        assert len(context) <= 200 + 50  # allow some margin for truncation prefix

    def test_truncation_keeps_recent(self, tmp_path: Path) -> None:
        s = SessionMemory(base_path=str(tmp_path / "mem"), max_context_chars=100)
        s.save_conversation("old message", "old reply")
        s.save_conversation("RECENT_MARKER", "RECENT_REPLY")
        context = s.get_context()
        # Recent content should be preserved (truncation cuts from front)
        assert "RECENT" in context


class TestGetLogByDate:
    """Verify date-specific log retrieval."""

    def test_valid_date(self, session: SessionMemory) -> None:
        session.save_conversation("Hi", "Hello")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log = session.get_log_by_date(today)
        assert "Hi" in log

    def test_invalid_date_format(self, session: SessionMemory) -> None:
        assert session.get_log_by_date("not-a-date") == ""

    def test_nonexistent_date(self, session: SessionMemory) -> None:
        assert session.get_log_by_date("2000-01-01") == ""


class TestSearchLogs:
    """Verify keyword search across logs."""

    def test_finds_keyword(self, session: SessionMemory) -> None:
        session.save_conversation("Python is great", "Indeed!")
        results = session.search_logs("python")
        assert len(results) >= 1
        assert "Python" in results[0]["content"]

    def test_case_insensitive(self, session: SessionMemory) -> None:
        session.save_conversation("REACT component", "Sure")
        results = session.search_logs("react")
        assert len(results) >= 1

    def test_no_results(self, session: SessionMemory) -> None:
        session.save_conversation("Hello", "World")
        results = session.search_logs("nonexistent_keyword_xyz")
        assert len(results) == 0


class TestCleanup:
    """Verify log file cleanup."""

    def test_deletes_old_logs(self, session: SessionMemory) -> None:
        # Create a fake old log file
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        old_file = session.logs_path / f"{old_date}.md"
        old_file.write_text("# Old log", encoding="utf-8")

        deleted = session.cleanup()
        assert deleted >= 1
        assert not old_file.exists()

    def test_keeps_recent_logs(self, session: SessionMemory) -> None:
        session.save_conversation("Today", "Now")
        deleted = session.cleanup()
        assert deleted == 0
        assert session.get_today_log() != ""

    def test_custom_keep_days(self, session: SessionMemory) -> None:
        # Create a 5-day-old log
        old_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
        old_file = session.logs_path / f"{old_date}.md"
        old_file.write_text("# 5 days ago", encoding="utf-8")

        # Keep 7 days -- should NOT delete
        deleted = session.cleanup(keep_days=7)
        assert deleted == 0
        assert old_file.exists()


class TestStats:
    """Verify stats reporting."""

    def test_stats_structure(self, session: SessionMemory) -> None:
        stats = session.get_stats()
        assert "log_files_count" in stats
        assert "total_log_size_kb" in stats
        assert "profile_size_kb" in stats
        assert "rolling_days" in stats
        assert "base_path" in stats


class TestExportImport:
    """Verify data export and import."""

    def test_round_trip(self, session: SessionMemory, tmp_path: Path) -> None:
        session.save_conversation("Export test", "Works!")
        session.update_profile("Preferences", "Theme: dark")

        # Export
        data = session.export()
        assert "profile" in data
        assert "logs" in data

        # Import into a new instance
        new_session = SessionMemory(base_path=str(tmp_path / "mem2"))
        result = new_session.import_data(data)
        assert result is True
        assert "Theme: dark" in new_session.get_profile()

    def test_import_invalid_date_skipped(self, session: SessionMemory) -> None:
        data = {"logs": {"not-a-date": "bad content"}}
        result = session.import_data(data)
        assert result is True  # should not crash
