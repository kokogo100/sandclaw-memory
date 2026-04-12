# ═══════════════════════════════════════════════════════════
# loader.py -- TieredLoader (Layer Orchestration + Budget)
#
# WHAT THIS MODULE DOES:
#   Loads memories from the right layers based on search depth,
#   and enforces a character budget so you don't overflow the
#   LLM's context window.
#
# ANALOGY:
#   You have a 15KB backpack. The loader decides what to pack:
#     CASUAL:   just your phone (L1)            -> fits easily
#     STANDARD: phone + notebook (L1 + L2)      -> still fits
#     DEEP:     phone + notebook + laptop (L1+L2+L3) -> careful packing
#
# BUDGET SYSTEM:
#   Default budget: 15,000 characters (~3,750 tokens)
#   Each layer gets a share:
#     L1: 40% (most recent, most relevant)
#     L2: 30% (summary, compressed info)
#     L3: 30% (archive search results)
#
# HOW TO CUSTOMIZE:
#   loader = TieredLoader(max_context_chars=30_000)  # bigger budget
#
# DEPENDS ON:
#   types.py (Depth)
#   utils.py (truncate)
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from typing import Any

from sandclaw_memory.types import Depth
from sandclaw_memory.utils import truncate

__all__ = ["TieredLoader"]

logger = logging.getLogger(__name__)


class TieredLoader:
    """Loads memory context from appropriate layers within a budget.

    Usage:
        loader = TieredLoader(max_context_chars=15_000)
        context = loader.load(
            depth=Depth.STANDARD,
            query="what happened last week?",
            session=my_session,
            summary=my_summary,
            archive=my_archive,
        )
        # -> Markdown string within 15KB budget
    """

    def __init__(self, max_context_chars: int = 15_000) -> None:
        """Initialize the loader.

        Args:
            max_context_chars: Maximum characters in the assembled context.
                Default 15,000 (~3,750 tokens). Adjust based on your
                LLM's context window.

        HOW TO CUSTOMIZE:
            # For GPT-4 with 128K context, you can use more:
            loader = TieredLoader(max_context_chars=50_000)

            # For smaller models, use less:
            loader = TieredLoader(max_context_chars=5_000)
        """
        self.max_context_chars = max_context_chars

    def load(
        self,
        depth: Depth,
        query: str = "",
        session: Any = None,
        summary: Any = None,
        archive: Any = None,
    ) -> str:
        """Load memory context from the appropriate layers.

        Args:
            depth: How deep to search (CASUAL, STANDARD, DEEP).
            query: The user's query (used for L3 archive search).
            session: SessionMemory instance (L1).
            summary: SummaryMemory instance (L2).
            archive: ArchiveMemory instance (L3).

        Returns:
            Assembled Markdown string within the character budget.

        HOW IT WORKS:
            CASUAL:   loads L1 only (40% of budget)
            STANDARD: loads L1 (40%) + L2 (30%)
            DEEP:     loads L1 (40%) + L2 (30%) + L3 (30%)
        """
        parts: list[str] = []
        budget = self.max_context_chars

        # ─── Budget allocation ───
        # WHY THESE PERCENTAGES?
        # L1 gets the most because recent context is usually most relevant.
        # L2 and L3 share the rest. You can adjust these by subclassing.
        l1_budget = int(budget * 0.4)
        l2_budget = int(budget * 0.3)
        l3_budget = int(budget * 0.3)

        # ─── L1: Session (always loaded) ───
        if session is not None:
            l1_context = session.get_context()
            if l1_context:
                parts.append(truncate(l1_context, l1_budget))

        # ─── L2: Summary (STANDARD and DEEP) ───
        if depth in (Depth.STANDARD, Depth.DEEP) and summary is not None:
            l2_context = summary.get_summary()
            if l2_context:
                parts.append("\n## 30-Day Summary")
                parts.append(truncate(l2_context, l2_budget))

        # ─── L3: Archive (DEEP only) ───
        if depth == Depth.DEEP and archive is not None and query:
            entries = archive.search(query, limit=10)
            if entries:
                parts.append("\n## Archive (Permanent Memories)")
                archive_text: list[str] = []
                for entry in entries:
                    tags_str = ", ".join(entry.tags) if entry.tags else ""
                    line = f"- [{tags_str}] {entry.content[:200]}"
                    archive_text.append(line)
                parts.append(truncate("\n".join(archive_text), l3_budget))

        result = "\n".join(parts)
        logger.debug(
            "Loaded %s context: %d chars (budget: %d)",
            depth.value, len(result), budget,
        )
        return result
