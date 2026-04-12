<p align="center">
  <h1 align="center">sandclaw-memory</h1>
  <p align="center"><strong>Self-Growing Tag-Dictionary RAG for Any Device</strong></p>
</p>

<p align="center">
  <a href="https://pypi.org/project/sandclaw-memory/"><img src="https://img.shields.io/pypi/v/sandclaw-memory?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/sandclaw-memory/"><img src="https://img.shields.io/pypi/pyversions/sandclaw-memory" alt="Python"></a>
  <a href="https://github.com/kokogo100/sandclaw-memory/blob/main/LICENSE"><img src="https://img.shields.io/github/license/kokogo100/sandclaw-memory" alt="License"></a>
  <a href="https://github.com/kokogo100/sandclaw-memory/actions"><img src="https://img.shields.io/github/actions/workflow/status/kokogo100/sandclaw-memory/ci.yml?label=tests" alt="Tests"></a>
</p>

---

Give your AI **long-term memory that grows smarter over time.**

No GPU. No vector database. No external dependencies.
Just `pip install` and go.

```python
from sandclaw_memory import BrainMemory

brain = BrainMemory(tag_extractor=my_ai_func)
brain.save("User loves Python and React")
context = brain.recall("what does the user like?")
# -> Returns relevant memories as Markdown, ready for LLM injection
```

## Why sandclaw-memory?

| Feature | sandclaw-memory | Vector DB (Pinecone, Weaviate) | mem0 |
|---|---|---|---|
| **Setup** | `pip install` (done) | Docker + API keys + config | `pip install` + API key |
| **GPU required** | No | Often yes | No |
| **Cost over time** | Decreases (self-growing) | Constant | Constant |
| **Search** | FTS5 + BM25 (proven) | Cosine similarity | Embedding-based |
| **Privacy** | 100% local | Cloud required | Cloud optional |
| **Dependencies** | 0 (stdlib only) | Many | Several |
| **Size** | ~50KB | 100MB+ Docker | ~5MB |

### The Self-Growing Advantage

Traditional RAG calls AI for **every** search. sandclaw-memory learns:

```
Day 1:  "React로 페이지 만듦"  → AI extracts: [react, frontend, page]
         keyword_map registers: "React" → react, "페이지" → page

Day 30: "React Native 시작"   → keyword_map instant match! No AI needed.
         Cost: $0.00

Day 90: 80% of saves match keyword_map → AI calls reduced by 80%
```

**The more you use it, the cheaper it gets.**

## Quick Start

### Install

```bash
pip install sandclaw-memory
```

### 3-Line Memory

```python
from sandclaw_memory import BrainMemory

with BrainMemory(tag_extractor=my_tag_func) as brain:
    brain.save("Important: migrate to FastAPI by Q2")
    print(brain.recall("what's the migration plan?"))
```

### With OpenAI

```python
import json, openai
from sandclaw_memory import BrainMemory

def tag_extractor(content: str) -> list[str]:
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "Extract 3-7 keyword tags. Return JSON array only."
        }, {"role": "user", "content": content}],
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)

with BrainMemory(
    db_path="./my_memory",
    tag_extractor=tag_extractor,
) as brain:
    brain.start_polling()  # Background tag extraction every 15s

    brain.save("User prefers Python and TypeScript")
    brain.save("Decided to use PostgreSQL", source="archive")

    context = brain.recall("what tech stack?")
    # Inject 'context' into your LLM's system prompt
```

### With Claude

```python
import json, anthropic
from sandclaw_memory import BrainMemory

client = anthropic.Anthropic()

def tag_extractor(content: str) -> list[str]:
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user",
                   "content": f"Extract 3-7 tags as JSON array:\n{content}"}],
    )
    return json.loads(resp.content[0].text)

brain = BrainMemory(tag_extractor=tag_extractor)
```

> See [`examples/`](examples/) for LangChain, custom callbacks, and scheduling patterns.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  BrainMemory                     │
│    save() → recall() → start_polling()          │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
│  │   L1    │  │    L2    │  │      L3        │  │
│  │ Session │  │ Summary  │  │   Archive      │  │
│  │         │  │          │  │                │  │
│  │ 3-day   │  │ 30-day   │  │ Permanent      │  │
│  │ rolling │  │ AI/text  │  │ SQLite + FTS5  │  │
│  │ Markdown│  │ summary  │  │ + self-growing │  │
│  │  logs   │  │          │  │   tag dict     │  │
│  └────┬────┘  └────┬─────┘  └───────┬────────┘  │
│       │            │                │            │
│  ┌────┴────────────┴────────────────┴────────┐  │
│  │          Intent Dispatcher                 │  │
│  │  CASUAL → L1  │ STANDARD → L1+L2         │  │
│  │               │ DEEP → L1+L2+L3           │  │
│  └───────────────┴───────────────────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │     Self-Growing Tag Pipeline            │   │
│  │  Stage 1: keyword_map (instant, free)    │   │
│  │  Stage 2: AI callback (async, queue)     │   │
│  │  → keyword_map grows → Stage 2 shrinks   │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Three Memory Layers

| Layer | What | Retention | Storage | Speed |
|---|---|---|---|---|
| **L1** Session | Conversation logs | 3 days (rolling) | Markdown files | Instant |
| **L2** Summary | Period summaries | 30 days | In-memory | Instant |
| **L3** Archive | Important memories | Forever | SQLite + FTS5 | ~1ms |

### Intent-Based Depth

The dispatcher auto-detects how deep to search:

```python
brain.recall("what time is it?")           # → CASUAL  (L1 only)
brain.recall("summarize this month")       # → STANDARD (L1 + L2)
brain.recall("why did we pick React?")     # → DEEP    (L1 + L2 + L3)

# Or override manually:
brain.recall("anything", depth="deep")
```

## API Reference

### BrainMemory

```python
BrainMemory(
    db_path="./memory",           # Where to store files
    tag_extractor=my_func,        # REQUIRED: (str) -> list[str]
    promote_checker=None,         # Optional: (str) -> bool
    depth_detector=None,          # Optional: (str) -> str
    duplicate_checker=None,       # Optional: (str, str) -> bool
    conflict_resolver=None,       # Optional: (str, str) -> str
    polling_interval=15,          # Seconds between maintenance cycles
    rolling_days=3,               # L1 retention period
    summary_days=30,              # L2 summary period
    max_context_chars=15_000,     # Context budget for LLM injection
    encryption_key=None,          # Optional SQLCipher encryption
)
```

### Core Methods

| Method | Description |
|---|---|
| `save(content, source="chat", tags=None)` | Save to memory. `source="archive"` forces L3. |
| `recall(query, depth=None)` | Recall relevant memories as Markdown. |
| `search(query, limit=20)` | Search L3 archive, returns `list[MemoryEntry]`. |
| `promote(content, tags=None)` | Manually save to L3. Returns memory ID. |
| `summarize(llm_callback=None)` | Generate a 30-day summary. |
| `start_polling()` | Start background maintenance loop. |
| `stop_polling()` | Stop background maintenance loop. |
| `run_maintenance()` | Run one maintenance cycle manually. |
| `get_stats()` | Get stats from all layers. |
| `get_tag_stats()` | Get tag usage counts. |
| `export_json(path=None)` | Export all data as JSON. |
| `on(event, callback)` | Register an event hook. |
| `close()` | Stop polling and close DB. |

### The 5 AI Callbacks

| Callback | Signature | Default |
|---|---|---|
| `tag_extractor` | `(str) -> list[str]` | **REQUIRED** |
| `promote_checker` | `(str) -> bool` | `len(content) > 200` |
| `depth_detector` | `(str) -> str` | Keyword matching |
| `duplicate_checker` | `(str, str) -> bool` | SequenceMatcher > 0.85 |
| `conflict_resolver` | `(str, str) -> str` | Keep newer text |

### Event Hooks

```python
brain.on("before_save",    lambda content, source: ...)
brain.on("after_save",     lambda content, source: ...)
brain.on("before_promote", lambda content: ...)
brain.on("after_promote",  lambda content, mem_id: ...)
brain.on("after_recall",   lambda query, depth, result: ...)
brain.on("after_cycle",    lambda stats: ...)
```

## Examples

| File | Description |
|---|---|
| [`basic_usage.py`](examples/basic_usage.py) | Simplest setup with OpenAI |
| [`with_openai.py`](examples/with_openai.py) | All 5 callbacks with OpenAI |
| [`with_anthropic.py`](examples/with_anthropic.py) | Claude API integration |
| [`with_langchain.py`](examples/with_langchain.py) | LangChain agent + memory |
| [`custom_callbacks.py`](examples/custom_callbacks.py) | Custom callbacks + hooks |
| [`scheduling.py`](examples/scheduling.py) | Polling, FastAPI, Celery |

## Compatibility

- **Python**: 3.9, 3.10, 3.11, 3.12, 3.13
- **OS**: Windows, macOS, Linux
- **Dependencies**: None (Python stdlib only)
- **SQLite**: Uses built-in `sqlite3` module (FTS5 optional, graceful fallback)

## Roadmap

| Version | Codename | Status |
|---|---|---|
| v0.1.0 | "Remembering AI" | Current |
| v0.2.0 | "Growing AI" | Planned -- tag trees + built-in AI (Gemma 4) |
| v0.3.0 | "Thinking AI" | Planned -- contradiction detection (CKN) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
