# Technology Stack

**Analysis Date:** 2026-03-22

## Overview

Telegram Bot Bridge is a Python-based async application that integrates Claude Code SDK with Telegram, enabling users to interact with Claude AI through Telegram messages, including voice transcription and TTS responses.

## Languages & Runtime

**Primary Language:** Python 3.11+

**Runtime Environment:**
- Standard CPython interpreter
- Async/await pattern throughout
- Event loop managed by `asyncio`

**Key Language Features Used:**
- Type hints with `typing` module
- Dataclasses for structured data
- Async/await for I/O operations
- Pathlib for filesystem operations

## Core Frameworks & Libraries

### Web Framework / Bot Framework
- **python-telegram-bot** >=20.7 - Official Telegram Bot API wrapper
  - Uses `Application` class for bot lifecycle
  - Command handlers, message handlers, callback query handlers
  - Built-in polling with auto-retry

### AI/ML Integration
- **claude-code-sdk** >=0.0.25 - Official Claude Code SDK
  - `ClaudeSDKClient` for conversation management
  - `ClaudeCodeOptions` for configuration
  - Permission callbacks for tool access

### Configuration & Validation
- **pydantic** >=2.0.0 - Data validation using Python type hints
- **pydantic-settings** >=2.0.0 - Settings management from env vars
- **python-dotenv** >=1.0.0 - Load environment from `.env` files

### Voice/Audio Processing
- **openai** >=1.0.0 - OpenAI API client for Whisper transcription
- **tos** - Volcengine TOS (Toutiao Object Storage) SDK for file staging
- **ffmpeg** (external binary) - Audio format conversion

### macOS Integration
- **macOS `say` command** - TTS (Text-to-Speech) for voice replies

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| python-telegram-bot | >=20.7 | Telegram Bot API |
| claude-code-sdk | >=0.0.25 | Claude Code integration |
| pydantic | >=2.0.0 | Data validation |
| pydantic-settings | >=2.0.0 | Configuration |
| python-dotenv | >=1.0.0 | Environment loading |
| openai | >=1.0.0 | Whisper API |
| tos | latest | Volcengine object storage |

## Configuration

**Configuration Files:**
- `.env` - Project-specific environment (in `PROJECT_ROOT/.telegram_bot/`)
- `.env` (bot source) - Global fallback configuration
- `.env.example` - Template with all available options

**Configuration Management:**
- `utils/config.py` - Pydantic-based settings class
- Environment variables take precedence
- Type coercion and validation on startup

**Key Configuration Categories:**
1. **Telegram Bot** - Token, polling settings, retry behavior
2. **Claude Integration** - CLI path, timeout, settings path
3. **Voice/Audio** - Transcription provider (whisper/volcengine), TTS settings
4. **Access Control** - Allowed user IDs
5. **Streaming** - Draft update intervals

## Development Tools

**Build/Package Management:**
- `requirements.txt` - Pip dependency specification
- `start.sh` - Bash-based orchestration script with venv management
- Virtual environment auto-creation in `venv/`

**Testing:**
- `unittest` - Python standard library testing
- Test files in `tests/` directory with `test_*.py` naming
- 20+ test modules covering core functionality

**Code Quality:**
- Type hints throughout (no mypy config found)
- Docstrings for public APIs
- Logging with structured format

**Runtime Monitoring:**
- Health reporter in `utils/health.py`
- Health status JSON file for process monitoring
- Log rotation (14 days retention)

## Platform Requirements

**Development:**
- Python 3.11+
- macOS (for TTS voice replies via `say` command)
- ffmpeg (for audio conversion)
- bash 4+ (for start.sh)

**Production:**
- Same as development
- Linux/macOS server environment
- launchd (macOS) for service management
- Environment variables for secrets

---

*Stack analysis: 2026-03-22*
