"""Tests for IntentDispatcher."""

from __future__ import annotations

from sandclaw_memory.dispatcher import IntentDispatcher
from sandclaw_memory.types import Depth


class TestKeywordDetection:
    """Verify keyword-based depth detection."""

    def test_casual_default(self) -> None:
        d = IntentDispatcher()
        assert d.detect("hello how are you?") == Depth.CASUAL

    def test_deep_english(self) -> None:
        d = IntentDispatcher()
        assert d.detect("what rule did I set 3 months ago?") == Depth.DEEP

    def test_deep_korean(self) -> None:
        d = IntentDispatcher()
        assert d.detect("3개월 전에 정한 규칙이 뭐야?") == Depth.DEEP

    def test_standard_english(self) -> None:
        d = IntentDispatcher()
        assert d.detect("give me a summary of last week") == Depth.STANDARD

    def test_standard_korean(self) -> None:
        d = IntentDispatcher()
        assert d.detect("최근 요약 보여줘") == Depth.STANDARD

    def test_deep_japanese(self) -> None:
        d = IntentDispatcher()
        assert d.detect("以前のルールを確認したい") == Depth.DEEP


class TestCallbackDetection:
    """Verify AI callback depth detection."""

    def test_callback_priority(self) -> None:
        """Callback should override keyword matching."""
        def always_deep(query: str) -> str:
            return "deep"

        d = IntentDispatcher(depth_detector=always_deep)
        # "hello" would normally be CASUAL, but callback says DEEP
        assert d.detect("hello") == Depth.DEEP

    def test_callback_failure_fallback(self) -> None:
        """If callback fails, should fall back to keywords."""
        def broken_detector(query: str) -> str:
            raise ValueError("API error")

        d = IntentDispatcher(depth_detector=broken_detector)
        # Should not crash, should fall back to keyword matching
        result = d.detect("what did I do 3 months ago?")
        assert result == Depth.DEEP  # keyword match still works
