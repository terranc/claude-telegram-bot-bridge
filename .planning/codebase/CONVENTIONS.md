# Coding Conventions

**Analysis Date:** 2026-03-22

## Overview

This codebase follows Python 3.11+ async patterns with strict typing and modular architecture. All code, comments, and log strings are in **English** per project requirements.

## Style Guidelines

### Indentation and Formatting
- **Indentation:** 4 spaces (no tabs)
- **Line Length:** 100 characters (soft limit), 120 (hard limit)
- **Quotes:** Double quotes for strings, single quotes only for docstrings when needed
- **Trailing Commas:** Required in multi-line collections

### Import Organization
Imports follow this order (separated by blank lines):
1. Standard library imports
2. Third-party package imports
3. Local module imports (using absolute paths)

Example from `/Users/terranc/www/telegram_bot/utils/audio_processor.py`:
```python
import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence
```

## Naming Conventions

### Variables and Functions
- **Variables:** `snake_case` (e.g., `audio_file`, `user_id`)
- **Functions:** `snake_case` with verb-first naming (e.g., `process_message`, `cleanup_stale_files`)
- **Constants:** `SCREAMING_SNAKE_CASE` at module level (e.g., `WHISPER_PRICE_PER_MINUTE_USD`)

### Classes
- **Classes:** `PascalCase` with noun-first naming
- **Private classes:** Leading underscore (e.g., `_PollingRestart`)
- **Exception classes:** Suffix with `Error` (e.g., `TranscriptionError`, `TtsSynthesisError`)

Examples from `/Users/terranc/www/telegram_bot/core/streaming.py`:
```python
@dataclass
class DraftState:
    message_id: int
    text: str
    last_update_time: float
    char_count_since_update: int = 0
    draft_id: Optional[str] = None


class StreamingMessageHandler:
    def __init__(self, bot: Bot, chat_id: int, user_id: int):
        ...
```

## Code Patterns

### Async Patterns
- **All I/O is async:** Use `async`/`await` for network calls, file operations, subprocesses
- **Prefer `asyncio.create_subprocess_exec`** over blocking subprocess calls
- **Use `AsyncMock`** for mocking async functions in tests

Example from `/Users/terranc/www/telegram_bot/utils/audio_processor.py`:
```python
async def check_ffmpeg_available(self) -> bool:
    exists = shutil.which(self.ffmpeg_path) is not None
    if not exists:
        logger.warning("ffmpeg binary not found: %s", self.ffmpeg_path)
    return exists
```

### Type Hints
- **All function parameters and return types must be typed**
- **Use `Optional[T]`** for nullable types
- **Use `List[T]`, `Dict[K, V]`** from `typing` module
- **Use `Path`** from `pathlib` for file paths

Example from `/Users/terranc/www/telegram_bot/utils/config.py`:
```python
from typing import Optional, List
from pathlib import Path

class Config(BaseSettings):
    claude_cli_path: Optional[Path] = Field(
        default=None,
        description="Optional absolute path to Claude CLI binary",
    )
    allowed_user_ids: List[int] = Field(
        default_factory=list,
        description="List of allowed Telegram user IDs (empty = allow all)",
    )
```

### Configuration with Pydantic
- **Use `pydantic_settings.BaseSettings`** for all configuration
- **Use `Field()`** for descriptions and defaults
- **Use `@field_validator`** for custom validation logic
- **Environment variables map to field names (case-insensitive)**

Example from `/Users/terranc/www/telegram_bot/utils/config.py`:
```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=[str(ENV_FILE_PATH), str(BOT_ENV_FILE_PATH)],
        extra="ignore",
    )

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v):
        """Parse allowed_user_ids from string or list"""
        if isinstance(v, str):
            if not v or v.strip() == "":
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v
```

## Error Handling

### Custom Exceptions
- **Define custom exception classes** for domain-specific errors
- **Inherit from `RuntimeError` or `Exception`**
- **Use descriptive error messages** with context

Example from `/Users/terranc/www/telegram_bot/utils/transcription.py`:
```python
class TranscriptionError(RuntimeError):
    """Raised when transcription fails after retries."""

class EmptyTranscriptionError(TranscriptionError):
    """Raised when provider returns empty or whitespace-only text."""
```

### Error Logging
- **Use `logger.exception()`** inside except blocks to include stack traces
- **Use `logger.error()`** for user-facing errors with context
- **Use `logger.warning()`** for recoverable issues
- **Include relevant identifiers** (user_id, file paths) in log messages

Example:
```python
except OSError as exc:
    logger.warning(
        "Failed to remove temporary audio file %s: %s", path, exc
    )
```

## Documentation

### Docstrings
- **Use triple-double quotes** for all docstrings
- **First line is a brief description**
- **Follow Google/PEP 257 style** for complex functions
- **Document exceptions raised** with `:raises:`

Example from `/Users/terranc/www/telegram_bot/core/streaming.py`:
```python
class StreamingMessageHandler:
    """
    Handles progressive streaming of AI responses using Telegram draft messages.

    Manages draft message lifecycle: creation, updates, finalization, and cancellation.
    Supports multi-message handling for content exceeding 4000 characters.
    """

    async def create_draft(self, text: str) -> Optional[DraftState]:
        """Send initial draft message"""
        ...
```

### Comments
- **Explain WHY, not WHAT** - code should be self-explanatory
- **Use `#` for inline comments** sparingly
- **Keep comments current** - outdated comments are worse than none
- **Use type hints instead of comments** for describing types

## Testing Patterns (Summary)

See `TESTING.md` for comprehensive testing documentation. Quick reference:
- Tests live in `/Users/terranc/www/telegram_bot/tests/`
- Uses Python `unittest` with `IsolatedAsyncioTestCase` for async tests
- Test files named `test_<module>.py`
- Mock external I/O and services
- Use `TemporaryDirectory` for filesystem tests

---

*Convention analysis: 2026-03-22*
