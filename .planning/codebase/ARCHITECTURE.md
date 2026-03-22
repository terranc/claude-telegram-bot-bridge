# Architecture

**Analysis Date:** 2026-03-22

## Overview

Telegram Bot is an async Python application that integrates Claude Code SDK with Telegram Bot API. It provides a bridge between Telegram users and Claude AI, supporting text messages, voice transcription, and real-time streaming responses.

**Key Architectural Pattern:** Layered architecture with clear separation between presentation (Telegram handlers), business logic (session/chat management), and infrastructure (external API integrations).

## Design Patterns

### 1. Singleton Pattern
- `SessionStore` (`session/store.py`): Single JSON-backed storage instance
- `SessionManager` (`session/manager.py`): Centralized session state management
- `ProjectChatHandler` (`core/project_chat.py`): Single handler for Claude SDK streams

### 2. Factory Pattern
- `StreamingMessageHandler` (`core/streaming.py`): Creates draft messages with unique IDs
- Audio processors and transcribers are instantiated based on configuration

### 3. Observer Pattern
- Telegram `Application` with `CommandHandler`, `MessageHandler`, `CallbackQueryHandler`
- Asyncio `Future` objects for permission callbacks

### 4. State Machine Pattern
- User session states: `reply_mode` (text/voice), pending questions, permission flows
- Stream lifecycle: `init` → `connected` → `processing` → `completed/error`

### 5. Producer-Consumer Pattern
- `ProjectChatHandler._reader_loop()`: Consumes messages from Claude SDK stream
- `asyncio.Queue` for pending requests per user stream

## Layer Structure

### Layer 1: Entry Point (`__main__.py`)
- **Purpose:** CLI argument parsing, environment setup, logging initialization
- **Key Files:**
  - `__main__.py`: Argument parsing for `--path`, `--debug`
  - `utils/config.py`: `Config` class with Pydantic validation

### Layer 2: Bot Layer (`core/bot.py`)
- **Purpose:** Telegram Bot handlers, command routing, access control
- **Key Components:**
  - `TelegramBot`: Main bot class with command handlers
  - Permission callback system for file access outside `PROJECT_ROOT`
  - Voice message handling with transcription
  - Streaming response coordination
- **Key Files:**
  - `core/bot.py`: `TelegramBot` class (~1200 lines)

### Layer 3: Chat Handler Layer (`core/project_chat.py`)
- **Purpose:** Claude SDK integration, per-user persistent streams
- **Key Components:**
  - `ProjectChatHandler`: Manages `ClaudeSDKClient` per user
  - `_UserStreamState`: Per-user stream state with locks and pending queue
  - `_PendingRequest`: Request wrapper with `asyncio.Future`
  - `ChatResponse`: Response dataclass with streaming flags
- **Key Files:**
  - `core/project_chat.py`: `ProjectChatHandler` class (~1030 lines)

### Layer 4: Streaming Layer (`core/streaming.py`)
- **Purpose:** Progressive draft message updates for real-time AI responses
- **Key Components:**
  - `StreamingMessageHandler`: Manages Telegram draft messages
  - `DraftState`: Tracks message state with timing and character counts
  - Overflow handling for 4000 character limit
  - Rate limiting with exponential backoff
- **Key Files:**
  - `core/streaming.py`: `StreamingMessageHandler` class (~315 lines)

### Layer 5: Session Layer (`session/`)
- **Purpose:** User session persistence and state management
- **Key Components:**
  - `SessionStore`: JSON-backed persistent storage
  - `SessionManager`: High-level session operations (reply mode, timestamps)
- **Key Files:**
  - `session/store.py`: `SessionStore` class (~68 lines)
  - `session/manager.py`: `SessionManager` class (~124 lines)

### Layer 6: Utilities Layer (`utils/`)
- **Purpose:** Cross-cutting concerns (audio, transcription, config, logging)
- **Key Components:**
  - `AudioProcessor`: ffmpeg-based audio conversion
  - `WhisperTranscriber` / `VolcengineFileFastTranscriber`: Speech-to-text
  - `MacOSTtsSynthesizer`: Text-to-speech for voice replies
  - `VolcengineTOSUploader`: Object storage for voice files
  - `ChatLogger`: Per-session debug logging
  - `HealthReporter`: Health check reporting
- **Key Files:**
  - `utils/audio_processor.py`: `AudioProcessor` class (~136 lines)
  - `utils/transcription.py`: Transcriber classes (~425 lines)
  - `utils/tts.py`: `MacOSTtsSynthesizer` class (~120 lines)
  - `utils/tos_uploader.py`: `VolcengineTOSUploader` class (~150 lines)
  - `utils/chat_logger.py`: `log_chat()` function (~70 lines)
  - `utils/health.py`: `HealthReporter` class (~180 lines)
  - `utils/config.py`: `Config` class with Pydantic (~400 lines)

## Data Flow

### Text Message Flow

```
1. User sends message → Telegram Bot API
   ↓
2. telegram.ext.MessageHandler
   ↓
3. TelegramBot._handle_message()
   - Access control check
   - Auto-new session detection (24h inactivity)
   ↓
4. session_manager.set_last_user_message_at()
   ↓
5. TelegramBot._process_user_message()
   - Create streaming handler
   - Call project_chat_handler.process_message()
   ↓
6. ProjectChatHandler.process_message()
   - Get/create user stream state
   - Create pending request with Future
   - Send to Claude SDK via client.query()
   ↓
7. ProjectChatHandler._reader_loop() (background)
   - Receive AssistantMessage with text blocks
   - Update streaming handler with text chunks
   - Receive ResultMessage with final result
   - Resolve Future with ChatResponse
   ↓
8. StreamingMessageHandler.update_if_needed()
   - Accumulate text chunks
   - Update Telegram draft messages
   - Handle 4000 char overflow
   ↓
9. TelegramBot._send_smart() / _reply_smart()
   - Send final response
   - Handle numbered options with inline keyboard
   ↓
10. User receives response
```

### Voice Message Flow

```
1. User sends voice message → Telegram Bot API
   ↓
2. TelegramBot._handle_voice_message()
   - Download voice file
   - Detect audio format
   ↓
3. AudioProcessor.convert_audio()
   - Convert to Whisper-friendly format (16kHz mono)
   ↓
4. WhisperTranscriber.transcribe_audio()
   - Call OpenAI Whisper API
   - Retry with backoff on failure
   ↓
5. Transcribed text → _process_user_message()
   - Prepend with "🎤 Voice:" preview
   - Continue with text message flow
```

### Permission Request Flow

```
1. Claude SDK tool execution requests file outside PROJECT_ROOT
   ↓
2. can_use_tool() callback invoked
   - Check if path is within PROJECT_ROOT
   - If outside, trigger permission callback
   ↓
3. TelegramBot._permission_callback()
   - Send permission request message with inline keyboard
   - Store Future in _pending_permission_futures
   ↓
4. User clicks Allow/Deny/Allow All button
   ↓
5. TelegramBot._handle_permission_callback()
   - Resolve Future with PermissionResultAllow/Deny
   ↓
6. Tool execution continues or denied based on user choice
```

### Revert Flow

```
1. User sends /revert command
   ↓
2. TelegramBot._revert_command()
   - Check for active streaming, cancel if needed
   - Get conversation history from JSONL
   ↓
3. Display paginated message history with inline keyboard
   ↓
4. User selects message and mode (restore code/conversation/both, summarize)
   ↓
5. TelegramBot._handle_revert_callback()
   - Truncate SDK JSONL to selected message
   - Clear active stream
   - Reset session state
   ↓
6. User receives confirmation of revert operation
```

## Key Abstractions

### 1. ChatResponse
**Purpose:** Standard response from Claude SDK processing
**File:** `core/project_chat.py`
```python
@dataclass
class ChatResponse:
    content: str
    success: bool = True
    error: Optional[str] = None
    session_id: Optional[str] = None
    has_options: bool = False
    streamed: bool = False
```

### 2. _UserStreamState
**Purpose:** Per-user Claude SDK connection state
**File:** `core/project_chat.py`
```python
@dataclass
class _UserStreamState:
    client: ClaudeSDKClient
    model: Optional[str]
    send_lock: asyncio.Lock
    pending: Deque[_PendingRequest]
    reader_task: Optional[asyncio.Task]
    typing_task: Optional[asyncio.Task]
    last_session_id: Optional[str]
```

### 3. StreamingMessageHandler
**Purpose:** Progressive draft message updates
**File:** `core/streaming.py`
```python
class StreamingMessageHandler:
    drafts: List[DraftState]
    accumulated_text: str
    min_chars: int  # 150 default
    min_interval: float  # 1.0s default
```

### 4. PermissionCallback
**Purpose:** Async callback for tool permission decisions
**File:** `core/project_chat.py`
```python
PermissionCallback = Callable[
    [int, int, str, Dict[str, Any]],  # chat_id, user_id, tool_name, tool_input
    Awaitable  # Returns bool or PermissionResult
]
```

### 5. SessionStore
**Purpose:** Persistent JSON-backed user session storage
**File:** `session/store.py`
```python
class SessionStore:
    _local_data: Dict[str, Any]
    _lock: asyncio.Lock
    _storage_path: Path  # PROJECT_ROOT/.telegram_bot/sessions.json
```

## Entry Points

### 1. Main Entry Point
**File:** `__main__.py`
**Purpose:** CLI argument parsing and bot startup
```bash
python -m telegram_bot --path /path/to/project --debug
```

### 2. Bot Run Method
**File:** `core/bot.py` → `TelegramBot.run()`
**Purpose:** Initialize health reporter and run async event loop

### 3. Async Entry Point
**File:** `core/bot.py` → `TelegramBot._run_async()`
**Purpose:** Manage Application lifecycle with polling restart loop

### 4. Start Script Entry Point
**File:** `start.sh`
**Purpose:** Shell wrapper for venv management, dependency installation, and bot lifecycle

---

*Architecture analysis: 2026-03-22*
