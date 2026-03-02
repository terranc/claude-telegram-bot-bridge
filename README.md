# Telegram Skill Bot

[中文文档](README-zh.md)

Turn your Telegram into a remote Claude Code terminal. Chat with Claude, run skills, edit code, search files — all from your phone, anywhere.

## The Problem

Claude Code is powerful, but it's bound to your terminal. When you step away from your computer — commuting, in a meeting, or just on the couch — you lose access. You can't quickly check a build result, ask Claude to fix a bug, or run a skill command until you're back at your desk.

Solutions like [OpenClaw](https://github.com/anthropics/openclaw) exist, but they come with trade-offs: a full web stack to deploy and maintain, potential security concerns with exposing your dev environment through a web interface, and heavyweight infrastructure that feels like overkill when you just want to quickly send Claude a message from your phone.

This bot takes a different approach — **lightweight, zero-infrastructure, secure by default**. It connects Claude Code SDK to a Telegram bot (a messaging app you already have), so you get a persistent, always-on Claude Code session you can talk to from anywhere. No web server, no ports to expose, no extra auth layer. Start it once for a project directory, and it runs as a daemon in the background — surviving crashes, rebooting with your Mac, managing its own dependencies. Telegram itself handles authentication, encryption, and push notifications.

## Features

**Core**
- Chat with Claude directly in Telegram, powered by Claude Code SDK
- Invoke any Claude Code skill (`/skill <name>`) or slash command (`/command <cmd>`) remotely
- Switch between Sonnet, Opus, and Haiku on the fly via `/model`
- Resume previous conversations with `/resume` and browse session history

**Smart Interaction**
- Progressive streaming: AI responses update in real-time as Claude thinks, not after completion
- Claude's numbered options auto-convert to Telegram inline keyboard buttons — just tap to choose
- File paths (images, PDFs, etc.) in Claude's responses are automatically sent as photos or documents
- Per-user dedicated SDK streams — low latency, concurrent message support (up to 3 per user)

**Security**
- File access inside the project directory is auto-allowed
- Access outside the project triggers inline-button confirmation in Telegram
- User whitelist via `ALLOWED_USER_IDS`
- Stale messages (>20 min) are silently dropped

**Operations**
- Daemon mode with auto-restart on crash (stops after 5 rapid crashes in 60s)
- One-command macOS launchd auto-start on boot (`--install`)
- MD5-based dependency caching — skips reinstall when `requirements.txt` is unchanged
- Auto venv creation, 14-day log rotation, crash logging with exit codes

## Prerequisites

- **Python 3.11+**
- **Claude CLI** — installed and in `$PATH`, or specify via `CLAUDE_CLI_PATH`
- **Telegram Bot Token** — from [@BotFather](https://t.me/BotFather)

## Quick Start

1. **Set up the environment:**

```bash
cd telegram_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

2. **Configure:**

```bash
cp .env.example .env
# Edit .env — add your TELEGRAM_BOT_TOKEN
```

3. **Set up a global alias** (recommended) — add to `~/.zshrc` or `~/.bashrc`:

```bash
alias tgbot='/absolute/path/to/telegram_bot/start.sh --path'
```

Then start from any project directory:

```bash
cd ~/my-project
tgbot .                # Start bot for current directory
tgbot . --debug        # Debug mode
tgbot . --status       # Check if running
tgbot . --stop         # Stop
```

4. **Or call `start.sh` directly:**

```bash
./start.sh --help                                # Show help
./start.sh --path /path/to/project              # Foreground (default)
./start.sh --path /path/to/project -d           # Daemon/background
./start.sh --path /path/to/project --debug       # Debug mode
```

## Usage Examples

### Fix a bug from your phone

You're away from your desk and a teammate reports a bug. Open Telegram:

```
You:   login page crashes when email contains a plus sign
Claude: I found the issue in src/auth/validator.ts:42 — the regex
        doesn't escape the + character. Fixed and the test passes now.
```

### Run a skill remotely

```
You:   /skill commit
Claude: Created commit: fix(auth): escape special characters in email validation
```

### Resume yesterday's work

```
You:   /resume
Bot:   1. Refactoring auth module — 2 hours ago
       2. Adding dark mode — yesterday
       3. API rate limiting — 3 days ago

You:   1
Bot:   Switched to session: Refactoring auth module

You:   where did we leave off?
Claude: We finished extracting the JWT logic into a separate service.
        Still remaining: updating the middleware to use the new service...
```

### Switch models mid-conversation

```
You:   /model haiku
Bot:   Switched to Claude Haiku

You:   summarize the changes in src/api/ from the last 3 commits
Claude: ...
```

### Let the bot run 24/7

```bash
# Install as macOS startup service — survives reboots
tgbot ~/my-project --install

# Check status anytime
tgbot ~/my-project --status
# 🟢 Bot is running (PID: 12345)

# Uninstall when done
tgbot ~/my-project --uninstall
```

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Start a conversation |
| `/new` | Start a new session (clears current stream and cancels ongoing streaming) |
| `/model` | Switch model (Sonnet / Opus / Haiku) |
| `/resume` | Browse and resume a previous session (shows progress summary with last assistant message) |
| `/stop` | Terminate the current running task |
| `/skills` | List available Claude Code skills |
| `/skill <name> [args]` | Execute a skill command |
| `/command <cmd> [args]` | Execute a Claude Code slash command |

Any unrecognized `/command` is also forwarded as a skill invocation.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram Bot API token |
| `ALLOWED_USER_IDS` | No | *(allow all)* | Comma-separated user ID whitelist |
| `CLAUDE_CLI_PATH` | No | *(auto-detect)* | Absolute path to Claude CLI binary |
| `CLAUDE_SETTINGS_PATH` | No | `~/.claude/settings.json` | Path to Claude Code settings file |
| `CLAUDE_PROCESS_TIMEOUT` | No | `600` | SDK timeout in seconds |
| `DRAFT_UPDATE_MIN_CHARS` | No | `150` | Minimum characters before streaming draft update |
| `DRAFT_UPDATE_INTERVAL` | No | `1.0` | Minimum seconds between streaming draft updates |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `PROXY_URL` | No | — | HTTP proxy; auto-configures `http_proxy`/`https_proxy`/`all_proxy` |

## Security

- `--path` sets the `PROJECT_ROOT` — the sandbox boundary for all file operations.
- File access within `PROJECT_ROOT` is auto-allowed. Outside access requires user confirmation via inline buttons.
- Bot output referencing external files requires confirmation before sending.
- All runtime data stays under `PROJECT_ROOT/.telegram_bot/`.

## Lifecycle Management

```bash
tgbot . --status       # Check if running
tgbot . --stop         # Stop
tgbot . --install      # macOS launchd auto-start on boot
tgbot . --uninstall    # Remove auto-start
```

The daemon auto-restarts on crash, logs each crash with exit code and uptime, and stops restarting after 5 rapid crashes in 60 seconds.

## Debugging

```bash
tgbot . --debug
# Or: BOT_DEBUG=1 python -m telegram_bot --path .
```

Enables full console logging, per-session chat logs, and SDK tool call tracing.

## License

MIT
