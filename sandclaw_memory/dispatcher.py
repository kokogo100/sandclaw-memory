# ═══════════════════════════════════════════════════════════
# dispatcher.py -- IntentDispatcher (Depth Detection)
#
# WHAT THIS MODULE DOES:
#   Looks at a user's question and figures out HOW DEEP
#   to search the memory. This saves tokens and time by
#   only loading what's needed.
#
# ANALOGY:
#   "What's for lunch?" -> just check the fridge (L1 only)
#   "What did we discuss last week?" -> check fridge + notes (L1+L2)
#   "What rule did I set 3 months ago?" -> check everything (L1+L2+L3)
#
# HOW IT WORKS:
#   1. If the developer provided a depth_detector callback, use it
#   2. Otherwise, use keyword matching (fast, no AI call)
#
# HOW TO CUSTOMIZE:
#   # Use AI for depth detection:
#   def my_depth_detector(query):
#       # call your AI here
#       return "deep"  # or "casual" or "standard"
#
#   dispatcher = IntentDispatcher(depth_detector=my_depth_detector)
#
# DEPENDS ON:
#   types.py (Depth enum)
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from collections.abc import Callable

from sandclaw_memory.types import Depth

__all__ = ["IntentDispatcher"]

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Keyword Sets for Rule-Based Detection
# ═══════════════════════════════════════════════════════════

# ─── HOW TO CUSTOMIZE ───
# These keyword lists determine which depth is selected.
# Add your own domain-specific keywords to make detection smarter.
#
# For example, a medical AI might add:
#   DEEP_KEYWORDS |= {"history", "diagnosis", "progression", "chronic"}
#
# Or you can bypass keywords entirely by providing depth_detector.
# ─────────────────────────

DEEP_KEYWORDS: set[str] = {
    # English
    "history", "months", "ago", "rule", "decided", "changed",
    "compare", "trend", "evolution", "always", "never", "pattern",
    "long-term", "archive", "permanent", "all time", "everything",
    "ever", "remember", "forgot", "promise", "commitment",
    # Korean
    "이전", "개월", "전에", "규칙", "결정", "변경",
    "비교", "추세", "항상", "패턴", "장기", "약속",
    # Japanese
    "以前", "ヶ月", "ルール", "決定", "変更", "比較",
}

STANDARD_KEYWORDS: set[str] = {
    # English
    "last week", "recently", "summary", "overview", "recap",
    "review", "discuss", "mentioned", "earlier", "previous",
    # Korean
    "지난주", "최근", "요약", "리뷰", "이전에",
    # Japanese
    "先週", "最近", "要約", "レビュー",
}

# If none of the above match, defaults to CASUAL (L1 only)


class IntentDispatcher:
    """Detects search depth from the user's query.

    Usage:
        dispatcher = IntentDispatcher()
        depth = dispatcher.detect("what did I say 3 months ago?")
        # -> Depth.DEEP

        depth = dispatcher.detect("what's up?")
        # -> Depth.CASUAL
    """

    def __init__(
        self,
        depth_detector: Callable[[str], str] | None = None,
    ) -> None:
        """Initialize the dispatcher.

        Args:
            depth_detector: Optional AI callback that takes a query
                and returns a depth string ("casual", "standard", "deep").
                If provided, this takes priority over keyword matching.

        HOW TO CUSTOMIZE:
            # AI-powered depth detection (more accurate, costs API calls):
            def smart_detector(query):
                resp = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "system",
                        "content": 'Classify the query depth: casual, standard, or deep'
                    }, {"role": "user", "content": query}]
                )
                return resp.choices[0].message.content.strip().lower()

            dispatcher = IntentDispatcher(depth_detector=smart_detector)

            # Or just use the default keyword matching (free, fast):
            dispatcher = IntentDispatcher()
        """
        self._depth_detector = depth_detector

    def detect(self, query: str) -> Depth:
        """Detect the appropriate search depth for a query.

        Args:
            query: The user's question or search text.

        Returns:
            Depth.CASUAL, Depth.STANDARD, or Depth.DEEP

        HOW IT WORKS:
            1. If depth_detector callback is set, use it (AI decides)
            2. If not, scan query for keywords:
               - Contains DEEP keywords? -> Depth.DEEP
               - Contains STANDARD keywords? -> Depth.STANDARD
               - Neither? -> Depth.CASUAL (fast, cheap)
        """
        # ─── Option 1: AI callback ───
        if self._depth_detector is not None:
            try:
                result = self._depth_detector(query)
                return Depth(result.lower().strip())
            except (ValueError, Exception) as e:
                logger.warning("depth_detector failed, falling back to keywords: %s", e)

        # ─── Option 2: Keyword matching (default) ───
        query_lower = query.lower()

        # Check DEEP first (most specific)
        for keyword in DEEP_KEYWORDS:
            if keyword in query_lower:
                logger.debug("Detected DEEP depth for: %s", query[:50])
                return Depth.DEEP

        # Then STANDARD
        for keyword in STANDARD_KEYWORDS:
            if keyword in query_lower:
                logger.debug("Detected STANDARD depth for: %s", query[:50])
                return Depth.STANDARD

        # Default: CASUAL (fast, cheap)
        return Depth.CASUAL
