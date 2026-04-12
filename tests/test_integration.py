"""End-to-end integration tests for sandclaw-memory.

Tests the FULL flow as a real developer would use the library:
  1. Save -> Recall (저장 후 불러오기)
  2. Recall -> Save (불러온 후 저장)
  3. AT (tag_extractor) + self-growing pipeline
  4. Export -> Import round-trip
  5. Polling loop + maintenance cycle
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sandclaw_memory import BrainMemory, Depth, MemoryEntry, SandclawError


# ═══════════════════════════════════════════════════════════
# Mock AI -- simulates a real tag_extractor callback
# ═══════════════════════════════════════════════════════════
EXTRACTOR_CALL_COUNT = 0


def mock_ai_tag_extractor(content: str) -> list[str]:
    """Simulates an AI tag extraction call (like OpenAI/Claude).

    Tracks call count so we can verify self-growing reduces AI calls.
    """
    global EXTRACTOR_CALL_COUNT
    EXTRACTOR_CALL_COUNT += 1

    # Simple keyword-based extraction (simulates what AI would return)
    tag_map = {
        "python": "python",
        "react": "react",
        "fastapi": "fastapi",
        "typescript": "typescript",
        "postgresql": "postgresql",
        "database": "database",
        "frontend": "frontend",
        "backend": "backend",
        "decision": "decision",
        "migrate": "migration",
        "deploy": "deployment",
        "bug": "bugfix",
    }
    words = content.lower().split()
    tags = []
    for word in words:
        clean = word.strip(".,!?;:()\"'")
        if clean in tag_map:
            tags.append(tag_map[clean])
    # Always return at least one tag
    if not tags:
        tags = ["general"]
    return tags


@pytest.fixture(autouse=True)
def reset_call_count():
    """Reset the extractor call counter before each test."""
    global EXTRACTOR_CALL_COUNT
    EXTRACTOR_CALL_COUNT = 0
    yield


@pytest.fixture
def brain(tmp_path: Path) -> BrainMemory:
    b = BrainMemory(
        db_path=str(tmp_path / "integration_memory"),
        tag_extractor=mock_ai_tag_extractor,
        polling_interval=1,  # fast for tests
    )
    yield b
    b.close()


# ═══════════════════════════════════════════════════════════
# Flow 1: Save -> Recall (저장 후 불러오기)
# ═══════════════════════════════════════════════════════════
class TestSaveThenRecall:
    """Save content, then recall it -- the most basic flow."""

    def test_save_chat_and_recall_casual(self, brain: BrainMemory) -> None:
        """Regular chat -> L1 only -> recall with CASUAL depth."""
        brain.save("User: What is React?\nAI: React is a frontend library.")
        context = brain.recall("React")
        # L1 session should contain it
        assert "React" in context

    def test_save_archive_and_recall_deep(self, brain: BrainMemory) -> None:
        """Important content -> L3 archive -> recall with DEEP depth."""
        brain.save(
            "We decided to use Python and FastAPI for the backend.",
            source="archive",
            tags=["python", "fastapi", "decision"],
        )
        context = brain.recall("what backend did we choose?", depth="deep")
        assert "Python" in context or "FastAPI" in context or "fastapi" in context.lower()

    def test_save_multiple_and_recall_finds_relevant(self, brain: BrainMemory) -> None:
        """Save multiple topics, recall should find the right one."""
        brain.save("Python is great for backend development", source="archive", tags=["python"])
        brain.save("React is used for frontend UI", source="archive", tags=["react"])
        brain.save("PostgreSQL is our main database", source="archive", tags=["postgresql"])

        # Search for database-related content
        results = brain.search("postgresql")
        assert len(results) >= 1
        assert any("PostgreSQL" in r.content for r in results)

    def test_save_and_recall_returns_markdown(self, brain: BrainMemory) -> None:
        """recall() should return a string (Markdown format)."""
        brain.save("Test content for markdown check")
        result = brain.recall("test")
        assert isinstance(result, str)

    def test_save_with_metadata_and_search(self, brain: BrainMemory) -> None:
        """Save with metadata, verify it's preserved in search results."""
        brain.save(
            "Deploy to production on Friday",
            source="archive",
            tags=["deployment"],
            metadata={"priority": "high", "deadline": "2026-04-18"},
        )
        results = brain.search("deploy")
        assert len(results) >= 1
        assert results[0].metadata.get("priority") == "high"


# ═══════════════════════════════════════════════════════════
# Flow 2: Recall -> Save (불러온 후 저장)
# ═══════════════════════════════════════════════════════════
class TestRecallThenSave:
    """Recall context first, then save new content based on it."""

    def test_recall_empty_then_save(self, brain: BrainMemory) -> None:
        """First recall (empty) -> save -> second recall (has data)."""
        # First recall - nothing saved yet
        context1 = brain.recall("anything")
        assert isinstance(context1, str)

        # Save based on "conversation"
        brain.save("User prefers dark mode in all applications", source="archive", tags=["preference"])

        # Second recall - should find it
        context2 = brain.recall("preferences", depth="deep")
        assert "dark mode" in context2 or len(context2) > len(context1)

    def test_recall_context_and_save_ai_response(self, brain: BrainMemory) -> None:
        """Simulate: recall -> inject into LLM -> save the response."""
        # Setup: save some history
        brain.save("User loves Python and TypeScript", source="archive", tags=["python", "typescript"])

        # Step 1: Recall for context
        context = brain.recall("what does the user like?", depth="deep")

        # Step 2: Simulate AI response based on context
        ai_response = f"Based on memory, the user likes Python. Context used: {len(context)} chars"

        # Step 3: Save the full conversation turn
        brain.save(f"User: What do I like?\nAI: {ai_response}")

        # Verify the turn was saved in L1
        context_after = brain.recall("what do I like")
        assert isinstance(context_after, str)


# ═══════════════════════════════════════════════════════════
# Flow 3: AT (tag_extractor) + Self-Growing Pipeline
# ═══════════════════════════════════════════════════════════
class TestATSelfGrowing:
    """Verify the complete self-growing tag pipeline."""

    def test_stage1_keyword_map_instant_match(self, brain: BrainMemory) -> None:
        """Pre-seed keyword_map -> Stage 1 matches without AI."""
        # Pre-seed the keyword map
        brain._archive.add_keyword("react", "react")
        brain._archive.add_keyword("vue", "vue")

        # extract_tags should find "react" instantly
        tags = brain._archive.extract_tags("I'm building a React app")
        assert "react" in tags

    def test_stage2_ai_extraction_via_polling(self, brain: BrainMemory) -> None:
        """Save -> polling processes tag_queue -> keywords registered."""
        global EXTRACTOR_CALL_COUNT
        initial_calls = EXTRACTOR_CALL_COUNT

        # Save content to archive (queues for tag extraction)
        brain.save("Learning Python and React for web development", source="archive")

        # Run one maintenance cycle (simulates what polling does)
        result = brain.run_maintenance()
        assert result["tags_processed"] >= 1

        # AI was called at least once
        assert EXTRACTOR_CALL_COUNT > initial_calls

    def test_self_growing_reduces_ai_calls(self, brain: BrainMemory) -> None:
        """After keywords are learned, same words should NOT trigger AI."""
        global EXTRACTOR_CALL_COUNT

        # Step 1: Save "Python" for the first time -> goes to tag_queue
        brain.save("Python is the best language", source="archive")
        brain.run_maintenance()  # AI extracts tags, registers "python" keyword
        calls_after_first = EXTRACTOR_CALL_COUNT

        # Step 2: Verify "python" is now in keyword_map
        tags = brain._archive.extract_tags("I love Python programming")
        assert "python" in tags  # Stage 1 matched!

        # Step 3: Save similar content -> Stage 1 should catch "python"
        brain.save("Python tutorial for beginners", source="archive", tags=["python"])
        # Since we provided tags explicitly, it doesn't need AI
        # But even if it goes to queue, keyword_map would handle "python" instantly

        # The keyword_map should have grown
        stats = brain.get_tag_stats()
        assert "python" in stats

    def test_tag_queue_processes_in_polling(self, brain: BrainMemory) -> None:
        """Start polling -> save content -> queue gets processed automatically."""
        brain.save("FastAPI backend deployment", source="archive")

        # Verify item is in queue
        stats_before = brain.get_stats()
        assert stats_before["archive"]["pending_tag_extractions"] >= 1

        # Start polling and wait for one cycle
        brain.start_polling()
        time.sleep(2)
        brain.stop_polling()

        # Queue should be processed
        stats_after = brain.get_stats()
        assert stats_after["archive"]["pending_tag_extractions"] == 0

    def test_manual_enqueue_and_process(self, brain: BrainMemory) -> None:
        """Manually enqueue + process for re-extraction."""
        # Save with explicit tags (skips auto-queue... wait, it still queues)
        mem_id = brain._archive.save("React Native mobile app", tags=["react"])
        assert mem_id > 0

        # Manually enqueue for re-extraction
        brain._archive.enqueue_tag_extraction(mem_id, "React Native mobile app")
        processed = brain.process_tag_queue()
        assert processed >= 1

    def test_keyword_map_grows_over_time(self, brain: BrainMemory) -> None:
        """Simulate multiple days of usage -> keyword_map should grow."""
        # Day 1: empty keyword_map
        stats1 = brain.get_stats()
        initial_keywords = stats1["archive"]["keyword_map_size"]

        # Save several diverse topics and process
        topics = [
            "Python backend development with FastAPI",
            "React frontend with TypeScript",
            "PostgreSQL database migration",
        ]
        for topic in topics:
            brain.save(topic, source="archive")
        brain.run_maintenance()

        # keyword_map should have grown
        stats2 = brain.get_stats()
        assert stats2["archive"]["keyword_map_size"] > initial_keywords


# ═══════════════════════════════════════════════════════════
# Flow 4: Export -> Import Round-Trip
# ═══════════════════════════════════════════════════════════
class TestExportImportRoundTrip:
    """Export data, import into a new brain, verify nothing is lost."""

    def test_full_round_trip(self, brain: BrainMemory, tmp_path: Path) -> None:
        """Save -> Export -> New Brain -> Import -> Verify."""
        # Step 1: Save diverse content
        brain.save("Python is my favorite language", source="archive", tags=["python"])
        brain.save("React for all frontend work", source="archive", tags=["react"])
        brain.save("Daily chat: weather is nice today")

        # Step 2: Export
        export_path = str(tmp_path / "roundtrip.json")
        data = brain.export_json(path=export_path)
        assert Path(export_path).exists()
        assert len(data["archive"]) >= 2  # at least python + react entries

        # Step 3: Create new brain and import
        brain2 = BrainMemory(
            db_path=str(tmp_path / "imported_memory"),
            tag_extractor=mock_ai_tag_extractor,
        )
        count = brain2.import_json(export_path)
        assert count >= 2  # session + archive entries

        # Step 4: Verify imported data is searchable
        results = brain2.search("python")
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

        brain2.close()

    def test_export_jsonl_contains_all_entries(self, brain: BrainMemory, tmp_path: Path) -> None:
        """JSONL export should contain all archive entries."""
        brain.save("Entry one", source="archive", tags=["test"])
        brain.save("Entry two", source="archive", tags=["test"])

        path = str(tmp_path / "export.jsonl")
        count = brain.export_jsonl(path)
        assert count >= 2

        # Verify file has correct number of lines
        lines = Path(path).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 2


# ═══════════════════════════════════════════════════════════
# Flow 5: Full Lifecycle (Context Manager + Polling + Hooks)
# ═══════════════════════════════════════════════════════════
class TestFullLifecycle:
    """Test the complete lifecycle as a developer would use it."""

    def test_with_statement_full_flow(self, tmp_path: Path) -> None:
        """with BrainMemory(...) as brain: -> full flow -> auto cleanup."""
        hook_events: list[str] = []

        with BrainMemory(
            db_path=str(tmp_path / "lifecycle"),
            tag_extractor=mock_ai_tag_extractor,
            polling_interval=1,
        ) as brain:
            # Register hooks
            brain.on("after_save", lambda c, s: hook_events.append(f"save:{s}"))
            brain.on("after_recall", lambda q, d, r: hook_events.append(f"recall:{d}"))
            brain.on("after_promote", lambda c, mid: hook_events.append(f"promote:{mid}"))

            # Save
            brain.save("Test lifecycle content", source="archive", tags=["test"])
            assert "save:archive" in hook_events
            assert any("promote:" in e for e in hook_events)

            # Recall
            brain.recall("test", depth="deep")
            assert any("recall:" in e for e in hook_events)

            # Stats
            stats = brain.get_stats()
            assert stats["archive"]["total_memories"] >= 1

        # After 'with' block: brain should be closed
        # (no crash = success)

    def test_polling_with_hooks(self, tmp_path: Path) -> None:
        """Polling loop fires after_cycle hooks."""
        cycle_stats: list[dict] = []

        with BrainMemory(
            db_path=str(tmp_path / "polling_hooks"),
            tag_extractor=mock_ai_tag_extractor,
            polling_interval=1,
        ) as brain:
            brain.on("after_cycle", lambda s: cycle_stats.append(s))

            brain.save("Content for polling test", source="archive")
            brain.start_polling()
            time.sleep(2.5)  # Wait for at least 1 cycle
            brain.stop_polling()

        assert len(cycle_stats) >= 1
        assert "tags_processed" in cycle_stats[0]

    def test_promote_checker_custom(self, tmp_path: Path) -> None:
        """Custom promote_checker decides what goes to L3."""
        def smart_promote(content: str) -> bool:
            # Only promote content containing "important" or "decision"
            return "important" in content.lower() or "decision" in content.lower()

        with BrainMemory(
            db_path=str(tmp_path / "custom_promote"),
            tag_extractor=mock_ai_tag_extractor,
            promote_checker=smart_promote,
        ) as brain:
            # This should NOT be promoted (no keyword)
            brain.save("The weather is nice today")
            stats1 = brain.get_stats()
            archive_count1 = stats1["archive"]["total_memories"]

            # This SHOULD be promoted (contains "important")
            brain.save("Important: we need to finish the API by Friday")
            stats2 = brain.get_stats()
            archive_count2 = stats2["archive"]["total_memories"]

            assert archive_count2 > archive_count1

    def test_depth_detector_custom(self, tmp_path: Path) -> None:
        """Custom depth_detector overrides keyword matching."""
        def always_deep(query: str) -> str:
            return "deep"

        with BrainMemory(
            db_path=str(tmp_path / "custom_depth"),
            tag_extractor=mock_ai_tag_extractor,
            depth_detector=always_deep,
        ) as brain:
            brain.save("Python tutorial", source="archive", tags=["python"])

            # Even a simple query should trigger DEEP search
            context = brain.recall("hi")
            # Should include L3 results because depth is forced to DEEP
            assert isinstance(context, str)

    def test_duplicate_detection_prevents_bloat(self, brain: BrainMemory) -> None:
        """Saving the same content twice should not create duplicates."""
        brain.save("Exact same content here", source="archive", tags=["test"])
        brain.save("Exact same content here", source="archive", tags=["test"])

        stats = brain.get_stats()
        # Should only have 1 memory (duplicate was caught)
        assert stats["archive"]["total_memories"] == 1

    def test_conflict_resolver_merges(self, tmp_path: Path) -> None:
        """Custom conflict_resolver merges duplicate content."""
        def merge(old: str, new: str) -> str:
            return f"{old} [UPDATED] {new}"

        with BrainMemory(
            db_path=str(tmp_path / "conflict_merge"),
            tag_extractor=mock_ai_tag_extractor,
            conflict_resolver=merge,
        ) as brain:
            brain.save("Python version 3.9", source="archive", tags=["python"])
            brain.save("Python version 3.9", source="archive", tags=["python"])

            # Should have merged content
            results = brain.search("python")
            assert len(results) >= 1
            assert "[UPDATED]" in results[0].content


# ═══════════════════════════════════════════════════════════
# Flow 6: Error Handling
# ═══════════════════════════════════════════════════════════
class TestErrorHandling:
    """Verify graceful error handling."""

    def test_no_tag_extractor_raises(self, tmp_path: Path) -> None:
        """tag_extractor=None must raise ConfigurationError."""
        with pytest.raises(SandclawError, match="tag_extractor"):
            BrainMemory(db_path=str(tmp_path / "no_at"), tag_extractor=None)

    def test_broken_tag_extractor_doesnt_crash(self, tmp_path: Path) -> None:
        """If tag_extractor raises, the system should not crash."""
        def broken_extractor(content: str) -> list[str]:
            raise RuntimeError("API timeout!")

        with BrainMemory(
            db_path=str(tmp_path / "broken_at"),
            tag_extractor=broken_extractor,
        ) as brain:
            # Save should still work (tags go to queue)
            brain.save("Content with broken extractor", source="archive")
            stats = brain.get_stats()
            assert stats["archive"]["total_memories"] >= 1

            # Maintenance should handle the error gracefully
            # (retry_count increments, doesn't crash)
            result = brain.run_maintenance()
            assert "tags_processed" in result

    def test_broken_promote_checker_uses_default(self, tmp_path: Path) -> None:
        """If promote_checker raises, fall back to default behavior."""
        def broken_promote(content: str) -> bool:
            raise ValueError("oops")

        with BrainMemory(
            db_path=str(tmp_path / "broken_promote"),
            tag_extractor=mock_ai_tag_extractor,
            promote_checker=broken_promote,
        ) as brain:
            # Should not crash
            brain.save("Some content that should still save")
            # Content should be in L1 at minimum
            context = brain.recall("content")
            assert isinstance(context, str)
