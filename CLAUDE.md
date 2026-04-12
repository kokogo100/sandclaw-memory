# CLAUDE.md = AI Assistant Guide for sandclaw-memory

> This file helps AI coding assistants (Claude Code, Cursor, Copilot, etc.)
> understand how to use and work with the sandclaw-memory library.

## What is sandclaw-memory?

A zero-dependency Python library that gives AI applications long-term memory
with a self-growing tag dictionary. Three memory layers (L1 session, L2 summary,
L3 archive) provide temporal RAG without GPU or vector databases.

## Quick Start for AI Assistants

When a developer asks you to add memory to their app, use this pattern:

```python
import json
from sandclaw_memory import BrainMemory

# The developer MUST provide a tag_extractor function.
# This function calls an AI to extract tags from text.
# It is the ONLY required callback = everything else has defaults.
def tag_extractor(content: str) -> list[str]:
    # Replace with the developer's preferred AI (OpenAI, Claude, Gemini, etc.)
    # Must return list[str]
    ...

with BrainMemory(
    db_path="./memory",          # Directory for all memory files
    tag_extractor=tag_extractor, # REQUIRED
) as brain:
    brain.start_polling()        # Background tag extraction (every 15s)

    # Save conversation turns (goes to L1 session log)
    brain.save("User: What's React?\nAI: A frontend library.")

    # Save important content permanently (goes to L1 + L3 archive)
    brain.save("User prefers Python and TypeScript", source="archive")

    # Recall relevant memories for a query (auto-detects depth)
    context = brain.recall("what languages does the user know?")

    # Inject into LLM system prompt
    # messages = [{"role": "system", "content": f"Memory:\n{context}"}, ...]
```

## Architecture (for understanding code)

```
sandclaw_memory/
  brain.py       = BrainMemory: the ONLY class most users need
  session.py     = L1: 3-day rolling Markdown logs ({db_path}/logs/)
  summary.py     = L2: 30-day AI-generated summary (in-memory)
  permanent.py   = L3: SQLite + FTS5 permanent archive ({db_path}/archive.db)
  dispatcher.py  = Auto-detects search depth (CASUAL/STANDARD/DEEP)
  loader.py      = Budget-aware loading (15KB default, 40/30/30 split)
  renderer.py    = Formats memories as Markdown for LLM injection
  types.py       = Depth enum, MemoryEntry dataclass
  exceptions.py  = SandclawError hierarchy
  utils.py       = HookRegistry, now_iso(), truncate(), safe_json_loads()
```

## Key Concepts to Know

### Three Memory Layers

| Layer | Purpose | Storage | Retention |
|-------|---------|---------|-----------|
| L1 Session | Conversation logs | Markdown files | 3 days (rolling) |
| L2 Summary | Period summaries | In-memory cache | 30 days |
| L3 Archive | Important memories | SQLite + FTS5 | Forever |

### Self-Growing Tag Dictionary

This is the library's core innovation:
- **Stage 1**: `keyword_map` table maps known words to tags instantly (free, no AI)
- **Stage 2**: `tag_extractor` callback calls AI for unknown words (async, queued)
- Each AI-extracted tag registers new keywords in the map
- Over time, Stage 1 catches more words -> fewer AI calls -> lower cost

### Intent-Based Depth Detection

```python
brain.recall("hi")                    # -> CASUAL  (L1 only)
brain.recall("summarize this month")  # -> STANDARD (L1 + L2)
brain.recall("why did we pick React?")# -> DEEP    (L1 + L2 + L3)
brain.recall("test", depth="deep")    # -> forced DEEP
```

### The 5 AI Callbacks

| Callback | Required | Signature | Default |
|----------|----------|-----------|---------|
| `tag_extractor` | YES | `(str) -> list[str]` | None (must provide) |
| `promote_checker` | no | `(str) -> bool` | `len > 200 chars` |
| `depth_detector` | no | `(str) -> str` | Keyword matching |
| `duplicate_checker` | no | `(str, str) -> bool` | SequenceMatcher > 0.85 |
| `conflict_resolver` | no | `(str, str) -> str` | Keep newer text |

## Common Tasks

### "Add memory to my chatbot"

```python
# In the chat loop:
context = brain.recall(user_message)
# Add context to system prompt
brain.save(f"User: {user_message}\nAI: {ai_response}")
```

### "Save something important permanently"

```python
brain.save("Critical decision: migrate to FastAPI", source="archive")
# Or with explicit tags:
brain.save("Use PostgreSQL for main DB", source="archive", tags=["database", "decision"])
```

### "Search old memories"

```python
results = brain.search("python")  # Returns list[MemoryEntry]
for entry in results:
    print(entry.content, entry.tags, entry.created_at)
```

### "Run maintenance manually (no polling)"

```python
brain = BrainMemory(tag_extractor=my_func)
# Don't call start_polling()
brain.save("content", source="archive")
brain.run_maintenance()  # Process tag queue + cleanup NOW
```

### "Export/backup memory"

```python
data = brain.export_json(path="./backup.json")
# Later, import into a new brain:
brain2.import_json("./backup.json")
```

### "Hook into events"

```python
brain.on("after_save", lambda content, source: print(f"Saved: {source}"))
brain.on("after_cycle", lambda stats: print(f"Tags processed: {stats}"))
# Events: before_save, after_save, before_promote, after_promote, after_recall, after_cycle
```

### "Use with FastAPI"

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

brain = BrainMemory(tag_extractor=my_func, polling_interval=30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    brain.start_polling()
    yield
    brain.close()

app = FastAPI(lifespan=lifespan)
```

## Important Rules

1. **tag_extractor is REQUIRED** = passing `None` raises `ConfigurationError`
2. **Always call `close()` or use `with` statement** = prevents resource leaks
3. **Zero external dependencies** = only Python stdlib + sqlite3
4. **Thread-safe** = polling loop and main thread can access the same DB
5. **FTS5 is optional** = gracefully falls back to LIKE search if unavailable
6. **Python 3.9+** = uses `from __future__ import annotations` for type hints

## Development Commands

```bash
# Run tests
python -m pytest

# Run linter
ruff check sandclaw_memory/

# Run formatter
ruff format sandclaw_memory/

# Run type checker
pyright sandclaw_memory/

# Build package
python -m build
```

## File Layout on Disk

```
{db_path}/
  logs/
    2026-04-10.md    # L1 daily conversation log
    2026-04-11.md
    PROFILE.md       # L1 persistent user profile
  archive.db         # L3 SQLite database (memories + tags + keyword_map)
```

## Version

- Current: v0.1.0 "Remembering AI" (AI callback required, flat tags)
- Next: v0.2.0 "Growing AI" (built-in AI via Gemma 4, tag trees)
