# External Integrations

**Analysis Date:** 2026-03-22

## Overview

The Telegram Bot Bridge integrates with multiple external services:
- **Telegram Bot API** - Primary interface for user communication
- **Claude Code SDK** - AI conversation and code execution
- **OpenAI Whisper** - Voice transcription (optional)
- **Volcengine** - Alternative ASR with TOS file staging (optional)
- **macOS Speech** - TTS for voice replies (optional)

## APIs & Services

### Telegram Bot API
**Purpose:** Primary user interface - message handling, commands, inline keyboards

**Integration Point:** `core/bot.py`

**Key Components:**
- `python-telegram-bot` library >=20.7
- `Application` class for bot lifecycle
- `CommandHandler`, `MessageHandler`, `CallbackQueryHandler`
- Polling-based message receiving

**Authentication:**
- `TELEGRAM_BOT_TOKEN` environment variable (required)
- Bot token from @BotFather

**Rate Limits:**
- Handled by library with auto-retry
- `network_retry_attempts` config (default: 3)
- `network_retry_delay` config (default: 5s)

### Claude Code SDK
**Purpose:** AI conversation, code execution, file operations

**Integration Point:** `core/project_chat.py`

**Key Components:**
- `ClaudeSDKClient` - Main client for conversations
- `ClaudeCodeOptions` - Configuration (model, timeout, etc.)
- Permission callbacks for tool access control
- `SubprocessCLITransport` for CLI communication

**Authentication:**
- Uses user's Claude CLI credentials (from `~/.claude/`)
- `CLAUDE_CLI_PATH` env var for custom binary location

**Models Available:**
- Sonnet (`sonnet`)
- Opus (`opus`)
- Haiku (`haiku`)

**Key Features:**
- Streaming responses with real-time draft updates
- Tool use (Read, Edit, Write, Bash, etc.)
- Permission gating for file access outside `PROJECT_ROOT`
- Session history with revert capabilities

### OpenAI Whisper API
**Purpose:** Voice message transcription (primary or fallback)

**Integration Point:** `utils/transcription.py`

**Key Components:**
- `WhisperTranscriber` class
- `openai.AsyncOpenAI` client
- Retry with exponential backoff
- Cost estimation ($0.006/minute)

**Authentication:**
- `OPENAI_API_KEY` environment variable
- Optional `OPENAI_BASE_URL` for custom endpoints

**Configuration:**
- `WHISPER_MODEL` (default: `whisper-1`)
- `max_retries` (default: 3)
- `initial_backoff` (default: 1.0s)

### Volcengine BigModel ASR
**Purpose:** Alternative ASR provider with submit/query workflow

**Integration Point:** `utils/transcription.py`

**Key Components:**
- `VolcengineFileFastTranscriber` class
- Submit endpoint for task creation
- Query endpoint for result polling
- Automatic retry with exponential backoff

**Endpoints:**
- Submit: `https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit`
- Query: `https://openspeech.bytedance.com/api/v3/auc/bigmodel/query`

**Authentication:**
- `VOLCENGINE_APP_ID` - Application ID
- `VOLCENGINE_TOKEN` - Access token

**Required for TOS staging:**
- `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_ACCESS_KEY`
- `VOLCENGINE_TOS_BUCKET_NAME`
- `VOLCENGINE_TOS_ENDPOINT`

### Volcengine TOS (Toutiao Object Storage)
**Purpose:** File staging for Volcengine ASR

**Integration Point:** `utils/tos_uploader.py`

**Key Components:**
- `VolcengineTOSUploader` class
- Upload local audio files to TOS
- Generate signed URLs for ASR access
- `tos` Python SDK

**Authentication:**
- Access Key / Secret Access Key (IAM credentials)
- Bucket name and endpoint

## Databases & Storage

### File-Based Storage

**Session Store:**
- Location: `PROJECT_ROOT/.telegram_bot/sessions.json`
- Format: JSON
- Content: Per-user session state, model preferences, history metadata

**Conversation Logs (Claude SDK):**
- Location: `~/.claude/projects/{PROJECT_DIR_NAME}/*.jsonl`
- Format: JSONL (one JSON object per line)
- Content: Full conversation history per session

**Application Logs:**
- Location: `PROJECT_ROOT/.telegram_bot/logs/`
- Files:
  - `bot.log` - Main application log
  - `error_YYYY-MM-DD.log` - Daily error logs with stack traces
  - `{user_id}_{session_id}_{date}.log` - Per-session debug chat logs
- Retention: 14 days (auto-cleanup)

**Health Status:**
- Location: `PROJECT_ROOT/.telegram_bot/health.json`
- Format: JSON
- Content: Service health state, Telegram/Claude connectivity status
- Updated: Every watchdog interval (60s)

### Data Structures

**Session State (in-memory):**
```python
{
    user_id: {
        "model": str,  # Current Claude model
        "session_id": str,  # Active session ID
        "last_activity": datetime,
        "permissions": dict,  # Tool permission cache
    }
}
```

**Runtime Task Tracking:**
- `_active_tasks: Dict[int, asyncio.Task]` - Currently executing tasks per user
- `_user_run_tasks: Dict[int, set[asyncio.Task]]` - Active /run command tasks
- `_user_voice_tasks: Dict[int, set[asyncio.Task]]` - Active voice processing tasks

## Authentication & Authorization

### Telegram Bot Authentication
- **Mechanism:** Bot Token (from @BotFather)
- **Storage:** Environment variable `TELEGRAM_BOT_TOKEN`
- **Validation:** Pydantic validator on startup
- **Token Lock:** File-based lock prevents multiple instances with same token

### Claude CLI Authentication
- **Mechanism:** User's Claude CLI credentials
- **Storage:** `~/.claude/` directory (managed by Claude CLI)
- **Session Files:** `~/.claude/projects/{name}/*.jsonl`
- **SDK Integration:** Auto-discovers credentials via SDK

### Access Control (User Whitelist)
- **Mechanism:** Comma-separated allowed user IDs
- **Storage:** `ALLOWED_USER_IDS` environment variable
- **Validation:** All messages checked against whitelist (if non-empty)
- **Admin Override:** None (whitelist strictly enforced)

### Tool Permission System
- **Auto-allowed tools:** All tools within `PROJECT_ROOT`
- **External access:** Requires user confirmation via inline keyboard
- **Permission options:**
  - Allow (once)
  - Deny
  - Allow All (session-wide)
- **Timeout:** 60 seconds for user response

### Volcengine Authentication (optional)
- **App ID / Token:** For ASR API access
- **Access Key / Secret:** For TOS bucket access
- **IAM Credentials:** From Volcengine console

## Webhooks & Events

### Telegram Polling (Not Webhooks)
- **Method:** Long-polling via `python-telegram-bot`
- **Reason:** Simpler deployment, works behind NAT/firewall
- **Timeout:** Configurable (default 30s)
- **Retry:** Auto-retry on network errors

### Message Handling Flow

**Text Messages:**
1. `MessageHandler` receives update
2. Access control check (whitelist)
3. Session validation/auto-resume
4. Message queue check (max 3 concurrent)
5. `ProjectChatHandler.process_message()`
6. Claude SDK streaming response
7. Telegram draft message updates

**Voice Messages:**
1. Voice `MessageHandler` receives update
2. Download audio file
3. `AudioProcessor` - format detection/conversion
4. Transcription (Whisper or Volcengine)
5. Text injected as `🎤 Voice:` prefix
6. Same flow as text message

**Commands:**
- `/start` - Initialize session
- `/new` - Start new conversation
- `/stop` - Cancel current operation
- `/revert` - Browse and restore history
- `/model` - Change Claude model
- `/resume` - Resume previous session
- `/skills` - List/manage skills

### Callback Queries (Inline Keyboards)
- Permission requests (Allow/Deny/Allow All)
- Revert history navigation (prev/next/page)
- Revert mode selection (5 modes)
- Menu/cancel actions

### Event-Driven Architecture

**Asyncio Tasks:**
- Main polling loop (telegram)
- Per-user message processing tasks
- Voice transcription tasks
- Streaming draft update tasks
- Health reporter background task

**Synchronization Primitives:**
- `asyncio.Lock` per user message queue
- `asyncio.Future` for permission callbacks
- `set[asyncio.Task]` for task tracking

---

*Integration analysis: 2026-03-22*
