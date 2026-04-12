# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure
- Core types: `Depth` enum, `MemoryEntry` dataclass
- Custom exception hierarchy (`SandclawError` and subclasses)
- Utility helpers (`HookRegistry`, timestamp, text truncation)

## [0.1.0] - TBD

### Added
- L1 `SessionMemory` — 3-day rolling Markdown logs
- L2 `SummaryMemory` — 30-day AI-generated summaries
- L3 `ArchiveMemory` — permanent SQLite + FTS5 storage with self-growing tags
- `IntentDispatcher` — intent-based depth detection (CASUAL / STANDARD / DEEP)
- `TieredLoader` — layered loading with 15 KB context budget
- `MarkdownRenderer` — LLM-ready Markdown output
- `BrainMemory` — orchestrator with polling loop and context manager
- 5 AI callbacks (tag_extractor required + 4 optional)
- Event hooks (before_save, after_save, after_recall, etc.)
- JSON / JSONL export and import
- Optional SQLCipher encryption
- Zero external dependencies
