"""
with_anthropic.py -- Claude API integration with sandclaw-memory.

WHAT THIS EXAMPLE SHOWS:
    How to use Anthropic's Claude as the AI backend for sandclaw-memory.
    Claude excels at nuanced tag extraction -- it understands context
    better than simple keyword matching.

BEFORE YOU RUN THIS:
    1. pip install sandclaw-memory anthropic
    2. Set your ANTHROPIC_API_KEY environment variable

COST:
    Claude Haiku 4.5 is the cheapest option:
    ~$0.25/1M input, ~$1.25/1M output tokens.
    Tag extraction uses ~100-200 tokens = ~$0.00005 per call.
    Cost decreases over time as keyword_map grows!

WHY CLAUDE?
    - Excellent at understanding nuance and context
    - Haiku 4.5 is fast and cheap for tag extraction
    - Sonnet 4.6 for high-quality depth detection
    - Mix models across callbacks for cost optimization
"""

from __future__ import annotations

import json

import anthropic
from sandclaw_memory import BrainMemory

# ─── Create the Anthropic client ───
# The client reads ANTHROPIC_API_KEY from environment automatically.
client = anthropic.Anthropic()


# ═══════════════════════════════════════════════════════════
# Tag Extractor using Claude Haiku (fast + cheap)
# ═══════════════════════════════════════════════════════════
def tag_extractor(content: str) -> list[str]:
    """Extract tags using Claude Haiku 4.5.

    WHY HAIKU:
        Tag extraction is a simple task -- we don't need
        the most powerful model. Haiku is 10x cheaper
        than Sonnet and plenty good for this.
    """
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract 3-7 keyword tags from this text. "
                    "Return ONLY a JSON array of lowercase strings.\n\n"
                    f"Text: {content}"
                ),
            },
        ],
    )
    return json.loads(resp.content[0].text)


# ═══════════════════════════════════════════════════════════
# Depth Detector using Claude Haiku
# ═══════════════════════════════════════════════════════════
def depth_detector(query: str) -> str:
    """Detect search depth using Claude.

    Returns "casual", "standard", or "deep".
    """
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[
            {
                "role": "user",
                "content": (
                    "Classify this query's search depth.\n"
                    "casual = recent/simple, standard = this month/trends, "
                    "deep = old/historical/why questions.\n"
                    "Reply with ONLY: casual, standard, or deep\n\n"
                    f"Query: {query}"
                ),
            },
        ],
    )
    return resp.content[0].text.strip().lower()


# ═══════════════════════════════════════════════════════════
# Promote Checker using Claude Haiku
# ═══════════════════════════════════════════════════════════
def promote_checker(content: str) -> bool:
    """AI decides if content deserves permanent storage."""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[
            {
                "role": "user",
                "content": (
                    "Should this text be saved as a permanent memory? "
                    "YES if it contains decisions, preferences, or facts. "
                    "NO if it's small talk or ephemeral. "
                    "Reply ONLY YES or NO.\n\n"
                    f"Text: {content}"
                ),
            },
        ],
    )
    return resp.content[0].text.strip().upper() == "YES"


# ═══════════════════════════════════════════════════════════
# Summarize using Claude Sonnet (smarter model for summaries)
# ═══════════════════════════════════════════════════════════
def summarize_callback(prompt: str) -> str:
    """Generate a monthly summary using Claude Sonnet 4.6.

    WHY SONNET FOR SUMMARIES:
        Summaries run once per month (or manually), so the extra
        cost of a smarter model is negligible. Better summaries
        = better L2 context for STANDARD-depth recalls.
    """
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )
    return resp.content[0].text


# ═══════════════════════════════════════════════════════════
# Usage
# ═══════════════════════════════════════════════════════════
with BrainMemory(
    db_path="./claude_memory",
    tag_extractor=tag_extractor,        # Haiku (cheap)
    promote_checker=promote_checker,    # Haiku (cheap)
    depth_detector=depth_detector,      # Haiku (cheap)
    polling_interval=15,
) as brain:
    brain.start_polling()

    # ─── Save some content ───
    brain.save("User is building a SaaS product with Next.js and Supabase.")
    brain.save("The target market is small businesses in Japan.")
    brain.save(
        "Key decision: using Stripe for payments, not PayPal.",
        source="archive",
        tags=["payments", "stripe", "decision"],
    )

    # ─── Recall with auto depth detection ───
    context = brain.recall("what tech stack are we using?")
    print("=== Recalled Memory ===")
    print(context)

    # ─── Generate a summary (uses Sonnet for quality) ───
    summary = brain.summarize(llm_callback=summarize_callback)
    print("\n=== Monthly Summary ===")
    print(summary)

    # ─── Export for backup ───
    brain.export_json(path="./backup.json")
    print("\nBackup saved to ./backup.json")
