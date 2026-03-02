# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot that integrates with Claude Code SDK to run Claude Code sessions and skills from Telegram. Written in Python 3.11+, fully async. All user-facing strings are in Chinese (zh-CN).

## Code Style

- All code, comments, variable names, shell messages, and log strings must be in **English**
- User-facing strings sent to Telegram (bot replies) are in Chinese (zh-CN)


```bash
# Setup
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# Run (foreground, default)
./start.sh --path /absolute/path/to/project

# Run (daemon/background)
./start.sh --path /absolute/path/to/project -d

# Debug mode (verbose logging + chat file logging)
./start.sh --path /absolute/path/to/project --debug

# Direct Python invocation
python -m telegram_bot --path /absolute/path/to/project --debug

# Lifecycle
./start.sh --path /path --status
./start.sh --path /path --stop
./start.sh --path /path --install    # macOS launchd auto-start
./start.sh --path /path --uninstall
```

No test suite exists yet.

## Architecture

```
__main__.py          CLI entry → parses --path/--debug → calls bot.run()
    │
core/bot.py          TelegramBot — command handlers, access control,
    │                permission gating, response formatting, message queuing
    │
core/project_chat.py ProjectChatHandler — per-user long-lived Claude SDK
    │                streams, message queueing, tool permission callbacks,
    │                response processing, session history browsing
    │
session/             SessionManager/SessionStore — per-user state in JSON
    │                (PROJECT_ROOT/.telegram_bot/sessions.json)
    │
utils/config.py      Pydantic Settings config from .env
utils/chat_logger.py Per-session debug chat logging
```

### Key data flows

- **User message** → `TelegramBot` handler → access check → `ProjectChatHandler.process_message()` → Claude SDK stream → response back to Telegram
- **Permission gating**: Tool requests pass through `_permission_callback()` in bot.py. File access inside `PROJECT_ROOT` is auto-allowed; outside requires user confirmation via Telegram inline buttons.
- **Per-user streams**: Each user gets a persistent `ClaudeSDKClient` connection in `ProjectChatHandler._streams`. Streams are reused across messages and cleared on `/new` or model change.
- **Session state**: Three layers — Telegram-side (SessionStore JSON), SDK-side (~/.claude/projects/{name}/*.jsonl), runtime tracking (_runtime_active_sessions dict).

### Important patterns

- `AskUserQuestion` tool is degraded: converted to plain text with numbered options rendered as Telegram inline keyboard buttons.
- Responses with file paths matching media extensions are auto-sent as Telegram photos/documents.
- Message queue per user: max 3 concurrent tasks with overflow rejection.
- `start.sh` handles venv creation, dependency caching (MD5-based), log rotation (14 days), auto-restart with crash detection (>5 in 60s).

## Key environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram Bot API token |
| `ALLOWED_USER_IDS` | No | Comma-separated user IDs; empty = allow all |
| `CLAUDE_CLI_PATH` | No | Absolute path to Claude CLI binary |
| `CLAUDE_PROCESS_TIMEOUT` | No | SDK timeout in seconds (default: 600) |
| `PROXY_URL` | No | HTTP proxy; start.sh auto-configures env vars |
| `PROJECT_ROOT` | Set by start.sh | Base path for all file access validation |

## Runtime directories

All bot data writes to `PROJECT_ROOT/.telegram_bot/`:
- `sessions.json` — user session persistence
- `logs/bot.log` — main log (daily rotation)
- `logs/error_YYYYMMDD.log` — error log
- `logs/{user_id}_{session_id}_{date}.log` — debug chat logs

SDK conversation logs: `~/.claude/projects/{PROJECT_DIR_NAME}/*.jsonl`
