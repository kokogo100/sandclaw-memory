# ═══════════════════════════════════════════════════════════
# exceptions.py -- Custom Exception Hierarchy
#
# WHAT THIS MODULE DOES:
#   Defines all error types that sandclaw-memory can raise.
#   Every error inherits from SandclawError, so you can
#   catch ALL library errors with a single except clause:
#
#     try:
#         brain.save("something")
#     except SandclawError as e:
#         print(f"sandclaw-memory error: {e}")
#
# WHY A CUSTOM HIERARCHY?
#   If the library just raised generic Exception or ValueError,
#   you couldn't tell OUR errors from errors in your own code
#   or other libraries. Custom exceptions let you handle them
#   specifically.
#
# HIERARCHY:
#   SandclawError (base -- catch this to catch everything)
#     ├── ConfigurationError  -- wrong setup (missing callback, bad path)
#     ├── StorageError        -- SQLite read/write failure
#     └── CallbackError       -- your AI callback raised an error
#           └── TagExtractionError -- specifically the tag_extractor failed
#
# HOW TO CUSTOMIZE:
#   If you want to add your own error type, just subclass SandclawError:
#
#     class MyCustomError(SandclawError):
#         pass
# ═══════════════════════════════════════════════════════════

from __future__ import annotations

__all__ = [
    "SandclawError",
    "ConfigurationError",
    "StorageError",
    "CallbackError",
    "TagExtractionError",
]


class SandclawError(Exception):
    """Base exception for all sandclaw-memory errors.

    Catch this to handle every error the library can raise:

        try:
            brain.recall("query")
        except SandclawError as e:
            log.error(f"Memory error: {e}")
    """


class ConfigurationError(SandclawError):
    """Raised when the library is configured incorrectly.

    Common causes:
      - tag_extractor is None (it is required)
      - db_path points to an invalid location
      - encryption_key format is wrong

    The error message always includes HOW to fix the problem.
    """


class StorageError(SandclawError):
    """Raised when SQLite or filesystem operations fail.

    Common causes:
      - Database file is locked by another process
      - Disk is full
      - File permissions prevent writing
      - Corrupted database file
    """


class CallbackError(SandclawError):
    """Raised when a user-provided AI callback fails.

    This wraps whatever error your callback raised, so you
    can still see the original traceback.

    Common causes:
      - AI API returned an error (rate limit, auth failure)
      - Callback returned wrong type (expected list[str], got str)
      - Network timeout
    """


class TagExtractionError(CallbackError):
    """Raised specifically when tag_extractor fails.

    This is a subclass of CallbackError, so catching CallbackError
    will also catch this.

    Common causes:
      - AI API returned invalid JSON
      - tag_extractor returned None instead of list[str]
      - AI model refused to extract tags
    """
