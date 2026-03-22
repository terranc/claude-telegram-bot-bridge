# Directory Structure

**Analysis Date:** 2026-03-22

## Overview

Telegram Bot follows a modular Python package structure with clear separation of concerns. The project is organized into layers: entry point, core bot logic, session management, and utilities.

## Directory Layout

```
telegram_bot/
├── __main__.py              # CLI entry point
├── __init__.py              # Package marker
├── core/                    # Core bot functionality
│   ├── __init__.py
│   ├── bot.py              # TelegramBot class (~1200 lines)
│   ├── project_chat.py     # ProjectChatHandler, Claude SDK integration
│   └── streaming.py        # StreamingMessageHandler for draft messages
├── session/                 # Session persistence
│   ├── __init__.py
│   ├── manager.py          # SessionManager, reply mode handling
│   └── store.py            # SessionStore, JSON persistence
├── utils/                   # Cross-cutting utilities
│   ├── __init__.py
│   ├── audio_processor.py  # AudioProcessor, ffmpeg wrapper
│   ├── chat_logger.py      # Per-session debug logging
│   ├── config.py           # Config class with Pydantic settings
│   ├── health.py           # HealthReporter for monitoring
│   ├── tos_uploader.py     # VolcengineTOSUploader for voice files
│   ├── transcription.py    # WhisperTranscriber, Volcengine transcriber
│   └── tts.py              # MacOSTtsSynthesizer for voice replies
├── skills/                  # Skill modules (empty structure)
│   └── __init__.py
├── interaction/             # Interaction handlers
│   └── __init__.py
├── docs/                    # Documentation
│   └── plans/
├── hooks/                   # Git hooks
├── openspec/                # OpenAPI specifications
│   └── specs/
├── tests/                   # Test suite
│   ├── test_*.py           # Unit/integration tests
│   └── __pycache__/
├── venv/                    # Python virtual environment
├── .telegram_bot/           # Runtime data (logs, sessions, audio)
├── .planning/               # Planning documents
│   └── codebase/
│       ├── ARCHITECTURE.md
│       └── STRUCTURE.md
├── start.sh                 # Shell wrapper for bot lifecycle
├── setup.sh                 # Setup script
├── requirements.txt         # Python dependencies
├── CLAUDE.md                # Project instructions
├── README.md                # Documentation
├── README-zh.md             # Chinese documentation
├── CHANGELOG.md             # Version history
└── AGENTS.md                # Agent documentation
```

## Key Locations

### Entry Points
- **`__main__.py`**: CLI entry, argument parsing (`--path`, `--debug`)
- **`core/bot.py:TelegramBot.run()`**: Main bot execution
- **`start.sh`**: Shell wrapper for venv and dependency management

### Core Logic
- **`core/bot.py`**: TelegramBot class with command handlers, permission system, voice handling
- **`core/project_chat.py`**: ProjectChatHandler for Claude SDK integration
- **`core/streaming.py`**: StreamingMessageHandler for draft message updates

### Configuration
- **`utils/config.py`**: Pydantic-based Config class with env var validation
- **`.env`**: Environment variables (TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, etc.)

### Session Management
- **`session/store.py`**: SessionStore for JSON persistence
- **`session/manager.py`**: SessionManager for reply modes and timestamps

### Testing
- **`tests/`**: Test files following `test_*.py` naming
- Run with: `python -m pytest tests/`

## Naming Conventions

### Files
- **Modules:** lowercase_with_underscores (e.g., `project_chat.py`, `audio_processor.py`)
- **Classes:** PascalCase (e.g., `TelegramBot`, `ProjectChatHandler`)
- **Functions:** lowercase_with_underscores (e.g., `process_message`, `transcribe_audio`)
- **Constants:** UPPER_SNAKE_CASE (e.g., `ALLOWED_TOOLS`, `PROCESS_TIMEOUT`)

### Directories
- All lowercase, descriptive names: `core/`, `utils/`, `session/`, `tests/`

### Private Members
- Single underscore prefix: `_pending_permission_futures`, `_reader_loop()`
- Internal dataclasses: `_PendingRequest`, `_UserStreamState`

## Module Organization

### `core/` - Bot Core
| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `bot.py` | Telegram bot handlers | `TelegramBot` |
| `project_chat.py` | Claude SDK integration | `ProjectChatHandler`, `ChatResponse` |
| `streaming.py` | Draft message streaming | `StreamingMessageHandler`, `DraftState` |

### `session/` - Session Management
| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `store.py` | JSON persistence | `SessionStore` |
| `manager.py` | Session operations | `SessionManager` |

### `utils/` - Utilities
| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `config.py` | Configuration | `Config`, `setup_logging()` |
| `audio_processor.py` | Audio conversion | `AudioProcessor` |
| `transcription.py` | Speech-to-text | `WhisperTranscriber`, `VolcengineFileFastTranscriber` |
| `tts.py` | Text-to-speech | `MacOSTtsSynthesizer` |
| `chat_logger.py` | Debug logging | `log_chat()` |
| `health.py` | Health monitoring | `HealthReporter` |
| `tos_uploader.py` | Object storage | `VolcengineTOSUploader` |

## Where to Add New Code

### New Command Handler
1. Add handler method to `TelegramBot` class in `core/bot.py`
2. Register handler in `_setup_handlers()` method
3. Add command to `_set_bot_commands()` for bot menu

### New Utility Function
1. Add to appropriate module in `utils/` directory
2. For new category, create new module with `__init__.py`
3. Export from module's `__all__` if applicable

### New Session Field
1. Add default value logic to `SessionManager` in `session/manager.py`
2. Use `session_manager.update_session()` to persist
3. Access via `session_manager.get_session()`

### New External Integration
1. Create client class in `utils/` directory
2. Add configuration fields to `utils/config.py`
3. Initialize in `TelegramBot.__init__()` if needed at startup

---

*Structure analysis: 2026-03-22*
