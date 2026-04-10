#!/bin/bash

# Telegram Skill Bot startup script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
ENV_FILE="$SCRIPT_DIR/.env"
REQ_HASH_FILE="$VENV_DIR/.req_hash"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Version check cache
CACHE_DIR="$HOME/.telegram-bot-cache"
CACHE_FILE="$CACHE_DIR/update_check"

get_requirements_hash() {
    md5 -q "$REQ_FILE" 2>/dev/null || md5sum "$REQ_FILE" | cut -d' ' -f1
}

ensure_venv() {
    if [ -d "$VENV_DIR" ]; then
        return 0
    fi

    echo "📦 Virtual environment not found, creating..."
    if ! python3 -m venv "$VENV_DIR"; then
        echo "❌ Failed to create virtual environment: $VENV_DIR"
        exit 1
    fi
}

sync_dependencies() {
    local force_install="$1"
    local current_hash saved_hash

    current_hash="$(get_requirements_hash)"
    [ -f "$REQ_HASH_FILE" ] && saved_hash="$(cat "$REQ_HASH_FILE")"

    if [ "$force_install" = "1" ] || [ -z "$saved_hash" ] || [ "$saved_hash" != "$current_hash" ]; then
        echo "📦 Installing Python dependencies..."
        if ! "$VENV_DIR/bin/pip" install -q --upgrade pip; then
            echo "❌ Failed to upgrade pip"
            exit 1
        fi
        if ! "$VENV_DIR/bin/pip" install -q -r "$REQ_FILE"; then
            echo "❌ Dependency installation failed"
            exit 1
        fi
        echo "$current_hash" > "$REQ_HASH_FILE"
        echo "✅ Dependencies are up to date"
    else
        echo -e "\033[90m✓ Dependencies unchanged (requirements hash match)\033[0m"
    fi
}

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

# Basic repository sanity check
if [ ! -f "$REQ_FILE" ]; then
    echo ""
    echo -e "${RED}❌ requirements.txt not found: $REQ_FILE${NC}"
    echo "Please run this script from the project repository."
    echo ""
    exit 1
fi

ACTION="run"
DAEMON_MODE=0  # Default to foreground mode
PROCESS_MODE="foreground"
RUN_AS_DAEMON_SUPERVISOR=0
INTERNAL_RUN=0
WATCHDOG_INTERVAL=60

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
        --_daemon_supervisor)
            PROCESS_MODE="daemon"
            RUN_AS_DAEMON_SUPERVISOR=1
            INTERNAL_RUN=1
            DAEMON_MODE=0
            shift
            ;;
        --_launchd_child)
            PROCESS_MODE="launchd"
            INTERNAL_RUN=1
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
  --upgrade           Update bot to latest version and reinstall dependencies
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
SUPERVISOR_PID_FILE="$BOT_DATA_DIR/supervisor.pid"
HEALTH_FILE="$BOT_DATA_DIR/health.json"
HEALTH_STALE_SECONDS=$((WATCHDOG_INTERVAL * 2 + 30))
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

read_supervisor_pid() {
    [ -f "$SUPERVISOR_PID_FILE" ] && cat "$SUPERVISOR_PID_FILE"
}

is_running() {
    local pid
    pid="$(read_pid)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

is_supervisor_running() {
    local pid
    pid="$(read_supervisor_pid)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cleanup_pid() {
    rm -f "$PID_FILE" 2>/dev/null || true
}

cleanup_supervisor_pid() {
    rm -f "$SUPERVISOR_PID_FILE" 2>/dev/null || true
}

print_component_status() {
    local component="$1"
    local state="$2"
    local detail="$3"
    printf '   %s: %s' "$component" "$state"
    if [ -n "$detail" ]; then
        printf ' (%s)' "$detail"
    fi
    printf '\n'
}

render_status_from_health() {
    python3 - "$1" "$2" "$3" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

health_path = Path(sys.argv[1])
pid = sys.argv[2]
stale_seconds = int(sys.argv[3])


def parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_age(seconds: int) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def line(component: str, state: str, detail: str = "") -> str:
    if detail:
        return f"   {component}: {state} ({detail})"
    return f"   {component}: {state}"


if not health_path.exists():
    print("🟡 Bot status: degraded")
    print(line("Process", "alive", f"PID: {pid}"))
    print(line("Service", "degraded", "health missing"))
    print(line("Telegram", "degraded", "health missing"))
    print(line("Claude", "degraded", "health missing"))
    raise SystemExit(0)

try:
    data = json.loads(health_path.read_text(encoding="utf-8"))
except Exception as exc:
    print("🟡 Bot status: degraded")
    print(line("Process", "alive", f"PID: {pid}"))
    print(line("Service", "degraded", f"invalid health file: {exc}"))
    print(line("Telegram", "degraded", "health unreadable"))
    print(line("Claude", "degraded", "health unreadable"))
    raise SystemExit(0)

updated_at = parse_iso(data.get("updated_at"))
age_seconds = None
if updated_at is not None:
    age_seconds = max(0, int((datetime.now(timezone.utc) - updated_at).total_seconds()))

service = data.get("service") or {}
telegram = data.get("telegram") or {}
claude = data.get("claude") or {}

if age_seconds is None or age_seconds > stale_seconds:
    detail = "health stale"
    if age_seconds is not None:
        detail = f"health stale: last update {format_age(age_seconds)} ago"
    print("🟡 Bot status: degraded")
    print(line("Process", "alive", f"PID: {pid}"))
    print(line("Service", "degraded", detail))
    print(line("Telegram", "degraded", detail))
    print(line("Claude", "degraded", detail))
    raise SystemExit(0)

service_state = service.get("state") or "degraded"
service_reason = service.get("reason") or ""
telegram_state = telegram.get("state") or "degraded"
telegram_reason = telegram.get("last_error") or ""
claude_state = claude.get("state") or "degraded"
claude_reason = claude.get("last_error") or ""

icons = {
    "available": "🟢",
    "starting": "🟡",
    "degraded": "🟡",
    "unavailable": "🔴",
}
print(f"{icons.get(service_state, '🟡')} Bot status: {service_state}")
print(line("Process", "alive", f"PID: {pid}"))
print(line("Service", service_state, service_reason))
print(line("Telegram", telegram_state, telegram_reason if telegram_state != "healthy" else ""))
print(line("Claude", claude_state, claude_reason if claude_state != "healthy" else ""))
PY
}

# ── Action handlers ──

do_status() {
    local pid
    pid="$(read_pid)"
    if [ -z "$pid" ]; then
        echo "🔴 Bot status: unavailable"
        print_component_status "Process" "dead" "no PID file"
        print_component_status "Service" "unavailable" "process not running"
        print_component_status "Telegram" "unavailable" "process not running"
        print_component_status "Claude" "unavailable" "process not running"
        exit 0
    fi
    if kill -0 "$pid" 2>/dev/null; then
        render_status_from_health "$HEALTH_FILE" "$pid" "$HEALTH_STALE_SECONDS"
    else
        echo "🔴 Bot status: unavailable"
        print_component_status "Process" "dead" "stale PID: $pid"
        print_component_status "Service" "unavailable" "process not running"
        print_component_status "Telegram" "unavailable" "process not running"
        print_component_status "Claude" "unavailable" "process not running"
        cleanup_pid
    fi
    exit 0
}

do_stop() {
    local pid supervisor_pid
    local stopped_service=0
    supervisor_pid="$(read_supervisor_pid)"
    pid="$(read_pid)"

    if [ -f "$PLIST_FILE" ]; then
        echo "🛑 Stopping launchd service: $PLIST_LABEL..."
        launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || launchctl unload "$PLIST_FILE" 2>/dev/null || true
        stopped_service=1
        sleep 1
    fi

    if [ -n "$supervisor_pid" ] && kill -0 "$supervisor_pid" 2>/dev/null; then
        echo "🛑 Stopping daemon supervisor (PID: $supervisor_pid)..."
        kill "$supervisor_pid"
        for i in $(seq 1 10); do
            kill -0 "$supervisor_pid" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$supervisor_pid" 2>/dev/null; then
            echo "⚠️  Supervisor not responding to SIGTERM, sending SIGKILL..."
            kill -9 "$supervisor_pid" 2>/dev/null
            sleep 0.5
        fi
    fi

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "🛑 Stopping bot process (PID: $pid)..."
        kill "$pid"
        for i in $(seq 1 10); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "⚠️  Bot process not responding to SIGTERM, sending SIGKILL..."
            kill -9 "$pid" 2>/dev/null
            sleep 0.5
        fi
    fi

    cleanup_pid
    cleanup_supervisor_pid
    cleanup_token_lock_if_safe "$supervisor_pid" "$pid"
    if [ "$stopped_service" -eq 1 ] || [ -n "$supervisor_pid" ] || [ -n "$pid" ]; then
        echo "✅ Bot stopped"
    else
        echo "⚪ Bot is not running"
    fi
    exit 0
}

read_env_value() {
    local key="$1"
    local file="${2:-$ENV_FILE}"
    [ -f "$file" ] || return 0
    local line
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" | tail -n1)"
    [ -n "$line" ] || return 0
    local value="${line#*=}"
    value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    # Strip trailing inline comment (common pattern: KEY=value # comment)
    value="${value%% \#*}"
    value="$(printf '%s' "$value" | sed -E 's/[[:space:]]+$//')"
    echo "$value"
}

upsert_env_value() {
    local key="$1"
    local value="$2"
    local file="$3"
    local tmp_file

    tmp_file="$(mktemp "${file}.tmp.XXXXXX")" || return 1

    if awk -v key="$key" -v value="$value" '
        BEGIN { updated = 0 }
        $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
            if (!updated) {
                print key "=" value
                updated = 1
            }
            next
        }
        { print }
        END {
            if (!updated) {
                print key "=" value
            }
        }
    ' "$file" > "$tmp_file"; then
        mv "$tmp_file" "$file"
        return 0
    fi

    rm -f "$tmp_file"
    return 1
}

_is_valid_token() {
    [ -n "$1" ] && [ "$1" != "your_bot_token_here" ]
}

# Read a config value from project .env, falling back to bot source dir .env
# NOTE: For comprehensive env merging at startup, merge_env_files() is preferred
read_env_with_fallback() {
    local key="$1"
    local value
    value="$(read_env_value "$key")"
    if [ -z "$value" ]; then
        value="$(read_env_value "$key" "$SCRIPT_DIR/.env")"
    fi
    echo "$value"
}

# Merge project .env with global fallback .env
# Project .env values take precedence over global .env
merge_env_files() {
    local project_env="$ENV_FILE"
    local global_env="$SCRIPT_DIR/.env"

    if [ ! -f "$global_env" ]; then
        return
    fi

    # Read all keys from global .env
    local keys key value project_value
    keys=$(grep -E "^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=" "$global_env" 2>/dev/null | \
           sed -E 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*).*/\2/' | sort -u)

    for key in $keys; do
        # Check if key exists in project .env
        project_value="$(read_env_value "$key" "$project_env")"
        if [ -z "$project_value" ]; then
            # Not in project .env, get from global and export
            value="$(read_env_value "$key" "$global_env")"
            if [ -n "$value" ]; then
                export "$key=$value"
            fi
        fi
    done
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
        if ! upsert_env_value "TELEGRAM_BOT_TOKEN" "$INPUT_TOKEN" "$ENV_FILE"; then
            echo "❌ Failed to save token to $ENV_FILE"
            exit 1
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
    init_token_lock
    # Refuse if an instance is already running (any startup mode)
    if is_running || is_supervisor_running; then
        echo "⚠️  Bot is already running. Use --stop first."
        exit 1
    fi
    if is_token_locked; then
        echo "⚠️  Another instance is already using the same Bot Token (PID: $(cat "$TOKEN_LOCK_FILE")). Stop it first."
        exit 1
    fi
    echo "📝 Generating launchd plist: $PLIST_FILE"
    mkdir -p "$(dirname "$PLIST_FILE")"
    # Ensure .local/bin is in PATH for claude CLI
    LAUNCHD_PATH="${PATH}"
    if [ -d "$HOME/.local/bin" ] && ! echo "$LAUNCHD_PATH" | grep -q "$HOME/.local/bin"; then
        LAUNCHD_PATH="$HOME/.local/bin:$LAUNCHD_PATH"
    fi

    # Read proxy config for launchd environment
    local proxy_url
    proxy_url="$(read_env_with_fallback "PROXY_URL")"

    # Build environment variables section
    local env_vars
    env_vars="    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${LAUNCHD_PATH}</string>
        <key>HOME</key>
        <string>${HOME}</string>"
    if [ -n "$proxy_url" ]; then
        env_vars="$env_vars
        <key>http_proxy</key>
        <string>${proxy_url}</string>
        <key>https_proxy</key>
        <string>${proxy_url}</string>
        <key>all_proxy</key>
        <string>${proxy_url}</string>
        <key>no_proxy</key>
        <string>localhost,127.0.0.1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12</string>"
    fi
    env_vars="$env_vars
    </dict>"

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
        <string>${SCRIPT_DIR}/start.sh</string>
        <string>--path</string>
        <string>${PROJECT_ROOT}</string>
        <string>--_launchd_child</string>
    </array>
${env_vars}
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
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
    # Wait for process to start (up to 5 seconds)
    echo "⏳ Waiting for bot to initialize..."
    for i in $(seq 1 10); do
        sleep 0.5
        if [ -f "$PID_FILE" ]; then
            pid="$(cat "$PID_FILE")"
            if kill -0 "$pid" 2>/dev/null; then
                echo "✅ Bot process started (PID: $pid)"
                break
            fi
        fi
    done
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --status to check status"
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --uninstall to remove startup service"
    exit 0
}

do_uninstall() {
    if [ -f "$PLIST_FILE" ]; then
        echo "🗑️  Uninstalling launchd plist..."
        # Stop the service first
        launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || launchctl unload "$PLIST_FILE" 2>/dev/null || true
        sleep 1
        # Stop any remaining processes
        local pid supervisor_pid
        supervisor_pid="$(read_supervisor_pid)"
        pid="$(read_pid)"
        if [ -n "$supervisor_pid" ] && kill -0 "$supervisor_pid" 2>/dev/null; then
            echo "🛑 Stopping daemon supervisor (PID: $supervisor_pid)..."
            kill "$supervisor_pid" 2>/dev/null || true
        fi
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "🛑 Stopping bot process (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
        fi
        cleanup_pid
        cleanup_supervisor_pid
        cleanup_token_lock_if_safe "$supervisor_pid" "$pid"
        # Remove the plist file
        rm -f "$PLIST_FILE"
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
        echo "✅ Already up to date (v${current}), syncing dependencies..."
        ensure_venv
        sync_dependencies 1
        echo "✅ Dependency sync complete"
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

    ensure_venv
    sync_dependencies 1

    current="$(get_current_version)"
    echo "✅ Upgrade complete! Now running v${current}"
    exit 0
}

# ── Token-based global lock (prevents duplicate instances across different project dirs) ──
TOKEN_LOCK_FILE=""

init_token_lock() {
    if [ -n "$TOKEN_LOCK_FILE" ]; then
        return 0
    fi
    local raw_token token_hash
    raw_token="$(read_env_with_fallback "TELEGRAM_BOT_TOKEN")"
    token_hash="$(printf '%s' "$raw_token" | md5 -q 2>/dev/null || printf '%s' "$raw_token" | md5sum | cut -d' ' -f1)"
    TOKEN_LOCK_DIR="$HOME/.telegram-bot-locks"
    TOKEN_LOCK_FILE="$TOKEN_LOCK_DIR/${token_hash}.pid"
    mkdir -p "$TOKEN_LOCK_DIR"
}

is_token_locked() {
    init_token_lock
    [ -f "$TOKEN_LOCK_FILE" ] || return 1
    local lock_pid
    lock_pid="$(cat "$TOKEN_LOCK_FILE")"
    [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null
}

write_token_lock() {
    init_token_lock
    printf '%s\n' "$1" > "$TOKEN_LOCK_FILE"
}

cleanup_token_lock() {
    if [ -z "$TOKEN_LOCK_FILE" ]; then
        init_token_lock
    fi
    [ -n "$TOKEN_LOCK_FILE" ] && rm -f "$TOKEN_LOCK_FILE"
}

cleanup_token_lock_if_safe() {
    local expected_pid_1="$1"
    local expected_pid_2="$2"
    local lock_pid

    if [ -z "$TOKEN_LOCK_FILE" ]; then
        init_token_lock
    fi
    [ -n "$TOKEN_LOCK_FILE" ] || return 0
    [ -f "$TOKEN_LOCK_FILE" ] || return 0

    lock_pid="$(cat "$TOKEN_LOCK_FILE" 2>/dev/null)"
    if [ -z "$lock_pid" ]; then
        cleanup_token_lock
        return 0
    fi

    if [ -n "$expected_pid_1" ] && [ "$lock_pid" = "$expected_pid_1" ]; then
        cleanup_token_lock
        return 0
    fi
    if [ -n "$expected_pid_2" ] && [ "$lock_pid" = "$expected_pid_2" ]; then
        cleanup_token_lock
        return 0
    fi
    if ! kill -0 "$lock_pid" 2>/dev/null; then
        cleanup_token_lock
    fi
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
[ "$ACTION" = "run" ] && [ "$INTERNAL_RUN" -eq 0 ] && check_update

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

prepare_runtime() {
    load_optional_env
    maybe_setup_claude_cli

    if ! command -v python3 >/dev/null 2>&1; then
        echo "❌ Error: Python 3.11+ is required"
        exit 1
    fi

    ensure_venv
    sync_dependencies 0

    echo "✅ Activating virtual environment"
    . "$VENV_DIR/bin/activate"

    CLEANUP_MARKER="$BOT_DATA_DIR/.last_cleanup"
    if [ -d "$LOGS_DIR" ]; then
        if [ ! -f "$CLEANUP_MARKER" ] || [ -n "$(find "$CLEANUP_MARKER" -mtime +1 2>/dev/null)" ]; then
            echo -e "\033[90m🧹 Cleaning up logs older than 14 days...\033[0m"
            find "$LOGS_DIR" -name "*.log" -mtime +14 -delete 2>/dev/null
            touch "$CLEANUP_MARKER"
        fi
    fi

    cd "$REPO_ROOT"
}

exec_bot_once() {
    export BOT_PROCESS_MODE="$PROCESS_MODE"
    export BOT_TOKEN_LOCK_FILE="$TOKEN_LOCK_FILE"
    export BOT_OWNS_TOKEN_LOCK="1"
    write_token_lock "$$"

    echo ""
    echo "🚀 Starting Telegram Bot..."
    echo "================================"

    if [ -n "$BOT_DEBUG" ]; then
        exec "$VENV_DIR/bin/python" -m telegram_bot --path "$PROJECT_ROOT" --debug
    fi
    exec "$VENV_DIR/bin/python" -m telegram_bot --path "$PROJECT_ROOT"
}

run_daemon_supervisor() {
    MAX_RAPID_CRASHES=5
    RAPID_CRASH_WINDOW=60
    RESTART_DELAY_BASE=3
    rapid_crash_count=0
    child_pid=""

    daemon_cleanup() {
        if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
            kill "$child_pid" 2>/dev/null || true
            wait "$child_pid" 2>/dev/null || true
        fi
        cleanup_supervisor_pid
        cleanup_token_lock
    }

    trap daemon_cleanup EXIT
    trap 'exit 143' TERM INT

    echo $$ > "$SUPERVISOR_PID_FILE"
    write_token_lock "$$"

    # Debug: log environment variables for daemon supervisor
    echo "DEBUG: http_proxy=$http_proxy" >> "$LOGS_DIR/supervisor.log"
    echo "DEBUG: https_proxy=$https_proxy" >> "$LOGS_DIR/supervisor.log"
    echo "DEBUG: VENV_DIR=$VENV_DIR" >> "$LOGS_DIR/supervisor.log"
    echo "DEBUG: PROJECT_ROOT=$PROJECT_ROOT" >> "$LOGS_DIR/supervisor.log"

    while true; do
        echo ""
        echo "🚀 Starting Telegram Bot..."
        echo "================================"

        start_time=$(date +%s)
        if [ -n "$BOT_DEBUG" ]; then
            BOT_PROCESS_MODE=daemon BOT_TOKEN_LOCK_FILE="$TOKEN_LOCK_FILE" BOT_OWNS_TOKEN_LOCK=0 \
                http_proxy="$http_proxy" https_proxy="$https_proxy" all_proxy="$all_proxy" no_proxy="$no_proxy" \
                "$VENV_DIR/bin/python" -m telegram_bot --path "$PROJECT_ROOT" --debug &
        else
            BOT_PROCESS_MODE=daemon BOT_TOKEN_LOCK_FILE="$TOKEN_LOCK_FILE" BOT_OWNS_TOKEN_LOCK=0 \
                http_proxy="$http_proxy" https_proxy="$https_proxy" all_proxy="$all_proxy" no_proxy="$no_proxy" \
                "$VENV_DIR/bin/python" -m telegram_bot --path "$PROJECT_ROOT" &
        fi
        child_pid=$!
        wait "$child_pid"
        exit_code=$?
        child_pid=""
        end_time=$(date +%s)

        if [ "$exit_code" -eq 0 ]; then
            echo "✅ Bot exited normally"
            break
        fi

        crash_log="$LOGS_DIR/crash_$(date +%Y%m%d_%H%M%S).log"
        {
            echo "=== Bot crashed ==="
            echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Exit code: $exit_code"
            echo "Uptime: $((end_time - start_time)) seconds"
        } > "$crash_log"
        echo "❌ Bot crashed (exit code: $exit_code), log written to: $crash_log"

        if [ $((end_time - start_time)) -lt $RAPID_CRASH_WINDOW ]; then
            rapid_crash_count=$((rapid_crash_count + 1))
            echo "⚠️  Rapid crash ($rapid_crash_count/$MAX_RAPID_CRASHES)"
            if [ "$rapid_crash_count" -ge "$MAX_RAPID_CRASHES" ]; then
                echo "🛑 Rapid crash limit reached ($MAX_RAPID_CRASHES times), stopping restart"
                exit 1
            fi
        else
            rapid_crash_count=0
        fi

        restart_delay=$((RESTART_DELAY_BASE * (rapid_crash_count + 1)))
        if [ "$restart_delay" -gt 30 ]; then
            restart_delay=30
        fi
        echo "🔄 Auto-restarting in ${restart_delay} seconds..."
        sleep "$restart_delay"
    done
}

# Merge env files before check_env so all config is available
merge_env_files

check_env
init_token_lock

if [ "$DAEMON_MODE" -eq 1 ] && [ "$RUN_AS_DAEMON_SUPERVISOR" -eq 0 ]; then
    if is_supervisor_running || is_running; then
        echo "⚠️  Bot is already running. Use --stop first to restart."
        exit 1
    fi
    if is_token_locked; then
        echo "⚠️  Another instance is already using the same Bot Token (PID: $(cat "$TOKEN_LOCK_FILE")). Stop it first."
        exit 1
    fi

    echo "🌙 Starting in daemon mode..."
    DAEMON_LOG="$LOGS_DIR/supervisor.log"
    SUPERVISOR_ARGS=("--path" "$PROJECT_ROOT" "--_daemon_supervisor")
    [ -n "$BOT_DEBUG" ] && SUPERVISOR_ARGS+=("--debug")
    nohup "$SCRIPT_DIR/start.sh" "${SUPERVISOR_ARGS[@]}" >> "$DAEMON_LOG" 2>&1 &
    SUPERVISOR_PID=$!
    echo "✅ Bot started in background (PID: $SUPERVISOR_PID)"
    echo "📄 Log: $DAEMON_LOG"
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --status to check status"
    echo "💡 Use $0 --path \"$PROJECT_ROOT\" --stop to stop"
    exit 0
fi

if [ "$RUN_AS_DAEMON_SUPERVISOR" -eq 1 ]; then
    prepare_runtime
    run_daemon_supervisor
    exit $?
fi

if is_token_locked; then
    echo "⚠️  Another instance is already using the same Bot Token (PID: $(cat "$TOKEN_LOCK_FILE")). Stop it first."
    exit 1
fi

prepare_runtime
exec_bot_once
