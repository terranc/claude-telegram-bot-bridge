#!/bin/bash

# Telegram Skill Bot startup script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
ENV_FILE="$SCRIPT_DIR/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Version check cache
CACHE_DIR="$HOME/.telegram-bot-cache"
CACHE_FILE="$CACHE_DIR/update_check"

get_current_version() {
    grep -E "^## \[[0-9]" "$SCRIPT_DIR/CHANGELOG.md" | head -1 | sed -E 's/^## \[([0-9.]+)\].*/\1/'
}

compare_versions() {
    [ "$1" = "$2" ] && return 1
    local IFS=.
    local i ver1=($1) ver2=($2)
    for ((i=0; i<${#ver1[@]} || i<${#ver2[@]}; i++)); do
        [ "${ver1[i]:-0}" -gt "${ver2[i]:-0}" ] && return 2
        [ "${ver1[i]:-0}" -lt "${ver2[i]:-0}" ] && return 0
    done
    return 1
}

check_update() {
    local current
    current="$(get_current_version)"

    mkdir -p "$CACHE_DIR"
    if [ -f "$CACHE_FILE" ] && [ -n "$(find "$CACHE_FILE" -mmin -60 2>/dev/null)" ]; then
        echo -e "\033[90m✓ Bridge version: v${current} (up to date)\033[0m"
        return
    fi

    local latest
    latest="$(curl -sL --max-time 3 "https://api.github.com/repos/terranc/claude-telegram-bot-bridge/releases/latest" 2>/dev/null | grep -o '"tag_name": *"v[^"]*"' | sed 's/.*"v\([^"]*\)".*/\1/')"
    [ -z "$latest" ] && return
    touch "$CACHE_FILE"
    if compare_versions "$current" "$latest"; then
        echo -e "${BLUE}📦 Update available: v${current} → v${latest}${NC}"
        echo -e "${BLUE}   Run: ./start.sh --upgrade${NC}"
    else
        echo -e "\033[90m✓ Bridge version: v${current} (up to date)\033[0m"
    fi
}

# Check if installation is complete
if [ ! -d "$VENV_DIR" ] || [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo -e "${RED}❌ Installation not found${NC}"
    echo ""
    echo "Please run the installation script first:"
    echo -e "  ${BLUE}./setup.sh${NC}"
    echo ""
    echo "The installation wizard will guide you through:"
    echo "  • System requirements check"
    echo "  • Bot configuration (Token, whitelist, proxy)"
    echo "  • Python environment setup"
    echo ""
    exit 1
fi

ACTION="run"
DAEMON_MODE=0  # Default to foreground mode

# Show help when no arguments are given
if [ $# -eq 0 ]; then
    set -- "--help"
fi

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --path)
            export PROJECT_ROOT="$2"
            shift 2
            ;;
        --debug)
            export BOT_DEBUG=1
            export LOG_LEVEL=DEBUG
            shift
            ;;
        -d|--daemon)
            DAEMON_MODE=1
            shift
            ;;
        --install)
            ACTION="install"
            shift
            ;;
        --uninstall)
            ACTION="uninstall"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --stop)
            ACTION="stop"
            shift
            ;;
        --upgrade)
            ACTION="upgrade"
            shift
            ;;
        --_daemon_child)
            # Internal flag: marks current process as daemon child, run in foreground
            DAEMON_MODE=0
            shift
            ;;
        -h|--help)
            cat <<EOF
Usage: $0 <project_path> [options]
       $0 --path <project_path> [options]

Options:
  -h, --help          Show this help message and exit
  --path <dir>        Set project root directory (required for all actions)
  -d, --daemon        Run bot in background (default: foreground)
  --debug             Enable debug/verbose logging
  --status            Show whether the bot is running
  --stop              Stop the running bot
  --upgrade           Update bot to latest version
  --install           Install as macOS launchd startup service
  --uninstall         Remove macOS launchd startup service
EOF
            exit 0
            ;;
        *)
            # First non-option argument as project path
            if [ -z "$PROJECT_ROOT" ]; then
                export PROJECT_ROOT="$1"
            fi
            shift
            ;;
    esac
done

echo "🤖 Claude Telegram Bot Bridge"
echo "================================"

if [ -n "$BOT_DEBUG" ]; then
    echo "🐛 Debug mode enabled"
fi

if [ -z "$PROJECT_ROOT" ]; then
    echo "❌ Error: Please specify project path"
    echo "Usage: $0 <project_path>  or  $0 --path <project_path>"
    exit 1
fi

# Validate project path
PROJECT_ROOT="$(cd "$PROJECT_ROOT" 2>/dev/null && pwd)" || {
    echo "❌ Error: Project path does not exist: $PROJECT_ROOT"
    exit 1
}
export PROJECT_ROOT
echo "📂 Project path: $PROJECT_ROOT"
BOT_DATA_DIR="$PROJECT_ROOT/.telegram_bot"
LOGS_DIR="$BOT_DATA_DIR/logs"
PID_FILE="$BOT_DATA_DIR/bot.pid"
ENV_FILE="$BOT_DATA_DIR/.env"
ENV_EXAMPLE_FILE="$SCRIPT_DIR/.env.example"
PROJECT_SLUG="$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-*$//')"
PLIST_LABEL="com.telegram-skill-bot.${PROJECT_SLUG}"
PLIST_FILE="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
mkdir -p "$LOGS_DIR"

# ── PID utility functions ──

read_pid() {
    [ -f "$PID_FILE" ] && cat "$PID_FILE"
}

is_running() {
    local pid
    pid="$(read_pid)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cleanup_pid() {
    rm -f "$PID_FILE"
}

# ── Action handlers ──

do_status() {
    local pid
    pid="$(read_pid)"
    if [ -z "$pid" ]; then
        echo "⚪ Bot is not running (no PID file)"
        exit 0
    fi
    if kill -0 "$pid" 2>/dev/null; then
        echo "🟢 Bot is running (PID: $pid)"
    else
        echo "🔴 Bot is not running (PID $pid is stale)"
        cleanup_pid
    fi
    exit 0
}

do_stop() {
    local pid
    pid="$(read_pid)"
    if [ -z "$pid" ]; then
        echo "⚪ Bot is not running"
        exit 0
    fi
    if kill -0 "$pid" 2>/dev/null; then
        echo "🛑 Stopping Bot (PID: $pid)..."
        kill "$pid"
        # Wait for process to exit, max 10 seconds
        for i in $(seq 1 10); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "⚠️  Process not responding to SIGTERM, sending SIGKILL..."
            kill -9 "$pid" 2>/dev/null
            sleep 0.5
        fi
        cleanup_pid
        echo "✅ Bot stopped"
    else
        echo "🔴 Process $pid no longer exists, cleaning up PID file"
        cleanup_pid
    fi
    exit 0
}

read_env_value() {
    local key="$1"
    local file="${2:-$ENV_FILE}"
    [ -f "$file" ] || return 0
    local line
    line="$(grep -E "^${key}=" "$file" | tail -n1)"
    [ -n "$line" ] || return 0
    local value="${line#*=}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    echo "$value"
}

_is_valid_token() {
    [ -n "$1" ] && [ "$1" != "your_bot_token_here" ]
}

# Read a config value from project .env, falling back to bot source dir .env
read_env_with_fallback() {
    local key="$1"
    local value
    value="$(read_env_value "$key")"
    if [ -z "$value" ]; then
        value="$(read_env_value "$key" "$SCRIPT_DIR/.env")"
    fi
    echo "$value"
}

# ── Ensure project config exists and validate required settings ──
check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE_FILE" ]; then
            echo "📝 Creating project config file..."
            cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
            echo "✅ Created: $ENV_FILE"
        else
            echo "❌ Error: config template not found: $ENV_EXAMPLE_FILE"
            exit 1
        fi
    fi

    local bot_token
    bot_token="$(read_env_value "TELEGRAM_BOT_TOKEN")"
    if _is_valid_token "$bot_token"; then
        return
    fi

    # Fallback: check bot source dir .env
    bot_token="$(read_env_value "TELEGRAM_BOT_TOKEN" "$SCRIPT_DIR/.env")"
    if _is_valid_token "$bot_token"; then
        echo "ℹ️  Using TELEGRAM_BOT_TOKEN from $SCRIPT_DIR/.env (fallback)"
        return
    fi

    # No valid token anywhere — guide user
    echo ""
    echo "⚠️  TELEGRAM_BOT_TOKEN is not configured"
    echo "Open Telegram, search @BotFather, send /newbot to create a bot and get the token."
    echo ""
    if [ -t 0 ]; then
        printf "Enter Bot Token: "
        read -r INPUT_TOKEN
        if [ -z "$INPUT_TOKEN" ]; then
            echo "❌ Token cannot be empty. Please re-run and enter a valid token."
            exit 1
        fi
        if grep -q "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE"; then
            sed -i '' "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${INPUT_TOKEN}|" "$ENV_FILE"
        else
            echo "TELEGRAM_BOT_TOKEN=${INPUT_TOKEN}" >> "$ENV_FILE"
        fi
        echo "✅ Token saved to $ENV_FILE"
        echo ""
        echo "💡 To configure optional settings (ALLOWED_USER_IDS, PROXY_URL, etc.), edit:"
        echo "   $ENV_FILE"
        echo ""
    else
        echo "Please edit the config file and set TELEGRAM_BOT_TOKEN:"
        echo "   $ENV_FILE"
        echo ""
        echo "💡 See comments in the file for optional settings. Re-run after configuration."
        exit 1
    fi
}

do_install() {
    check_env
    # Refuse if an instance is already running (any startup mode)
    if is_running; then
        echo "⚠️  Bot is already running in background (PID: $(read_pid)). Use --stop first."
        exit 1
    fi
    if is_token_locked; then
        echo "⚠️  Another instance is already using the same Bot Token (PID: $(cat "$TOKEN_LOCK_FILE")). Stop it first."
        exit 1
    fi
    echo "📝 Generating launchd plist: $PLIST_FILE"
    mkdir -p "$(dirname "$PLIST_FILE")"
    cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-l</string>
        <string>${SCRIPT_DIR}/start.sh</string>
        <string>--path</string>
        <string>${PROJECT_ROOT}</string>
        <string>--_daemon_child</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${LOGS_DIR}/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOGS_DIR}/launchd_stderr.log</string>
    <key>WorkingDirectory</key>
    <string>${REPO_ROOT}</string>
</dict>
</plist>
PLIST
    # Ensure old service is unloaded first
    launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null
    # Load using new API
    if launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE"; then
        echo "✅ Installed and loaded as startup service"
        echo "🚀 Bot started via launchd"
    else
        echo "⚠️  launchctl bootstrap failed, trying legacy API..."
        launchctl load -w "$PLIST_FILE"
    fi
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --status to check status"
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --uninstall to remove startup service"
    exit 0
}

do_uninstall() {
    if [ -f "$PLIST_FILE" ]; then
        echo "🗑️  Uninstalling launchd plist..."
        launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || launchctl unload "$PLIST_FILE" 2>/dev/null
        rm -f "$PLIST_FILE"
        cleanup_pid
        echo "✅ Startup service uninstalled"
    else
        echo "⚪ Startup service not installed (plist not found)"
    fi
    exit 0
}

do_upgrade() {
    echo "🔄 Checking for updates..."
    local current latest
    current="$(get_current_version)"
    latest="$(curl -sL --max-time 3 "https://api.github.com/repos/terranc/claude-telegram-bot-bridge/releases/latest" 2>/dev/null | grep -o '"tag_name": *"v[^"]*"' | sed 's/.*"v\([^"]*\)".*/\1/')"

    if [ -z "$latest" ]; then
        echo "❌ Failed to fetch latest version from GitHub"
        exit 1
    fi

    if ! compare_versions "$current" "$latest"; then
        echo "✅ Already up to date (v${current})"
        exit 0
    fi

    echo "📦 Update available: v${current} → v${latest}"

    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo "⚠️  Uncommitted changes detected. Commit or stash them first."
        exit 1
    fi

    echo "⬇️  Pulling latest code..."
    if ! git pull; then
        echo "❌ git pull failed"
        exit 1
    fi

    echo "📦 Reinstalling dependencies..."
    if ! "$VENV_DIR/bin/pip" install -q -r "$REQ_FILE"; then
        echo "❌ Dependency installation failed"
        exit 1
    fi

    current="$(get_current_version)"
    echo "✅ Upgrade complete! Now running v${current}"
    exit 0
}

# ── Dispatch action ──

case "$ACTION" in
    status)    do_status ;;
    stop)      do_stop ;;
    install)   do_install ;;
    uninstall) do_uninstall ;;
    upgrade)   do_upgrade ;;
    run)       ;; # Continue to startup flow below
esac

# Check for updates (skip if running upgrade action)
[ "$ACTION" = "run" ] && check_update

load_optional_env() {
    local env_cli
    env_cli="$(read_env_with_fallback "CLAUDE_CLI_PATH")"
    if [ -n "$env_cli" ] && [ -z "$CLAUDE_CLI_PATH" ]; then
        export CLAUDE_CLI_PATH="$env_cli"
    fi

    local proxy_url
    proxy_url="$(read_env_with_fallback "PROXY_URL")"
    if [ -n "$proxy_url" ]; then
        export http_proxy="$proxy_url"
        export https_proxy="$proxy_url"
        export all_proxy="$proxy_url"
        export no_proxy="localhost,127.0.0.1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12"
        echo "🌐 Proxy configured: $proxy_url"
    fi

    # Auto-detect Git Bash path on Windows when not already set.
    # NOTE: Primary detection is done in Python (__main__.py) using pathlib which
    # handles Windows backslash paths correctly. The bash-side detection here is
    # only a fallback for when .env has an explicit value.
    if [ -z "$CLAUDE_CODE_GIT_BASH_PATH" ]; then
        local git_bash_path
        git_bash_path="$(read_env_with_fallback "CLAUDE_CODE_GIT_BASH_PATH")"
        if [ -n "$git_bash_path" ]; then
            export CLAUDE_CODE_GIT_BASH_PATH="$git_bash_path"
        fi
    fi
}

maybe_setup_claude_cli() {
    if [ -n "$CLAUDE_CLI_PATH" ]; then
        echo "🛠️ Using user-specified CLAUDE_CLI_PATH: $CLAUDE_CLI_PATH"
        return
    fi

    if command -v claude >/dev/null 2>&1; then
        echo "✅ Using system Claude CLI: $(command -v claude)"
    else
        echo "❌ Error: claude command not found. Please install Claude CLI or set CLAUDE_CLI_PATH in .env"
        exit 1
    fi
}
check_env

# ── Token-based global lock (prevents duplicate instances across different project dirs) ──
_raw_token="$(read_env_with_fallback "TELEGRAM_BOT_TOKEN")"
_token_hash="$(printf '%s' "$_raw_token" | md5 -q 2>/dev/null || printf '%s' "$_raw_token" | md5sum | cut -d' ' -f1)"
TOKEN_LOCK_DIR="$HOME/.telegram-bot-locks"
TOKEN_LOCK_FILE="$TOKEN_LOCK_DIR/${_token_hash}.pid"
mkdir -p "$TOKEN_LOCK_DIR"
unset _raw_token _token_hash

is_token_locked() {
    [ -f "$TOKEN_LOCK_FILE" ] || return 1
    local lock_pid
    lock_pid="$(cat "$TOKEN_LOCK_FILE")"
    [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null
}

cleanup_token_lock() {
    rm -f "$TOKEN_LOCK_FILE"
}

# ── Daemon mode handling ──

if [ "$DAEMON_MODE" -eq 1 ]; then
    # Check if an instance is already running
    if is_running; then
        echo "⚠️  Bot is already running in background (PID: $(read_pid)). Use --stop first to restart."
        exit 1
    fi
    if is_token_locked; then
        echo "⚠️  Another instance is already using the same Bot Token (PID: $(cat "$TOKEN_LOCK_FILE")). Stop it first."
        exit 1
    fi

    echo "🌙 Starting in daemon mode..."
    DAEMON_LOG="$LOGS_DIR/bot_stdout.log"

    # Build child process arguments (remove --daemon, add --_daemon_child)
    CHILD_ARGS=("--path" "$PROJECT_ROOT" "--_daemon_child")
    [ -n "$BOT_DEBUG" ] && CHILD_ARGS+=("--debug")

    nohup "$SCRIPT_DIR/start.sh" "${CHILD_ARGS[@]}" >> "$DAEMON_LOG" 2>&1 &
    CHILD_PID=$!
    echo "$CHILD_PID" > "$PID_FILE"
    echo "✅ Bot started in background (PID: $CHILD_PID)"
    echo "📄 Log: $DAEMON_LOG"
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --stop to stop"
    exit 0
fi

# Foreground mode (including --_daemon_child): write PID early and register cleanup
BOT_PID=""
on_exit() {
    [ -n "$BOT_PID" ] && kill "$BOT_PID" 2>/dev/null && wait "$BOT_PID" 2>/dev/null
    cleanup_pid
    cleanup_token_lock
}
trap on_exit EXIT
trap 'exit 143' TERM INT
if is_token_locked; then
    echo "⚠️  Another instance is already using the same Bot Token (PID: $(cat "$TOKEN_LOCK_FILE")). Stop it first."
    exit 1
fi
echo $$ > "$PID_FILE"
echo $$ > "$TOKEN_LOCK_FILE"

load_optional_env
maybe_setup_claude_cli

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3.11+ is required"
    exit 1
fi

# Activate virtual environment
echo "✅ Activating virtual environment"
source "$VENV_DIR/bin/activate"

# Clean up logs older than 14 days (at most once per day)
CLEANUP_MARKER="$BOT_DATA_DIR/.last_cleanup"
if [ -d "$LOGS_DIR" ]; then
    if [ ! -f "$CLEANUP_MARKER" ] || [ -n "$(find "$CLEANUP_MARKER" -mtime +1 2>/dev/null)" ]; then
        echo -e "\033[90m🧹 Cleaning up logs older than 14 days...\033[0m"
        find "$LOGS_DIR" -name "*.log" -mtime +14 -delete 2>/dev/null
        touch "$CLEANUP_MARKER"
    fi
fi

# Start Bot (auto-restart on crash)
MAX_RAPID_CRASHES=5
RAPID_CRASH_WINDOW=60
RESTART_DELAY=3
rapid_crash_count=0

cd "$REPO_ROOT"

# Ensure the package is importable as "telegram_bot"; create a symlink if the
# repo was cloned under a different directory name (e.g. claude-telegram-bot-bridge)
if [ "$(basename "$SCRIPT_DIR")" != "telegram_bot" ] && [ ! -e "$REPO_ROOT/telegram_bot" ]; then
    ln -s "$SCRIPT_DIR" "$REPO_ROOT/telegram_bot"
    echo "🔗 Created telegram_bot -> $(basename "$SCRIPT_DIR") symlink"
fi

while true; do
    echo ""
    echo "🚀 Starting Telegram Bot..."
    echo "================================"

    start_time=$(date +%s)
    "$VENV_DIR/bin/python" -m telegram_bot --path "$PROJECT_ROOT" &
    BOT_PID=$!
    wait $BOT_PID
    exit_code=$?
    BOT_PID=""
    end_time=$(date +%s)

    # Normal exit, no restart
    if [ $exit_code -eq 0 ]; then
        echo "✅ Bot exited normally"
        break
    fi

    # Log crash details
    crash_log="$LOGS_DIR/crash_$(date +%Y%m%d_%H%M%S).log"
    {
        echo "=== Bot crashed ==="
        echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Exit code: $exit_code"
        echo "Uptime: $((end_time - start_time)) seconds"
    } > "$crash_log"
    echo "❌ Bot crashed (exit code: $exit_code), log written to: $crash_log"

    # Rapid crash detection
    if [ $((end_time - start_time)) -lt $RAPID_CRASH_WINDOW ]; then
        rapid_crash_count=$((rapid_crash_count + 1))
        echo "⚠️  Rapid crash ($rapid_crash_count/$MAX_RAPID_CRASHES)"
        if [ $rapid_crash_count -ge $MAX_RAPID_CRASHES ]; then
            echo "🛑 Rapid crash limit reached ($MAX_RAPID_CRASHES times), stopping restart"
            exit 1
        fi
    else
        rapid_crash_count=0
    fi

    echo "🔄 Auto-restarting in ${RESTART_DELAY} seconds..."
    sleep $RESTART_DELAY
done
