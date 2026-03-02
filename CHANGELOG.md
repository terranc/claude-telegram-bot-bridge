# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-03

### Added
- Progressive streaming for AI responses using Telegram draft messages with real-time updates
- Telegram draft API compatibility layer with graceful fallback to regular messages
- Automatic detection of numbered options in responses (not just `AskUserQuestion` tool)
- Streaming configuration via `DRAFT_UPDATE_MIN_CHARS` and `DRAFT_UPDATE_INTERVAL` environment variables

### Fixed
- Duplicate message issue when responses contain option buttons: streamed messages are no longer re-sent
- Improved `AskUserQuestion` denial message with clearer formatting instructions for the AI

### Changed
- Streaming message handler now uses regular `send_message` for initial draft creation to ensure message_id availability
- Large text chunks are split into progressive updates for smoother streaming experience

## [0.2.1] - 2026-03-02

### Added
- Session progress summary: show last assistant message when switching sessions via `/resume`

### Changed
- Remove hardcoded zh-CN language policy; bot preset strings stay minimal English, LLM handles language adaptation naturally

## [0.2.0] - 2026-03-02

### Added
- Long message auto-splitting: responses are split at paragraph/line boundaries (4000-char limit) and sent as multiple messages instead of being truncated
- Typing keepalive loop: background task sends typing indicator at regular intervals during long tool calls to prevent Telegram from dropping the typing status

### Fixed
- Removed 4000-character hard truncation from `_clean_response`; full response content is now preserved
- Inline option keyboard now only appears for `AskUserQuestion` degraded responses (via `force_options` flag), preventing false positives on numbered lists in regular replies

## [0.1.0] - 2026-03-02

### Added
- Telegram bot integration with Claude Code SDK for running Claude sessions from Telegram
- Per-user persistent Claude SDK streams with session history browsing
- Permission gating for file access: auto-allow inside `PROJECT_ROOT`, inline button confirmation for outside
- Message queue per user (max 3 concurrent tasks with overflow rejection)
- `AskUserQuestion` tool degraded to Telegram inline keyboard buttons
- Auto-send media files (photos/documents) when response contains matching file paths
- Session persistence via JSON store (`PROJECT_ROOT/.telegram_bot/sessions.json`)
- Bilingual documentation (English and Chinese)
- `start.sh` lifecycle manager with venv creation, dependency caching, log rotation (14 days), and crash detection
- macOS launchd auto-start support via `--install` / `--uninstall`
- Debug mode with verbose logging and per-session chat file logging
- Proxy support via `PROXY_URL` environment variable
