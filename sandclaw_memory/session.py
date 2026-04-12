# ═══════════════════════════════════════════════════════════
# session.py -- L1 SessionMemory (Short-term, 3-day rolling)
#
# WHAT THIS MODULE DOES:
#   Stores recent conversations as Markdown log files.
#   Think of it as a "scratch pad" -- it keeps the last 3 days
#   of conversations and automatically deletes older ones.
#
# WHY MARKDOWN?
#   Markdown is human-readable. You can open these files in
#   any text editor and read your conversation history.
#   No special tools needed -- just open the file.
#
# HOW IT CONNECTS TO OTHER LAYERS:
#   L1 (this)       = sticky notes on your desk (3 days)
#   L2 (summary.py) = monthly summary report (30 days)
#   L3 (permanent.py) = filing cabinet (forever)
#
#   Important memories get "promoted" from L1 -> L3.
#   L2 summarizes what happened over the past 30 days.
#
# FILE STRUCTURE ON DISK:
#   {db_path}/
#     ├── PROFILE.md          <-- persistent user profile
#     └── logs/
#         ├── 2026-04-12.md   <-- today's conversations
#         ├── 2026-04-11.md   <-- yesterday
#         └── 2026-04-10.md   <-- 2 days ago
#
# HOW TO CUSTOMIZE:
#   - Change rolling_days to keep more/fewer days (default: 3)
#   - Change max_context_chars to control how much text is
#     loaded into the LLM prompt (default: 15000)
#   - Edit PROFILE.md directly to add custom sections
#
# DEPENDS ON:
#   utils.py (now_iso helper)
#   This module must NEVER import from brain.py or other layers.
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sandclaw_memory.utils import now_iso

__all__ = ["SessionMemory"]

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Default PROFILE.md Template
# ═══════════════════════════════════════════════════════════

# ─── WHY A PROFILE? ───
# The profile is a persistent Markdown file that stores
# long-lived user preferences and notes. Unlike daily logs
# (which get deleted after rolling_days), the profile stays
# forever.
#
# HOW TO CUSTOMIZE:
# Replace DEFAULT_PROFILE_TEMPLATE with your own string
# when creating SessionMemory:
#
#   session = SessionMemory(
#       base_path="./memory",
#       profile_template="# My Custom Profile\n\n## Notes\n"
#   )
# ──────────────────────

DEFAULT_PROFILE_TEMPLATE = """# User Profile

## Preferences
- (Your preferences will be recorded here)

## Important Notes
- (Important decisions and notes go here)

## AI Insights
- (AI-generated insights will be recorded here)
"""


class SessionMemory:
    """L1 short-term memory -- Markdown-based rolling log.

    This is the "recent memory" layer. It stores conversations
    as daily Markdown files and keeps them for `rolling_days` days.

    Usage:
        session = SessionMemory(base_path="./my_memory")
        session.save_conversation("What is Python?", "Python is...")
        context = session.get_context()  # recent conversations as text
    """

    def __init__(
        self,
        base_path: str = "./memory",
        rolling_days: int = 3,
        max_context_chars: int = 15_000,
        profile_template: str | None = None,
    ) -> None:
        """Initialize L1 SessionMemory.

        Args:
            base_path: Directory to store Markdown files.
            rolling_days: How many days of logs to keep (default 3).
            max_context_chars: Max characters to return in get_context().
                Controls how much recent text gets injected into LLM prompts.
            profile_template: Custom Markdown template for PROFILE.md.
                If None, uses the default template.

        HOW TO CUSTOMIZE:
            # Keep 7 days instead of 3:
            session = SessionMemory(rolling_days=7)

            # Allow more context (for models with large context windows):
            session = SessionMemory(max_context_chars=50_000)
        """
        self.base_path = Path(base_path)
        self.rolling_days = rolling_days
        self.max_context_chars = max_context_chars
        self._profile_template = profile_template or DEFAULT_PROFILE_TEMPLATE

        # ─── Create directories ───
        self.logs_path = self.base_path / "logs"
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # ─── Initialize PROFILE.md if it doesn't exist ───
        self.profile_path = self.base_path / "PROFILE.md"
        if not self.profile_path.exists():
            self.profile_path.write_text(self._profile_template, encoding="utf-8")

        logger.info("SessionMemory initialized at %s", self.base_path)

    # ═══════════════════════════════════════════════════════════
    # Saving Content
    # ═══════════════════════════════════════════════════════════

    def save_conversation(
        self,
        user_msg: str,
        ai_msg: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save a conversation turn to today's log.

        Args:
            user_msg: What the user said.
            ai_msg: What the AI responded.
            metadata: Optional extra info (stored as a comment in Markdown).

        HOW IT WORKS:
            Each conversation gets appended to today's Markdown file
            (e.g. logs/2026-04-12.md). The file is human-readable --
            you can open it in any text editor.

        HOW TO CUSTOMIZE:
            If you want to add extra fields (e.g. "mood", "topic"),
            pass them in metadata:
                session.save_conversation("Hi", "Hello!",
                    metadata={"mood": "happy", "topic": "greeting"})
        """
        log_file = self._get_today_log_path()

        now = datetime.now(timezone.utc)
        time_str = now.strftime("%H:%M")

        # ─── Build the Markdown entry ───
        entry = f"\n## {time_str} Conversation\n"
        entry += f"**User**: {user_msg}\n"
        entry += f"**AI**: {ai_msg}\n"

        if metadata:
            # Store metadata as a Markdown comment (invisible when rendered)
            import json

            entry += f"<!-- metadata: {json.dumps(metadata, ensure_ascii=False)} -->\n"

        self._append_to_log(log_file, entry)
        logger.debug("Saved conversation at %s", time_str)

    def save_entry(
        self,
        content: str,
        entry_type: str = "note",
    ) -> None:
        """Save a freeform entry to today's log.

        Args:
            content: The text content to save.
            entry_type: Label for the entry (e.g. "note", "action", "insight").

        Use this for anything that isn't a conversation turn:
            session.save_entry("Deployed v2.0 to production", entry_type="action")
            session.save_entry("User prefers dark mode", entry_type="insight")
        """
        log_file = self._get_today_log_path()

        now = datetime.now(timezone.utc)
        time_str = now.strftime("%H:%M")

        entry = f"\n## {time_str} {entry_type.capitalize()}\n"
        entry += f"{content}\n"

        self._append_to_log(log_file, entry)
        logger.debug("Saved %s entry at %s", entry_type, time_str)

    # ═══════════════════════════════════════════════════════════
    # Profile Management
    # ═══════════════════════════════════════════════════════════

    def update_profile(self, section: str, content: str) -> None:
        """Add a line to a specific section of PROFILE.md.

        Args:
            section: The section header (without "## " prefix).
            content: The text to add as a bullet point.

        Example:
            session.update_profile("Preferences", "Favorite language: Python")
            # This adds "- Favorite language: Python" under "## Preferences"

        HOW TO CUSTOMIZE:
            If the section doesn't exist, it gets created at the end
            of PROFILE.md. You can organize sections however you want.
        """
        if not self.profile_path.exists():
            self.profile_path.write_text(self._profile_template, encoding="utf-8")

        text = self.profile_path.read_text(encoding="utf-8")
        section_header = f"## {section}"

        if section_header in text:
            # ─── Insert content into existing section ───
            lines = text.split("\n")
            new_lines: list[str] = []
            in_section = False
            content_added = False

            for line in lines:
                new_lines.append(line)

                if line.strip() == section_header:
                    in_section = True
                    continue

                if in_section and line.startswith("## "):
                    # Reached the next section -- insert before it
                    if not content_added:
                        new_lines.insert(-1, f"- {content}")
                        content_added = True
                    in_section = False

            # If we were in the last section, append at the end
            if in_section and not content_added:
                new_lines.append(f"- {content}")

            self.profile_path.write_text("\n".join(new_lines), encoding="utf-8")
        else:
            # ─── Section doesn't exist -- create it at the end ───
            with open(self.profile_path, "a", encoding="utf-8") as f:
                f.write(f"\n{section_header}\n- {content}\n")

    def get_profile(self) -> str:
        """Read the entire PROFILE.md content.

        Returns:
            The profile text, or empty string if the file doesn't exist.
        """
        if self.profile_path.exists():
            return self.profile_path.read_text(encoding="utf-8")
        return ""

    # ═══════════════════════════════════════════════════════════
    # Reading / Context
    # ═══════════════════════════════════════════════════════════

    def get_context(self) -> str:
        """Get recent memory context for LLM injection.

        Returns:
            A Markdown string containing:
            1. User profile (PROFILE.md)
            2. Recent conversation logs (last rolling_days days)

        The result is truncated to max_context_chars to fit
        within LLM token budgets.

        HOW IT WORKS:
            This is the main method you call when building an LLM prompt.
            It assembles recent history + profile into a single string
            that you inject as system context.

        Example:
            context = session.get_context()
            # Use context in your LLM prompt:
            messages = [
                {"role": "system", "content": f"Memory:\\n{context}"},
                {"role": "user", "content": user_question}
            ]
        """
        parts: list[str] = []

        # ─── 1. Load profile (persistent) ───
        profile = self.get_profile()
        if profile:
            parts.append(profile)

        # ─── 2. Load recent logs (rolling window) ───
        parts.append("\n## Recent Conversations")
        today = datetime.now(timezone.utc)

        for i in range(self.rolling_days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = self.logs_path / f"{date}.md"

            if log_file.exists():
                log_content = log_file.read_text(encoding="utf-8")
                parts.append(f"\n### {date}")
                parts.append(log_content)

        result = "\n".join(parts)

        # ─── 3. Truncate if too long ───
        # WHY TRUNCATE FROM THE FRONT?
        # Recent memories matter more than old ones.
        # If we must cut, we keep the END (most recent) and
        # remove the BEGINNING (oldest).
        if self.max_context_chars > 0 and len(result) > self.max_context_chars:
            result = result[-self.max_context_chars :]
            # Clean cut at the first newline (don't start mid-sentence)
            first_newline = result.find("\n")
            if first_newline > 0:
                result = "...(truncated)\n" + result[first_newline + 1 :]

        return result

    def get_today_log(self) -> str:
        """Get only today's log content.

        Returns:
            Today's Markdown log content, or empty string.
        """
        log_file = self._get_today_log_path()
        if log_file.exists():
            return log_file.read_text(encoding="utf-8")
        return ""

    def get_log_by_date(self, date: str) -> str:
        """Get log content for a specific date.

        Args:
            date: Date string in YYYY-MM-DD format.

        Returns:
            The log content, or empty string if not found.
        """
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            logger.warning("Invalid date format rejected: %s", date)
            return ""
        log_file = self.logs_path / f"{date}.md"
        if log_file.exists():
            return log_file.read_text(encoding="utf-8")
        return ""

    def search_logs(self, keyword: str, days: int = 7) -> list[dict[str, str]]:
        """Search recent logs for a keyword.

        Args:
            keyword: Text to search for (case-insensitive).
            days: How many days back to search (default 7).

        Returns:
            List of dicts with "date" and "content" keys.
        """
        results: list[dict[str, str]] = []
        today = datetime.now(timezone.utc)
        keyword_lower = keyword.lower()

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = self.logs_path / f"{date}.md"

            if log_file.exists():
                content = log_file.read_text(encoding="utf-8")
                if keyword_lower in content.lower():
                    # Extract matching sections
                    sections = content.split("\n## ")
                    for section in sections:
                        if keyword_lower in section.lower():
                            snippet = section[:500]
                            if len(section) > 500:
                                snippet += "..."
                            results.append({"date": date, "content": "## " + snippet})

        return results

    # ═══════════════════════════════════════════════════════════
    # Maintenance
    # ═══════════════════════════════════════════════════════════

    def cleanup(self, keep_days: int | None = None) -> int:
        """Delete log files older than keep_days.

        Args:
            keep_days: Override for rolling_days. If None, uses
                the value set in __init__.

        Returns:
            Number of log files deleted.

        HOW TO CUSTOMIZE:
            # Delete everything older than 30 days:
            session.cleanup(keep_days=30)

            # Or rely on the default (rolling_days from __init__):
            session.cleanup()
        """
        days = keep_days if keep_days is not None else self.rolling_days
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=days)
        deleted_count = 0

        for log_file in self.logs_path.glob("*.md"):
            try:
                file_date = datetime.strptime(log_file.stem, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                if file_date < cutoff:
                    log_file.unlink()
                    deleted_count += 1
            except ValueError:
                # Filename isn't a date -- skip it
                continue

        if deleted_count > 0:
            logger.info("Cleaned up %d old log files", deleted_count)
        return deleted_count

    # ═══════════════════════════════════════════════════════════
    # Stats & Export
    # ═══════════════════════════════════════════════════════════

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the session memory.

        Returns:
            Dict with log count, total size, profile size, etc.
        """
        log_files = list(self.logs_path.glob("*.md"))
        total_size = sum(f.stat().st_size for f in log_files)

        profile_size = 0
        if self.profile_path.exists():
            profile_size = self.profile_path.stat().st_size

        return {
            "log_files_count": len(log_files),
            "total_log_size_kb": round(total_size / 1024, 2),
            "profile_size_kb": round(profile_size / 1024, 2),
            "rolling_days": self.rolling_days,
            "base_path": str(self.base_path),
        }

    def export(self) -> dict[str, Any]:
        """Export all session data as a dictionary.

        Returns:
            Dict with "profile", "logs", and "exported_at" keys.
            Useful for backup or migration.
        """
        result: dict[str, Any] = {
            "profile": self.get_profile(),
            "logs": {},
            "exported_at": now_iso(),
        }

        for log_file in sorted(self.logs_path.glob("*.md"), reverse=True)[:30]:
            result["logs"][log_file.stem] = log_file.read_text(encoding="utf-8")

        return result

    def import_data(self, data: dict[str, Any]) -> bool:
        """Import session data from an export dict.

        Args:
            data: Dict with "profile" and/or "logs" keys.

        Returns:
            True if import succeeded, False otherwise.
        """
        try:
            if "profile" in data and data["profile"]:
                self.profile_path.write_text(data["profile"], encoding="utf-8")

            if "logs" in data:
                for date, content in data["logs"].items():
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                        logger.warning("Skipping invalid date key: %s", date)
                        continue
                    log_file = self.logs_path / f"{date}.md"
                    log_file.write_text(content, encoding="utf-8")

            logger.info("Imported session data successfully")
            return True
        except Exception:
            logger.exception("Failed to import session data")
            return False

    # ═══════════════════════════════════════════════════════════
    # Internal Helpers
    # ═══════════════════════════════════════════════════════════

    def _get_today_log_path(self) -> Path:
        """Get the path to today's log file."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.logs_path / f"{today}.md"

    def _append_to_log(self, log_file: Path, entry: str) -> None:
        """Append text to a log file, creating the daily header if needed.

        Args:
            log_file: Path to the log file.
            entry: The Markdown text to append.
        """
        if not log_file.exists():
            header = f"# {log_file.stem} Conversation Log\n"
            log_file.write_text(header, encoding="utf-8")

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)
