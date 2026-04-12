"""
custom_callbacks.py -- Customize all 5 AI callbacks + event hooks.

WHAT THIS EXAMPLE SHOWS:
    sandclaw-memory has 5 AI callbacks and 6 event hooks.
    This example shows how to customize ALL of them.

THE 5 AI CALLBACKS:
    1. tag_extractor    (REQUIRED) -> extract tags from text
    2. promote_checker  (optional) -> decide if content is important
    3. depth_detector   (optional) -> detect search depth from query
    4. duplicate_checker(optional) -> detect semantic duplicates
    5. conflict_resolver(optional) -> merge conflicting memories

THE 6 EVENT HOOKS:
    1. before_save     -> runs before any save
    2. after_save      -> runs after save completes
    3. before_promote  -> runs before L3 promotion
    4. after_promote   -> runs after L3 promotion
    5. after_recall    -> runs after recall
    6. after_cycle     -> runs after each polling cycle

WHY CUSTOMIZE?
    The defaults are good for getting started:
    - promote_checker: len(content) > 200 chars
    - depth_detector: keyword matching ("months ago" -> DEEP)
    - duplicate_checker: SequenceMatcher > 0.85 similarity
    - conflict_resolver: keep newer text

    But AI-powered callbacks are smarter, and hooks let you
    add logging, analytics, or integrations.

NOTE:
    This example uses simple functions (no AI calls) to show
    the callback signatures. In production, replace them with
    actual AI calls (see with_openai.py or with_anthropic.py).
"""

from __future__ import annotations

from sandclaw_memory import BrainMemory


# ═══════════════════════════════════════════════════════════
# Callback 1: Tag Extractor (REQUIRED)
# ═══════════════════════════════════════════════════════════
# SIGNATURE: (content: str) -> list[str]
# CALLED WHEN: A new memory is saved to L3 (permanent archive)
# MUST RETURN: A list of lowercase string tags
#
# HOW TO CUSTOMIZE:
#   - Use any AI model (OpenAI, Claude, Gemini, local LLM)
#   - Or use simple NLP (spaCy, NLTK, regex)
#   - Or call an external API
#   - Just return list[str]!
def my_tag_extractor(content: str) -> list[str]:
    """Simple keyword-based tag extractor (no AI needed).

    Replace this with an AI call for production use.
    This is a demo showing the simplest possible implementation.
    """
    # Simple approach: split into words, filter by length
    words = content.lower().split()
    tags = []
    for word in words:
        # Strip punctuation
        clean = word.strip(".,!?;:'\"()[]{}#@")
        if len(clean) > 3 and clean not in ("this", "that", "with", "from", "have"):
            tags.append(clean)
    return tags[:7]  # Max 7 tags


# ═══════════════════════════════════════════════════════════
# Callback 2: Promote Checker (optional)
# ═══════════════════════════════════════════════════════════
# SIGNATURE: (content: str) -> bool
# CALLED WHEN: Content is saved via brain.save() (not source="archive")
# MUST RETURN: True to promote to L3, False to keep in L1 only
#
# DEFAULT: len(content) > 200
#
# HOW TO CUSTOMIZE:
#   - Check for keywords: "decided", "important", "preference"
#   - Use AI to evaluate importance
#   - Check content type (code snippets, decisions, etc.)
def my_promote_checker(content: str) -> bool:
    """Promote content that contains decision keywords."""
    decision_words = {
        "decided", "decision", "chose", "prefer", "important",
        "critical", "must", "always", "never", "rule",
    }
    words = set(content.lower().split())
    return bool(words & decision_words)


# ═══════════════════════════════════════════════════════════
# Callback 3: Depth Detector (optional)
# ═══════════════════════════════════════════════════════════
# SIGNATURE: (query: str) -> str
# CALLED WHEN: brain.recall() without explicit depth
# MUST RETURN: "casual", "standard", or "deep"
#
# DEFAULT: keyword matching (built-in English/Korean/Japanese)
#
# HOW TO CUSTOMIZE:
#   - Add your own keyword sets
#   - Use AI for nuanced detection
#   - Return based on conversation context
def my_depth_detector(query: str) -> str:
    """Depth detection with custom keyword sets."""
    q = query.lower()

    # Deep: historical or "why" questions
    if any(kw in q for kw in ["why", "history", "ago", "past", "origin"]):
        return "deep"

    # Standard: summary or trend questions
    if any(kw in q for kw in ["summary", "overview", "trend", "week", "month"]):
        return "standard"

    # Default: casual
    return "casual"


# ═══════════════════════════════════════════════════════════
# Callback 4: Duplicate Checker (optional)
# ═══════════════════════════════════════════════════════════
# SIGNATURE: (new_text: str, existing_text: str) -> bool
# CALLED WHEN: A new memory is being saved to L3, and an existing
#              memory with similar content is found
# MUST RETURN: True if they're duplicates, False if different
#
# DEFAULT: SequenceMatcher ratio > 0.85
#
# HOW TO CUSTOMIZE:
#   - Use AI for semantic comparison
#   - Use embeddings + cosine similarity
#   - Adjust the threshold
def my_duplicate_checker(new_text: str, existing_text: str) -> bool:
    """Check duplicates by normalized word overlap."""
    new_words = set(new_text.lower().split())
    old_words = set(existing_text.lower().split())

    if not new_words or not old_words:
        return False

    # Jaccard similarity
    overlap = len(new_words & old_words)
    union = len(new_words | old_words)
    return (overlap / union) > 0.7


# ═══════════════════════════════════════════════════════════
# Callback 5: Conflict Resolver (optional)
# ═══════════════════════════════════════════════════════════
# SIGNATURE: (old_text: str, new_text: str) -> str
# CALLED WHEN: duplicate_checker returns True (duplicate found)
#              and the system needs to decide which to keep
# MUST RETURN: The resolved text (merged, or one of the two)
#
# DEFAULT: keeps the newer text
#
# HOW TO CUSTOMIZE:
#   - Use AI to intelligently merge
#   - Append timestamps
#   - Keep both with a separator
def my_conflict_resolver(old_text: str, new_text: str) -> str:
    """Merge old and new information."""
    return f"{new_text} (updated from: {old_text})"


# ═══════════════════════════════════════════════════════════
# Usage with all callbacks
# ═══════════════════════════════════════════════════════════
with BrainMemory(
    db_path="./custom_memory",
    tag_extractor=my_tag_extractor,
    promote_checker=my_promote_checker,
    depth_detector=my_depth_detector,
    duplicate_checker=my_duplicate_checker,
    conflict_resolver=my_conflict_resolver,
    polling_interval=10,
) as brain:

    # ═══════════════════════════════════════════════════════════
    # Event Hooks
    # ═══════════════════════════════════════════════════════════
    # Hooks let you add side effects without modifying the library.
    # They're called with specific arguments (shown below).
    # If a hook throws an exception, it's silently caught
    # (your app won't crash from a logging error).

    # Hook 1: before_save(content, source)
    brain.on("before_save", lambda content, source: print(
        f"[HOOK] Saving: {content[:50]}... (source={source})"
    ))

    # Hook 2: after_save(content, source)
    brain.on("after_save", lambda content, source: print(
        f"[HOOK] Saved successfully (source={source})"
    ))

    # Hook 3: before_promote(content)
    brain.on("before_promote", lambda content: print(
        f"[HOOK] Promoting to L3: {content[:50]}..."
    ))

    # Hook 4: after_promote(content, memory_id)
    brain.on("after_promote", lambda content, mem_id: print(
        f"[HOOK] Promoted! Memory ID = {mem_id}"
    ))

    # Hook 5: after_recall(query, depth, result)
    brain.on("after_recall", lambda query, depth, result: print(
        f"[HOOK] Recalled (depth={depth}): {len(result)} chars"
    ))

    # Hook 6: after_cycle(stats_dict)
    brain.on("after_cycle", lambda stats: print(
        f"[HOOK] Maintenance cycle: {stats}"
    ))

    # ─── Demo ───
    print("=== Custom Callbacks Demo ===\n")

    # This triggers promote_checker (contains "decided")
    brain.save("We decided to use TypeScript for the frontend.")
    print()

    # This does NOT trigger promotion (no decision keywords)
    brain.save("The weather is nice today.")
    print()

    # Recall with custom depth detection
    context = brain.recall("why did we choose TypeScript?")
    print(f"\nRecalled:\n{context}")

    # Check stats
    stats = brain.get_stats()
    print(f"\nL3 memories: {stats['archive']['total_memories']}")
    print(f"Tags: {brain.get_tag_stats()}")
