# Architecture

## Overview

sandclaw-memory is a 3-layer temporal RAG system with a self-growing tag dictionary.

```
User Application
       │
       ▼
┌──────────────┐
│  BrainMemory │ ← The only class most users need
│  (brain.py)  │
└──────┬───────┘
       │
       ├── save()   → routes content to the right layer
       ├── recall()  → auto-detects depth, loads, renders
       └── start_polling() → background tag extraction
       │
       ▼
┌──────────────────────────────────────────────┐
│              Three Memory Layers              │
│                                               │
│  ┌─────────┐  ┌──────────┐  ┌─────────────┐  │
│  │   L1    │  │    L2    │  │     L3      │  │
│  │ Session │  │ Summary  │  │  Archive    │  │
│  │ 3 days  │  │ 30 days  │  │  Forever    │  │
│  │   .md   │  │ in-mem   │  │  SQLite     │  │
│  └─────────┘  └──────────┘  └─────────────┘  │
│                                               │
├───────────────────────────────────────────────┤
│  IntentDispatcher → TieredLoader → Renderer   │
│  (depth detect)    (budget load)   (Markdown)  │
└───────────────────────────────────────────────┘
```

## Memory Layers

### L1: SessionMemory (session.py)

**Purpose**: Short-term conversation log.

- Stores daily Markdown files in `{db_path}/logs/YYYY-MM-DD.md`
- Maintains a persistent `PROFILE.md` for user profile
- Rolling window: keeps the last N days (default 3), deletes older logs
- Fast to read (just load a text file)

**When to use**: Every conversation turn is automatically saved here.

### L2: SummaryMemory (summary.py)

**Purpose**: Mid-term aggregated summary.

- Collects data from L1 (session) and L3 (archive)
- Generates a 30-day summary using AI callback or fallback
- Cached in memory (regenerated on demand)

**When to use**: For "summarize this month" type queries.

### L3: ArchiveMemory (permanent.py)

**Purpose**: Permanent long-term storage.

- SQLite database with FTS5 full-text search
- BM25 ranking (same algorithm as search engines)
- Self-growing tag dictionary via 2-stage pipeline
- Thread-safe (threading.Lock)

**Schema**:
```sql
memories       = content, tags, source, metadata, timestamps
memories_fts   = FTS5 virtual table (content + tags)
tag_index      = tag → group mapping
keyword_map    = keyword → tag mapping (self-growing!)
tag_queue      = pending AI extractions
```

## Self-Growing Tag Pipeline

This is the key innovation. It works in 2 stages:

### Stage 1: Keyword Map (instant, free)

When you save "React Native app", the system checks `keyword_map`:
- If "React" → "react" exists in the map → instant match, no AI needed
- Tags applied immediately, zero cost

### Stage 2: AI Callback (async, queued)

If Stage 1 doesn't find all tags:
- Content goes into `tag_queue`
- Background polling calls `tag_extractor` callback
- AI returns tags like `["react-native", "mobile", "app"]`
- New keywords registered in `keyword_map`

### The Growth Effect

```
Day 1:   keyword_map = {}                 → 100% AI calls
Day 7:   keyword_map = {50 keywords}      → ~60% AI calls
Day 30:  keyword_map = {200 keywords}     → ~30% AI calls
Day 90:  keyword_map = {500+ keywords}    → ~10% AI calls
```

Each AI call teaches the system new keywords. Over time, most content matches existing keywords and AI calls become rare.

## Intent Dispatcher (dispatcher.py)

Detects search depth from the query:

| Depth | Layers | Triggers |
|---|---|---|
| CASUAL | L1 | "today", "just now", simple questions |
| STANDARD | L1 + L2 | "this month", "summary", "trend" |
| DEEP | L1 + L2 + L3 | "why", "months ago", "history" |

Priority:
1. `depth_detector` AI callback (if provided)
2. Built-in keyword matching (English, Korean, Japanese)
3. Default: CASUAL

## TieredLoader (loader.py)

Loads memories within a context budget:

- Default budget: 15,000 characters
- L1 gets 40%, L2 gets 30%, L3 gets 30%
- Each layer's output is truncated to its budget share
- Prevents exceeding LLM context limits

## Polling Loop

Background `threading.Timer` daemon thread:

1. Process tag queue (AI extraction)
2. Clean up old L1 logs
3. Fire `after_cycle` hook
4. Reschedule next cycle

Alternatives to polling:
- `run_maintenance()` for manual control
- FastAPI lifespan for web apps
- Celery Beat for distributed systems

## Thread Safety

- `ArchiveMemory` uses `threading.Lock` for all DB operations
- Polling thread and main thread can safely access the same DB
- `SessionMemory` uses file-based storage (no locking needed)

## File Layout

```
{db_path}/
  logs/
    2026-04-10.md    ← L1 daily logs
    2026-04-11.md
    2026-04-12.md
    PROFILE.md       ← L1 user profile
  archive.db         ← L3 SQLite database
```
