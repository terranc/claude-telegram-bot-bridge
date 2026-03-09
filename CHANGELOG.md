# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-03-10

### Added
- `/cd` command to change per-user working directory
- `/ls` command to list directory contents

### Fixed
- Improve Windows and directory-name compatibility
- Auto-detect Git Bash path on Windows via cygpath
- Improve Windows compatibility for SDK subprocess launching
- Improve error resilience and deliver late results for timed-out tasks

## [0.8.2] - 2026-03-10

### Fixed
- Add event loop watchdog that detects zombie state (asyncio loop closed but process alive) and force-exits, allowing start.sh auto-restart to recover
- Enable launchd `KeepAlive` so the service auto-restarts even if start.sh itself exits (e.g. rapid crash limit)

### Changed
- Enhanced `--status` command to detect inactive bots via log mtime checking, reporting detailed diagnostics instead of a misleading "running" status

## [0.8.1] - 2026-03-08

### Fixed
- Volcengine voice transcription now deletes the temporary TOS object after ASR completes, preventing staged voice files from accumulating over time
- TOS cleanup failures are isolated to logs and no longer affect user-facing transcription replies

### Changed
- Extended TOS uploader API to return uploaded object metadata (`object_key` + signed URL) for explicit post-transcription cleanup
- Added tests covering TOS object deletion on both success and failure paths

## [0.8.0] - 2026-03-08

### Added
- macOS voice reply mode with TTS support: bot automatically replies with voice when user sends voice messages, using macOS `say` command + ffmpeg conversion
- Smart voice delivery strategy based on response length (voice-only, text+voice, or text-only fallback)
- `VOICE_REPLY_PERSONA` config for selecting macOS TTS voice persona

### Fixed
- Voice reply mode gracefully falls back to text on non-macOS platforms

### Changed
- Updated README documentation (EN/ZH) with voice reply mode usage guide

## [0.7.0] - 2026-03-08

### Added
- Volcengine ASR support for voice transcription as an alternative to OpenAI Whisper
- TOS (Tencent Object Storage) upload flow for Volcengine ASR integration

### Changed
- Added Star History chart to README files

## [0.6.3] - 2026-03-06

### Changed
- Renamed project from "Telegram Skill Bot" to "Claude Telegram Bot Bridge"
- Updated project name in README.md, README-zh.md, and start.sh
- Changed version display from "Bot version" to "Bridge version"
- Simplified update notification to non-interactive text prompt

## [0.6.2] - 2026-03-06

### Added
- Auto-update check on startup with 1-hour cache to detect new releases
- Interactive upgrade prompt when update is available (upgrade now / skip)
- `--upgrade` command for one-click bot updates via git pull and dependency reinstall
- Version comparison logic to determine if update is needed
- Graceful handling of network failures during update check

### Changed
- Updated README.md and README-zh.md with upgrade command documentation
- Added auto-update feature to Operations section in documentation

## [0.6.1] - 2026-03-05

### Changed
- Simplified bot command descriptions for better user experience in Telegram command menu

## [0.6.0] - 2026-03-05

### Added
- `/revert` command to restore conversation to any previous message state
- 5 revert modes: full restore (code + conversation), conversation only, code only, summarize from point, or cancel
- Paginated history browser showing last 50 messages with inline keyboard navigation
- Priority handling for `/revert`: bypasses message queue limit and cancels active operations
- Interactive mode selection via Telegram inline buttons
- Conversation state restoration by truncating SDK JSONL files to selected message

### Changed
- Updated documentation (README.md, README-zh.md) with `/revert` usage examples
- Improved button text consistency: changed "Never mind" to "Cancel"

## [0.5.0] - 2026-03-05

### Added
- Native Telegram voice message support with automatic transcription via OpenAI Whisper API
- Audio format detection and conversion (OGG/AMR → MP3) using ffmpeg
- Voice message preview in chat: `🎤 Voice: [transcribed text]` before forwarding to Claude
- Priority `/stop` command: immediately cancels running tasks and voice transcription, even when message queue is full
- Comprehensive test coverage for audio processing, transcription, and voice message flow
- Voice configuration options: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `WHISPER_MODEL`, `MAX_VOICE_DURATION`, `FFMPEG_PATH`
- Automatic cleanup of temporary audio files and stale audio detection
- Retry logic with exponential backoff for Whisper API calls
- Voice message duration validation and cost/duration logging

### Changed
- `/setup` skill now includes optional voice message configuration step
- `.env.example` updated with voice-related configuration options
- Enhanced error handling for voice message processing with user-friendly error messages
- Updated documentation (README, CLAUDE.md) with voice message feature details

## [0.4.0] - 2026-03-04

### Added
- `/setup` skill for conversational, multi-language installation via Claude Code
- Support for installation in any language (English, Chinese, Japanese, Spanish, French, German, etc.)
- Interactive installation wizard with 4-step process (system check, configuration, Python environment, completion)

### Changed
- Renamed `install.sh` to `setup.sh` for consistency with skill naming
- Moved Python virtual environment creation and dependency installation from `start.sh` to `setup.sh`
- `start.sh` now checks for completed installation and provides friendly error message if not installed
- Installation flow now requires running `setup.sh` or `/setup` skill before `start.sh`
- Improved installation prompts with better formatting and clearer instructions
- Fixed color code rendering issues in installation scripts (added `-e` flag to all `echo` commands with color variables)

### Fixed
- Script references in README updated from `install.sh` to `setup.sh`
- Command examples in documentation now reflect new installation flow

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
