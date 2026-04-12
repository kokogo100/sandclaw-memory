"""
scheduling.py -- Polling configurations + web framework integration.

WHAT THIS EXAMPLE SHOWS:
    Three patterns for running sandclaw-memory's maintenance loop:
    1. Built-in polling (simplest, good for most apps)
    2. Manual maintenance (for scripts and notebooks)
    3. FastAPI lifespan integration (production web apps)

WHEN TO USE WHICH:
    - CLI app / chatbot   -> Pattern 1 (built-in polling)
    - Jupyter notebook     -> Pattern 2 (manual)
    - FastAPI / Flask      -> Pattern 3 (lifespan)
    - Celery / task queue  -> Pattern 4 (manual + Celery beat)

WHY POLLING MATTERS:
    The tag extraction queue needs to be processed regularly.
    When you call brain.save(), tags aren't extracted immediately
    (that would block the main thread with AI calls).
    Instead, they're queued and processed in the background.
"""

from __future__ import annotations

import json

from sandclaw_memory import BrainMemory


# ─── Shared tag extractor (replace with your AI call) ───
def tag_extractor(content: str) -> list[str]:
    words = content.lower().split()
    return [w.strip(".,!?") for w in words if len(w) > 3][:5]


# ═══════════════════════════════════════════════════════════
# Pattern 1: Built-in Polling (simplest)
# ═══════════════════════════════════════════════════════════
def pattern_built_in_polling() -> None:
    """Use the built-in threading.Timer loop.

    GOOD FOR:
        - CLI apps, chatbots, desktop apps
        - Single-process applications
        - When you don't have a task queue

    HOW IT WORKS:
        start_polling() starts a daemon thread that runs every N seconds.
        It processes the tag queue, cleans up old logs, and fires hooks.
        The thread dies automatically when the main process exits.
    """
    with BrainMemory(
        db_path="./memory_polling",
        tag_extractor=tag_extractor,
        polling_interval=15,    # Every 15 seconds (default)
    ) as brain:
        brain.start_polling()

        # Your app runs here...
        brain.save("Example content")

        # Stats show the polling state
        print(f"Polling active: {brain.is_polling}")
        print(f"Interval: {brain.get_stats()['polling_interval']}s")

    # 'with' block ends -> polling stops, DB closes


def pattern_fast_polling() -> None:
    """Fast polling for real-time applications.

    GOOD FOR:
        - Real-time chat apps where tags are needed quickly
        - Development/testing
    """
    with BrainMemory(
        db_path="./memory_fast",
        tag_extractor=tag_extractor,
        polling_interval=5,     # Every 5 seconds (fast!)
    ) as brain:
        brain.start_polling()
        brain.save("Fast processing needed", source="archive")
        # Tags extracted within 5 seconds


def pattern_slow_polling() -> None:
    """Slow polling for batch processing.

    GOOD FOR:
        - Background services with low urgency
        - Saving API costs (fewer AI calls)
        - High-volume applications
    """
    with BrainMemory(
        db_path="./memory_slow",
        tag_extractor=tag_extractor,
        polling_interval=300,   # Every 5 minutes
    ) as brain:
        brain.start_polling()
        brain.save("Batch processing mode", source="archive")
        # Tags extracted within 5 minutes


# ═══════════════════════════════════════════════════════════
# Pattern 2: Manual Maintenance (no polling)
# ═══════════════════════════════════════════════════════════
def pattern_manual() -> None:
    """Call run_maintenance() when YOU decide.

    GOOD FOR:
        - Jupyter notebooks
        - One-shot scripts
        - When you want full control over timing
        - When you don't want background threads
    """
    brain = BrainMemory(
        db_path="./memory_manual",
        tag_extractor=tag_extractor,
        # No need to set polling_interval -- we won't use it
    )

    # Save some content
    brain.save("Python is great for data science", source="archive")
    brain.save("React for building UIs", source="archive")

    # Nothing has been tagged yet! Tags are in the queue.
    stats = brain.get_stats()
    print(f"Pending tags: {stats['archive']['pending_tag_extractions']}")

    # NOW process the queue manually:
    result = brain.run_maintenance()
    print(f"Tags processed: {result['tags_processed']}")
    print(f"Logs cleaned: {result['cleaned']}")

    # Or process ONLY the tag queue:
    processed = brain.process_tag_queue()
    print(f"Additional tags processed: {processed}")

    brain.close()


# ═══════════════════════════════════════════════════════════
# Pattern 3: FastAPI Lifespan Integration
# ═══════════════════════════════════════════════════════════
def pattern_fastapi() -> None:
    """FastAPI app with sandclaw-memory.

    GOOD FOR:
        - Production web APIs
        - Long-running servers
        - Multi-user applications

    HOW IT WORKS:
        FastAPI's lifespan context manager starts polling on startup
        and stops it on shutdown. Clean and production-ready.

    BEFORE YOU RUN THIS:
        pip install sandclaw-memory fastapi uvicorn
    """
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    # ─── Initialize memory outside the lifespan ───
    brain = BrainMemory(
        db_path="./memory_fastapi",
        tag_extractor=tag_extractor,
        polling_interval=30,    # 30s is good for web apps
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Start polling on startup, stop on shutdown."""
        brain.start_polling()
        yield
        brain.close()  # stops polling + closes DB

    app = FastAPI(lifespan=lifespan)

    @app.post("/chat")
    async def chat(message: str):
        # 1. Recall relevant context
        context = brain.recall(message)

        # 2. Save the user message
        brain.save(f"User: {message}")

        # 3. Return context (your app would call an LLM here)
        return {"context": context, "message": message}

    @app.post("/save")
    async def save_memory(content: str, tags: list[str] | None = None):
        brain.save(content, source="archive", tags=tags)
        return {"status": "saved"}

    @app.get("/stats")
    async def get_stats():
        return brain.get_stats()

    # Run with: uvicorn scheduling:app --reload
    print("FastAPI app created. Run with: uvicorn scheduling:app --reload")
    return app


# ═══════════════════════════════════════════════════════════
# Pattern 4: Celery Beat (distributed task queue)
# ═══════════════════════════════════════════════════════════
def pattern_celery() -> None:
    """Celery periodic task for maintenance.

    GOOD FOR:
        - Distributed systems
        - Multiple workers
        - When you already use Celery

    NOTE:
        Don't use start_polling() with Celery --
        each worker would start its own polling loop!
        Instead, use Celery Beat for a single maintenance task.

    SETUP (celeryconfig.py):
        beat_schedule = {
            'memory-maintenance': {
                'task': 'tasks.run_memory_maintenance',
                'schedule': 30.0,  # every 30 seconds
            },
        }

    BEFORE YOU RUN THIS:
        pip install sandclaw-memory celery
    """
    print(
        "Celery pattern: use a periodic task instead of start_polling().\n"
        "See the code comments for the Celery Beat configuration."
    )
    # Example Celery task (would go in tasks.py):
    #
    # from celery import Celery
    # app = Celery('tasks')
    #
    # brain = BrainMemory(
    #     db_path="./memory_celery",
    #     tag_extractor=tag_extractor,
    # )
    #
    # @app.task
    # def run_memory_maintenance():
    #     result = brain.run_maintenance()
    #     return result


# ═══════════════════════════════════════════════════════════
# Run demos
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== Pattern 1: Built-in Polling ===")
    pattern_built_in_polling()

    print("\n=== Pattern 2: Manual Maintenance ===")
    pattern_manual()

    print("\n=== Pattern 3: FastAPI (info only) ===")
    pattern_fastapi()

    print("\n=== Pattern 4: Celery (info only) ===")
    pattern_celery()
