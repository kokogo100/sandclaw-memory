"""
with_openai.py -- Advanced OpenAI integration with all 5 callbacks.

WHAT THIS EXAMPLE SHOWS:
    How to use ALL 5 AI callbacks (not just tag_extractor).
    This gives OpenAI full control over:
    1. Tag extraction (what keywords describe this text?)
    2. Promotion (should this go to permanent storage?)
    3. Depth detection (how deep should we search?)
    4. Duplicate detection (is this the same as an existing memory?)
    5. Conflict resolution (which version is correct?)

WHY ALL 5?
    In basic_usage.py, we only set tag_extractor (the minimum).
    The other 4 callbacks use simple defaults (string length, keywords, etc.)
    But AI-powered callbacks are MUCH smarter:
    - promote_checker: AI decides importance (not just string length)
    - depth_detector: AI understands context (not just keyword matching)
    - duplicate_checker: AI catches semantic duplicates ("I love Python" ≈ "Python is my favorite")
    - conflict_resolver: AI picks the latest truth when facts contradict

COST ESTIMATE:
    5 callbacks = more AI calls. With gpt-4o-mini:
    - tag_extractor: ~100 tokens per save
    - promote_checker: ~80 tokens per save
    - depth_detector: ~60 tokens per recall
    - duplicate_checker: ~120 tokens per save (only when similar found)
    - conflict_resolver: ~150 tokens per conflict (rare)
    Total: ~$0.0001 per save cycle. Very cheap for powerful memory.

BEFORE YOU RUN THIS:
    1. pip install sandclaw-memory openai
    2. Set your OPENAI_API_KEY environment variable
"""

from __future__ import annotations

import json

import openai
from sandclaw_memory import BrainMemory


# ═══════════════════════════════════════════════════════════
# Callback 1: Tag Extractor (REQUIRED)
# ═══════════════════════════════════════════════════════════
def tag_extractor(content: str) -> list[str]:
    """Extract 3-7 keyword tags from content.

    WHY THIS IS REQUIRED:
        Tags are the backbone of self-growing memory.
        Without them, the keyword_map can't grow,
        and search can't find relevant memories.
    """
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract 3-7 keyword tags from the text. "
                    "Focus on: technologies, concepts, decisions, people, emotions. "
                    "Return a JSON array of lowercase strings. "
                    'Example: ["python", "architecture", "decision"]'
                ),
            },
            {"role": "user", "content": content},
        ],
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


# ═══════════════════════════════════════════════════════════
# Callback 2: Promote Checker (optional)
# ═══════════════════════════════════════════════════════════
def promote_checker(content: str) -> bool:
    """AI decides if content is important enough for permanent storage.

    DEFAULT BEHAVIOR (without this callback):
        len(content) > 200 → promote.
        This is dumb -- a 201-char joke gets saved, but a 50-char
        critical decision ("We're switching to Rust") doesn't.

    WITH THIS CALLBACK:
        AI evaluates actual importance.
    """
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Decide if this text should be saved as a permanent memory. "
                    "Answer YES if it contains: decisions, preferences, facts, "
                    "technical choices, or important context. "
                    "Answer NO if it's small talk, greetings, or ephemeral. "
                    "Reply with ONLY 'YES' or 'NO'."
                ),
            },
            {"role": "user", "content": content},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip().upper() == "YES"


# ═══════════════════════════════════════════════════════════
# Callback 3: Depth Detector (optional)
# ═══════════════════════════════════════════════════════════
def depth_detector(query: str) -> str:
    """AI decides how deep to search for a given query.

    DEFAULT BEHAVIOR (without this callback):
        Keyword matching -- "months ago" → DEEP, "today" → CASUAL.
        Misses nuance like "why did we choose React?" (needs DEEP
        even though there's no time keyword).

    WITH THIS CALLBACK:
        AI understands intent, not just keywords.

    MUST RETURN: "casual", "standard", or "deep"
    """
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify this query's search depth:\n"
                    '- "casual": recent/simple questions (today, what time)\n'
                    '- "standard": this month, summaries, trends\n'
                    '- "deep": old memories, decisions, history, "why"\n'
                    "Reply with ONLY one word: casual, standard, or deep"
                ),
            },
            {"role": "user", "content": query},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip().lower()


# ═══════════════════════════════════════════════════════════
# Callback 4: Duplicate Checker (optional)
# ═══════════════════════════════════════════════════════════
def duplicate_checker(new_text: str, existing_text: str) -> bool:
    """AI detects if two texts are semantically the same.

    DEFAULT BEHAVIOR (without this callback):
        difflib.SequenceMatcher > 0.85 similarity.
        Misses: "I love Python" ≈ "Python is my favorite language"
        (different words, same meaning → similarity < 0.85)

    WITH THIS CALLBACK:
        AI catches semantic duplicates.
    """
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Are these two texts saying the same thing? "
                    "Reply ONLY 'YES' or 'NO'.\n\n"
                    f"Text A: {new_text}\n"
                    f"Text B: {existing_text}"
                ),
            },
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip().upper() == "YES"


# ═══════════════════════════════════════════════════════════
# Callback 5: Conflict Resolver (optional)
# ═══════════════════════════════════════════════════════════
def conflict_resolver(old_text: str, new_text: str) -> str:
    """AI resolves conflicting information.

    DEFAULT BEHAVIOR (without this callback):
        Keeps the newer text (last-write-wins).

    WITH THIS CALLBACK:
        AI merges information intelligently.

    Example:
        old: "User likes Python 3.9"
        new: "User upgraded to Python 3.13"
        result: "User uses Python (upgraded from 3.9 to 3.13)"
    """
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Two memories contain conflicting information. "
                    "Merge them into one accurate statement. "
                    "Keep all important details. Reply with ONLY the merged text.\n\n"
                    f"Older memory: {old_text}\n"
                    f"Newer memory: {new_text}"
                ),
            },
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


# ═══════════════════════════════════════════════════════════
# Usage
# ═══════════════════════════════════════════════════════════
with BrainMemory(
    db_path="./smart_memory",
    tag_extractor=tag_extractor,            # REQUIRED
    promote_checker=promote_checker,        # AI-powered importance detection
    depth_detector=depth_detector,          # AI-powered depth classification
    duplicate_checker=duplicate_checker,    # AI-powered dedup
    conflict_resolver=conflict_resolver,    # AI-powered conflict merge
    polling_interval=30,                    # 30s between maintenance cycles
) as brain:
    brain.start_polling()

    # ─── Save various types of content ───
    # promote_checker decides what's important (not string length!)
    brain.save("We decided to use PostgreSQL for the main database.")
    # ^ AI says YES → saved to L3 even though it's short

    brain.save("Hi! How are you doing today?")
    # ^ AI says NO → stays in L1 only (ephemeral)

    brain.save("User prefers dark mode in all applications.")
    # ^ AI says YES → saved to L3

    # ─── Recall with AI depth detection ───
    context = brain.recall("why did we choose PostgreSQL?")
    # ^ depth_detector returns "deep" (it's a "why" question about a past decision)
    print(context)

    # ─── Check what's been stored ───
    stats = brain.get_stats()
    print(f"\nTotal permanent memories: {stats['archive']['total_memories']}")
    tag_stats = brain.get_tag_stats()
    print(f"Tags learned: {tag_stats}")
