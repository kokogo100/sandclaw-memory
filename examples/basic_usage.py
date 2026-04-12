"""
basic_usage.py -- Simplest way to use sandclaw-memory.

WHAT THIS EXAMPLE SHOWS:
    How to get started with sandclaw-memory in under 30 lines.
    Uses OpenAI's gpt-4o-mini as the tag extractor (cheapest option).

BEFORE YOU RUN THIS:
    1. pip install sandclaw-memory openai
    2. Set your OPENAI_API_KEY environment variable

WHAT HAPPENS:
    1. BrainMemory initializes 3 memory layers (session, summary, archive)
    2. You save some content -> it goes to the right layer
    3. You recall -> it auto-detects depth and returns relevant memories
    4. The polling loop extracts tags in the background (self-growing!)

COST:
    gpt-4o-mini costs ~$0.15/1M input tokens.
    A typical tag extraction call uses ~100 tokens = $0.000015 per save.
    As the keyword_map grows, AI calls decrease over time!
"""

from __future__ import annotations

import json
import os

import openai
from sandclaw_memory import BrainMemory


# ─── Step 1: Define your tag extractor ───
# WHY: This is the ONLY required callback.
# It tells the library HOW to extract tags from text.
# You can use any AI model, any API, or even a local model.
def tag_extractor(content: str) -> list[str]:
    """Ask OpenAI to extract tags from the content."""
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract 3-7 keyword tags from the text below. "
                    "Return a JSON array of lowercase strings only. "
                    "Example: [\"python\", \"web\", \"react\"]"
                ),
            },
            {"role": "user", "content": content},
        ],
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


# ─── Step 2: Create BrainMemory ───
# The 'with' statement auto-cleans up (stops polling, closes DB).
# If you forget close(), resources leak. Always use 'with'.
with BrainMemory(
    db_path="./my_memory",          # Where to store files (created automatically)
    tag_extractor=tag_extractor,    # REQUIRED: the AI function above
    polling_interval=15,            # Background maintenance every 15 seconds
) as brain:

    # ─── Step 3: Start background polling ───
    # This runs a loop that:
    #   - Extracts tags from new memories (AI call)
    #   - Registers new keywords (self-growing!)
    #   - Cleans up old session logs
    brain.start_polling()

    # ─── Step 4: Save some memories ───

    # Regular conversation -> goes to L1 (session log, 3-day rolling)
    brain.save("User: What's the weather?\nAI: It's sunny, 25 degrees in Seoul.")

    # Important content -> goes to L1 AND L3 (permanent archive)
    brain.save(
        "User primarily uses Python and React for web development.",
        source="archive",
        tags=["python", "react", "preference"],  # Optional: provide tags yourself
    )

    # Auto-promote: if content is long enough, it auto-saves to L3
    brain.save(
        "After extensive discussion, the user decided to migrate the backend "
        "from Express.js to FastAPI for better type safety and performance. "
        "The frontend will remain React with TypeScript. The migration should "
        "be completed by end of Q2. This is a critical architectural decision "
        "that affects the entire team."
    )
    # ^ This is > 200 chars, so the default promote_checker saves it to L3 too!

    # ─── Step 5: Recall memories ───

    # The dispatcher auto-detects depth from the query:
    #   "what does the user like?" -> CASUAL (simple question)
    #   "summarize this month"     -> STANDARD (summary needed)
    #   "what happened 3 months ago?" -> DEEP (long-term search)
    context = brain.recall("what programming languages does the user prefer?")
    print("=== Recalled Memory ===")
    print(context)

    # Or force a specific depth:
    deep_context = brain.recall("preferences", depth="deep")
    print("\n=== Deep Search ===")
    print(deep_context)

    # ─── Step 6: Inject into your LLM ───

    user_message = "Can you recommend a project stack for me?"
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Use the following memory context to personalize your response:\n\n"
                    f"{context}"
                ),
            },
            {"role": "user", "content": user_message},
        ],
    )
    print("\n=== AI Response (with memory) ===")
    print(response.choices[0].message.content)

    # ─── Step 7: Check stats ───
    stats = brain.get_stats()
    print(f"\n=== Memory Stats ===")
    print(f"L3 memories: {stats['archive']['total_memories']}")
    print(f"Polling active: {stats['is_polling']}")

# When the 'with' block ends:
#   - Polling stops automatically
#   - Database connections close
#   - No resource leaks!
