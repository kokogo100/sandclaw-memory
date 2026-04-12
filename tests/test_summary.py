"""Tests for L2 SummaryMemory."""

from __future__ import annotations

from unittest.mock import MagicMock

from sandclaw_memory.summary import SummaryMemory


class TestCollectData:
    """Verify data collection from L1 and L3."""

    def test_collects_from_session(self) -> None:
        session = MagicMock()
        session.get_context.return_value = "Session content"
        archive = MagicMock()
        archive.search_by_date.return_value = []

        sm = SummaryMemory()
        data = sm.collect_data(session, archive)

        assert data["session_context"] == "Session content"
        assert "collected_at" in data

    def test_collects_from_archive(self) -> None:
        session = MagicMock()
        session.get_context.return_value = ""

        entry = MagicMock()
        entry.content = "Important memory"
        entry.tags = ["python"]
        entry.created_at = "2026-04-01"
        archive = MagicMock()
        archive.search_by_date.return_value = [entry]

        sm = SummaryMemory()
        data = sm.collect_data(session, archive)
        assert len(data["archive_entries"]) == 1

    def test_handles_none_layers(self) -> None:
        sm = SummaryMemory()
        data = sm.collect_data(None, None)
        assert data["session_context"] == ""
        assert data["archive_entries"] == []


class TestGenerate:
    """Verify summary generation."""

    def test_with_llm_callback(self) -> None:
        sm = SummaryMemory()
        data = {"session_context": "test", "archive_entries": [], "days": 30}

        def mock_llm(prompt: str) -> str:
            return "AI generated summary"

        result = sm.generate(data, llm_callback=mock_llm)
        assert result == "AI generated summary"
        assert sm.get_summary() == "AI generated summary"

    def test_without_callback_uses_fallback(self) -> None:
        sm = SummaryMemory()
        data = {
            "session_context": "",
            "archive_entries": [{"content": "Memory one", "tags": ["test"]}],
            "days": 30,
        }

        result = sm.generate(data, llm_callback=None)
        assert "30-Day Summary" in result
        assert "Memory one" in result

    def test_callback_failure_uses_fallback(self) -> None:
        sm = SummaryMemory()
        data = {"session_context": "", "archive_entries": [], "days": 7}

        def broken_llm(prompt: str) -> str:
            raise ValueError("API timeout")

        result = sm.generate(data, llm_callback=broken_llm)
        assert "Summary" in result  # should not crash

    def test_get_summary_empty_before_generate(self) -> None:
        sm = SummaryMemory()
        assert sm.get_summary() == ""
