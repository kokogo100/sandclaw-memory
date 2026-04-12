# API Reference

## BrainMemory

The main class. Connects all three memory layers into one simple API.

### Constructor

```python
BrainMemory(
    db_path: str = "./memory",
    rolling_days: int = 3,
    summary_days: int = 30,
    max_context_chars: int = 15_000,
    content_truncate: int = 450,
    summary_truncate: int = 2500,
    tag_extractor: Callable[[str], list[str]] = None,  # REQUIRED
    promote_checker: Callable[[str], bool] = None,
    depth_detector: Callable[[str], str] = None,
    duplicate_checker: Callable[[str, str], bool] = None,
    conflict_resolver: Callable[[str, str], str] = None,
    polling_interval: int = 15,
    encryption_key: str = None,
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `db_path` | `str` | `"./memory"` | Base directory for all memory files |
| `rolling_days` | `int` | `3` | L1 session log retention in days |
| `summary_days` | `int` | `30` | L2 summary period in days |
| `max_context_chars` | `int` | `15000` | Context budget for LLM injection |
| `content_truncate` | `int` | `450` | Max chars per memory in render output |
| `summary_truncate` | `int` | `2500` | Max chars for summary in render output |
| `tag_extractor` | `Callable` | **REQUIRED** | `(str) -> list[str]` - extract tags from text |
| `promote_checker` | `Callable` | `len > 200` | `(str) -> bool` - decide if content should be promoted to L3 |
| `depth_detector` | `Callable` | keywords | `(str) -> str` - detect search depth ("casual"/"standard"/"deep") |
| `duplicate_checker` | `Callable` | similarity 0.85 | `(str, str) -> bool` - detect duplicate memories |
| `conflict_resolver` | `Callable` | keep newer | `(str, str) -> str` - resolve conflicting memories |
| `polling_interval` | `int` | `15` | Seconds between background maintenance cycles |
| `encryption_key` | `str` | `None` | SQLCipher encryption key for L3 database |

**Raises**: `ConfigurationError` if `tag_extractor` is `None`.

---

### save()

```python
brain.save(
    content: str,
    source: str = "chat",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> None
```

Save content to memory.

- `source="chat"` (default): saves to L1 only
- `source="archive"`: saves to L1 AND L3
- Any other source: saves to L1 only, but `promote_checker` may promote to L3

**Parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `content` | `str` | required | The text to save |
| `source` | `str` | `"chat"` | Source identifier |
| `tags` | `list[str]` | `None` | Pre-defined tags (for L3) |
| `metadata` | `dict` | `None` | Extra key-value data |

---

### recall()

```python
brain.recall(
    query: str = "",
    depth: str | None = None,
) -> str
```

Recall relevant memories. Returns Markdown ready for LLM injection.

**Parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | `""` | Search text or user question |
| `depth` | `str` | `None` | Manual override: "casual", "standard", or "deep". Auto-detected if None. |

**Returns**: `str` - Markdown with relevant memories.

---

### search()

```python
brain.search(query: str, limit: int = 20) -> list[MemoryEntry]
```

Search L3 archive. Returns structured results (not Markdown).

**Returns**: `list[MemoryEntry]` - each entry has `.content`, `.tags`, `.created_at`, etc.

---

### promote()

```python
brain.promote(content: str, tags: list[str] | None = None) -> int
```

Manually save content to L3 permanent storage.

**Returns**: `int` - memory ID in L3 (`-1` if duplicate detected).

---

### summarize()

```python
brain.summarize(llm_callback: Callable[[str], str] | None = None) -> str
```

Generate a period summary.

| Parameter | Type | Description |
|---|---|---|
| `llm_callback` | `Callable` | AI function to generate summary. Receives a prompt string, returns summary text. |

If `llm_callback` is None or fails, uses a simple text fallback.

---

### start_polling() / stop_polling()

```python
brain.start_polling() -> None
brain.stop_polling() -> None
```

Start/stop the background maintenance loop. The loop:
1. Processes the tag extraction queue
2. Cleans up old L1 logs
3. Fires the `after_cycle` hook

---

### run_maintenance()

```python
brain.run_maintenance(older_than_days: int | None = None) -> dict
```

Run one maintenance cycle manually (no polling needed).

**Returns**: `{"tags_processed": int, "cleaned": int}`

---

### process_tag_queue()

```python
brain.process_tag_queue() -> int
```

Process only the tag extraction queue.

**Returns**: Number of items processed.

---

### get_stats()

```python
brain.get_stats() -> dict
```

**Returns**:
```python
{
    "session": {...},      # L1 stats
    "archive": {           # L3 stats
        "total_memories": int,
        "total_tags": int,
        "keyword_map_size": int,
        "pending_tag_extractions": int,
    },
    "is_polling": bool,
    "polling_interval": int,
}
```

---

### get_tag_stats()

```python
brain.get_tag_stats() -> dict[str, int]
```

**Returns**: `{"python": 15, "react": 8, ...}` - tag usage counts.

---

### on()

```python
brain.on(event: str, callback: Callable) -> None
```

Register an event hook.

| Event | Arguments | When |
|---|---|---|
| `before_save` | `(content, source)` | Before any save |
| `after_save` | `(content, source)` | After save completes |
| `before_promote` | `(content,)` | Before L3 promotion |
| `after_promote` | `(content, memory_id)` | After L3 promotion |
| `after_recall` | `(query, depth, result)` | After recall completes |
| `after_cycle` | `(stats_dict,)` | After each polling cycle |

Hook exceptions are silently caught (they won't crash your app).

---

### export_json()

```python
brain.export_json(path: str | None = None) -> dict
```

Export all data as JSON. If `path` is given, also writes to file.

---

### close()

```python
brain.close() -> None
```

Stop polling and close the database. Called automatically by `with` statement.

---

## Types

### Depth

```python
from sandclaw_memory import Depth

Depth.CASUAL    # "casual" - L1 only
Depth.STANDARD  # "standard" - L1 + L2
Depth.DEEP      # "deep" - L1 + L2 + L3
```

### MemoryEntry

```python
from sandclaw_memory import MemoryEntry

entry.id          # int
entry.content     # str
entry.content_type # str
entry.tags        # list[str]
entry.source      # str
entry.metadata    # dict
entry.created_at  # str (ISO 8601)
entry.updated_at  # str (ISO 8601)
```

### Exceptions

```python
from sandclaw_memory import SandclawError
from sandclaw_memory.exceptions import (
    ConfigurationError,   # Bad config (e.g. missing tag_extractor)
    StorageError,         # Database errors
    CallbackError,        # Callback function failures
    TagExtractionError,   # Tag extractor failures (subclass of CallbackError)
)
```

All exceptions inherit from `SandclawError`. Catch it to handle all library errors:

```python
try:
    brain.save("content")
except SandclawError as e:
    print(f"sandclaw-memory error: {e}")
```
