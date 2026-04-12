# ═══════════════════════════════════════════════════════════
# renderer.py -- MarkdownRenderer (LLM-Ready Output)
#
# WHAT THIS MODULE DOES:
#   Converts memory data into clean Markdown that can be
#   injected into an LLM system prompt. Think of it as the
#   "presentation layer" -- it formats raw data into something
#   the AI can read efficiently.
#
# WHY MARKDOWN?
#   LLMs understand Markdown headers, bullet points, and
#   formatting. It's also human-readable, so you can debug
#   what the AI is actually "seeing".
#
# HOW TO CUSTOMIZE:
#   renderer = MarkdownRenderer(
#       content_truncate=800,    # longer snippets
#       summary_truncate=5000,   # longer summaries
#   )
#
# DEPENDS ON:
#   types.py (MemoryEntry)
#   utils.py (truncate)
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import logging

from sandclaw_memory.types import MemoryEntry
from sandclaw_memory.utils import truncate

__all__ = ["MarkdownRenderer"]

logger = logging.getLogger(__name__)


class MarkdownRenderer:
    """Converts memory entries into LLM-friendly Markdown.

    Usage:
        renderer = MarkdownRenderer()
        markdown = renderer.render_entries(entries, title="Search Results")
        # -> "## Search Results\\n- [python, react] Built a login page..."
    """

    def __init__(
        self,
        content_truncate: int = 450,
        summary_truncate: int = 2500,
    ) -> None:
        """Initialize the renderer.

        Args:
            content_truncate: Max chars per memory entry (default 450).
                Prevents a single long memory from taking all the space.
            summary_truncate: Max chars for summary text (default 2500).

        HOW TO CUSTOMIZE:
            # Show more of each memory:
            renderer = MarkdownRenderer(content_truncate=800)

            # More summary space:
            renderer = MarkdownRenderer(summary_truncate=5000)
        """
        self.content_truncate = content_truncate
        self.summary_truncate = summary_truncate

    def render_entries(
        self,
        entries: list[MemoryEntry],
        title: str = "Memories",
    ) -> str:
        """Render a list of memory entries as Markdown.

        Args:
            entries: List of MemoryEntry objects to render.
            title: Section header for the output.

        Returns:
            Markdown string with header and bullet points.

        Example output:
            ## Memories
            - [python, react] Built a login page with React...
            - [bugfix] Fixed the authentication timeout issue...
        """
        if not entries:
            return ""

        lines: list[str] = [f"## {title}"]
        for entry in entries:
            tags_str = ", ".join(entry.tags) if entry.tags else "untagged"
            content = truncate(entry.content, self.content_truncate)
            # Clean up newlines for inline display
            content = content.replace("\n", " ").strip()
            lines.append(f"- [{tags_str}] {content}")

        return "\n".join(lines)

    def render_summary(self, summary_text: str, title: str = "30-Day Summary") -> str:
        """Render a summary as Markdown.

        Args:
            summary_text: The summary text to render.
            title: Section header.

        Returns:
            Markdown string with header and truncated summary.
        """
        if not summary_text:
            return ""

        return f"## {title}\n{truncate(summary_text, self.summary_truncate)}"

    def render_context(
        self,
        session_text: str = "",
        summary_text: str = "",
        entries: list[MemoryEntry] | None = None,
    ) -> str:
        """Render a complete context block for LLM injection.

        This is a convenience method that combines session context,
        summary, and archive entries into one Markdown document.

        Args:
            session_text: Raw session context (from L1).
            summary_text: Summary text (from L2).
            entries: Archive entries (from L3).

        Returns:
            Complete Markdown context string.

        Example:
            context = renderer.render_context(
                session_text=session.get_context(),
                summary_text=summary.get_summary(),
                entries=archive.search("python"),
            )
            # Use in LLM prompt:
            messages = [{"role": "system", "content": f"Memory:\\n{context}"}]
        """
        parts: list[str] = []

        if session_text:
            parts.append(session_text)

        if summary_text:
            parts.append(self.render_summary(summary_text))

        if entries:
            parts.append(self.render_entries(entries, title="Related Memories"))

        return "\n\n".join(parts)
