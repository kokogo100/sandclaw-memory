"""Tests for TieredLoader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sandclaw_memory.loader import TieredLoader
from sandclaw_memory.types import Depth, MemoryEntry


@pytest.fixture
def loader() -> TieredLoader:
    return TieredLoader(max_context_chars=1000)


class TestLoad:
    """Verify layered loading behavior."""

    def test_casual_loads_l1_only(self, loader: TieredLoader) -> None:
        session = MagicMock()
        session.get_context.return_value = "Today's conversation"
        summary = MagicMock()
        archive = MagicMock()

        result = loader.load(Depth.CASUAL, session=session, summary=summary, archive=archive)

        session.get_context.assert_called_once()
        summary.get_summary.assert_not_called()
        archive.search.assert_not_called()
        assert "Today's conversation" in result

    def test_standard_loads_l1_and_l2(self, loader: TieredLoader) -> None:
        session = MagicMock()
        session.get_context.return_value = "Session data"
        summary = MagicMock()
        summary.get_summary.return_value = "Monthly summary"
        archive = MagicMock()

        result = loader.load(Depth.STANDARD, session=session, summary=summary, archive=archive)

        session.get_context.assert_called_once()
        summary.get_summary.assert_called_once()
        archive.search.assert_not_called()
        assert "Session data" in result
        assert "Monthly summary" in result

    def test_deep_loads_all_layers(self, loader: TieredLoader) -> None:
        session = MagicMock()
        session.get_context.return_value = "Session"
        summary = MagicMock()
        summary.get_summary.return_value = "Summary"
        archive = MagicMock()
        archive.search.return_value = [
            MemoryEntry(content="Archive entry", tags=["python"])
        ]

        result = loader.load(
            Depth.DEEP, query="python", session=session, summary=summary, archive=archive
        )

        session.get_context.assert_called_once()
        summary.get_summary.assert_called_once()
        archive.search.assert_called_once()
        assert "Archive entry" in result

    def test_respects_budget(self) -> None:
        small_loader = TieredLoader(max_context_chars=100)
        session = MagicMock()
        session.get_context.return_value = "A" * 500

        result = small_loader.load(Depth.CASUAL, session=session)
        assert len(result) <= 100 + 10  # small margin for truncation suffix

    def test_handles_none_layers(self, loader: TieredLoader) -> None:
        """Should not crash if layers are None."""
        result = loader.load(Depth.DEEP, query="test", session=None, summary=None, archive=None)
        assert isinstance(result, str)
