"""Tests for the custom exception hierarchy."""

from __future__ import annotations

from sandclaw_memory.exceptions import (
    CallbackError,
    ConfigurationError,
    SandclawError,
    StorageError,
    TagExtractionError,
)


class TestExceptionHierarchy:
    """Verify that all exceptions inherit correctly."""

    def test_sandclaw_error_is_base(self) -> None:
        """SandclawError should be catchable as Exception."""
        assert issubclass(SandclawError, Exception)

    def test_configuration_error_is_sandclaw(self) -> None:
        assert issubclass(ConfigurationError, SandclawError)

    def test_storage_error_is_sandclaw(self) -> None:
        assert issubclass(StorageError, SandclawError)

    def test_callback_error_is_sandclaw(self) -> None:
        assert issubclass(CallbackError, SandclawError)

    def test_tag_extraction_error_is_callback(self) -> None:
        """TagExtractionError should be catchable as CallbackError AND SandclawError."""
        assert issubclass(TagExtractionError, CallbackError)
        assert issubclass(TagExtractionError, SandclawError)

    def test_catch_all_with_sandclaw_error(self) -> None:
        """A single 'except SandclawError' should catch every subclass."""
        for exc_class in [ConfigurationError, StorageError, CallbackError, TagExtractionError]:
            try:
                raise exc_class("test message")
            except SandclawError as e:
                assert str(e) == "test message"
            else:
                raise AssertionError(f"{exc_class.__name__} was not caught by SandclawError")

    def test_error_message_is_preserved(self) -> None:
        """Error messages should be readable and contain the original text."""
        msg = (
            "tag_extractor is required but got None. "
            "Provide a callable: BrainMemory(tag_extractor=my_func). "
            "See examples/basic_usage.py for reference."
        )
        err = ConfigurationError(msg)
        assert "tag_extractor is required" in str(err)
        assert "BrainMemory(tag_extractor=my_func)" in str(err)


class TestTypes:
    """Verify Depth enum and MemoryEntry dataclass."""

    def test_depth_values(self) -> None:
        from sandclaw_memory.types import Depth

        assert Depth.CASUAL.value == "casual"
        assert Depth.STANDARD.value == "standard"
        assert Depth.DEEP.value == "deep"

    def test_depth_from_string(self) -> None:
        from sandclaw_memory.types import Depth

        assert Depth("casual") == Depth.CASUAL
        assert Depth("deep") == Depth.DEEP

    def test_memory_entry_defaults(self) -> None:
        from sandclaw_memory.types import MemoryEntry

        entry = MemoryEntry()
        assert entry.id == 0
        assert entry.content == ""
        assert entry.content_type == "general"
        assert entry.tags == []
        assert entry.source == "chat"
        assert entry.metadata == {}

    def test_memory_entry_custom_values(self) -> None:
        from sandclaw_memory.types import MemoryEntry

        entry = MemoryEntry(
            id=42,
            content="Fixed login bug",
            content_type="bugfix",
            tags=["auth", "frontend"],
            source="archive",
            metadata={"jira": "PROJ-123"},
            created_at="2026-04-12T10:00:00+00:00",
        )
        assert entry.id == 42
        assert "login" in entry.content
        assert "auth" in entry.tags
        assert entry.metadata["jira"] == "PROJ-123"

    def test_memory_entry_tags_are_independent(self) -> None:
        """Each MemoryEntry should have its own tags list (not shared)."""
        from sandclaw_memory.types import MemoryEntry

        entry1 = MemoryEntry()
        entry2 = MemoryEntry()
        entry1.tags.append("python")
        assert entry2.tags == []  # must NOT be affected


class TestUtils:
    """Verify utility functions."""

    def test_now_iso_format(self) -> None:
        from sandclaw_memory.utils import now_iso

        ts = now_iso()
        # Should be a valid ISO 8601 string with timezone
        assert "T" in ts
        assert "+" in ts or "Z" in ts

    def test_truncate_short_text(self) -> None:
        from sandclaw_memory.utils import truncate

        assert truncate("Hello", 50) == "Hello"

    def test_truncate_long_text(self) -> None:
        from sandclaw_memory.utils import truncate

        result = truncate("Hello World", 8)
        assert len(result) <= 8
        assert result.endswith("...")

    def test_truncate_custom_suffix(self) -> None:
        from sandclaw_memory.utils import truncate

        result = truncate("Hello World", 8, "[+]")
        assert result.endswith("[+]")
        assert len(result) <= 8

    def test_safe_json_loads_valid(self) -> None:
        from sandclaw_memory.utils import safe_json_loads

        assert safe_json_loads('["react", "python"]') == ["react", "python"]
        assert safe_json_loads('{"key": 1}') == {"key": 1}

    def test_safe_json_loads_invalid(self) -> None:
        from sandclaw_memory.utils import safe_json_loads

        assert safe_json_loads("not json") is None
        assert safe_json_loads("bad", default=[]) == []

    def test_hook_registry_fire(self) -> None:
        from sandclaw_memory.utils import HookRegistry

        results: list[str] = []
        hooks = HookRegistry()
        hooks.register("test_event", lambda msg: results.append(msg))
        hooks.fire("test_event", "hello")
        assert results == ["hello"]

    def test_hook_registry_multiple(self) -> None:
        from sandclaw_memory.utils import HookRegistry

        count = []
        hooks = HookRegistry()
        hooks.register("evt", lambda: count.append(1))
        hooks.register("evt", lambda: count.append(2))
        hooks.fire("evt")
        assert count == [1, 2]

    def test_hook_registry_error_swallowed(self) -> None:
        """A crashing hook should NOT prevent other hooks from running."""
        from sandclaw_memory.utils import HookRegistry

        results: list[str] = []
        hooks = HookRegistry()
        hooks.register("evt", lambda: (_ for _ in ()).throw(ValueError("boom")))
        hooks.register("evt", lambda: results.append("ok"))
        hooks.fire("evt")
        # The second hook should still run
        assert results == ["ok"]

    def test_hook_registry_unknown_event(self) -> None:
        """Firing an event with no registered hooks should not crash."""
        from sandclaw_memory.utils import HookRegistry

        hooks = HookRegistry()
        hooks.fire("nonexistent_event")  # should not raise
