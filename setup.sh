#!/bin/bash

# Telegram Skill Bot Installation Script
# One-command setup for new installations

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

# Colors and icons
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Parse arguments
SILENT_MODE=0
TOKEN=""
ALLOWED_USERS=""
PROXY=""

show_help() {
    cat <<EOF
Telegram Skill Bot Installation Script

Usage: $0 [options]

Options:
  -h, --help              Show this help message
  --silent                Silent installation mode (requires --token)
  --token <token>         Telegram Bot Token (required in silent mode)
  --allowed-users <ids>   Comma-separated user IDs (optional)
  --proxy <url>           Proxy URL (optional)

Examples:
  # Interactive installation (recommended)
  ./setup.sh

  # Silent installation
  ./setup.sh --silent --token "123456789:ABCdefGHI..." --allowed-users "123,456"

EOF
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            show_help
            ;;
        --silent)
            SILENT_MODE=1
            shift
            ;;
        --token)
            TOKEN="$2"
            shift 2
            ;;
        --allowed-users)
            ALLOWED_USERS="$2"
            shift 2
            ;;
        --proxy)
            PROXY="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Trap Ctrl+C for cleanup
trap 'echo -e "\n${YELLOW}⚠️  Installation interrupted${NC}"; exit 130' INT

# Welcome message
if [ $SILENT_MODE -eq 0 ]; then
    clear
    echo -e "${CYAN}${BOLD}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║        🤖  Telegram Skill Bot Installation Wizard         ║"
    echo "║                                                            ║"
    echo "║     Turn your Telegram into a remote Claude Code CLI      ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo -e "${BOLD}This wizard will guide you through 4 simple steps:${NC}"
    echo ""
    echo -e "  ${CYAN}1.${NC} Check system requirements (Python, Claude CLI)"
    echo -e "  ${CYAN}2.${NC} Configure your Telegram bot token"
    echo -e "  ${CYAN}3.${NC} Set up Python environment and install dependencies"
    echo -e "  ${CYAN}4.${NC} Complete installation"
    echo ""
    echo -e "${BOLD}Estimated time: 3-5 minutes${NC}"
    echo ""
    read -p "Press Enter to start..."
    echo ""
fi

# ============================================================================
# Environment Checks
# ============================================================================

check_python_version() {
    if [ $SILENT_MODE -eq 0 ]; then
        echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}${BOLD}Step 1 of 3: System Requirements Check${NC}"
        echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
    fi

    echo -n "🔍 Checking Python version... "

    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌${NC}"
        echo ""
        echo -e "${RED}${BOLD}Python 3 not found${NC}"
        echo ""
        echo "Please install Python 3.11 or higher:"
        echo "  • macOS: brew install python@3.11"
        echo "  • Visit: https://www.python.org/downloads/"
        echo ""
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    REQUIRED_VERSION="3.11"

    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        echo -e "${RED}❌${NC}"
        echo ""
        echo -e "${RED}${BOLD}Python $PYTHON_VERSION found, but $REQUIRED_VERSION or higher is required${NC}"
        echo ""
        echo "Please upgrade Python:"
        echo "  • macOS: brew install python@3.11"
        echo "  • Visit: https://www.python.org/downloads/"
        echo ""
        exit 1
    fi

    echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"
}

check_claude_cli() {
    echo -n "🔍 Checking Claude CLI... "

    if ! command -v claude &> /dev/null; then
        echo -e "${RED}❌${NC}"
        echo ""
        echo -e "${RED}${BOLD}Claude CLI not found${NC}"
        echo ""
        echo "Claude CLI is required to run this bot. Please install it first:"
        echo ""
        echo -e "${BOLD}Option 1: Using npm (recommended)${NC}"
        echo "  npm install -g @anthropic-ai/claude-code"
        echo ""
        echo -e "${BOLD}Option 2: Using Homebrew${NC}"
        echo "  brew install anthropics/claude/claude"
        echo ""
        echo "After installation, make sure 'claude' is in your PATH, then run this script again."
        echo ""
        exit 1
    fi

    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    echo -e "${GREEN}✅ $CLAUDE_VERSION${NC}"
}

check_optional_deps() {
    echo -n "🔍 Checking optional dependencies... "

    WARNINGS=()

    if ! command -v git &> /dev/null; then
        WARNINGS+=("Git not found (recommended for version control)")
    fi

    if [ ${#WARNINGS[@]} -eq 0 ]; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️${NC}"
        for warning in "${WARNINGS[@]}"; do
            echo -e "  ${YELLOW}⚠️  $warning${NC}"
        done
    fi

    echo ""
    if [ $SILENT_MODE -eq 0 ]; then
        echo -e "${GREEN}${BOLD}✓ All required dependencies are installed!${NC}"
        echo ""
        read -p "Press Enter to continue..."
        echo ""
    fi
}

# ============================================================================
# Validation Functions
# ============================================================================

validate_token_format() {
    local token="$1"
    # Telegram Bot Token format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
    if [[ "$token" =~ ^[0-9]{8,10}:[A-Za-z0-9_-]{35}$ ]]; then
        return 0
    else
        return 1
    fi
}

validate_user_ids() {
    local ids="$1"
    # Empty is valid (allow all users)
    if [ -z "$ids" ]; then
        return 0
    fi
    # Check comma-separated numbers
    if [[ "$ids" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        return 0
    else
        return 1
    fi
}

validate_proxy_url() {
    local url="$1"
    # Empty is valid (no proxy)
    if [ -z "$url" ]; then
        return 0
    fi
    # Basic URL format check
    if [[ "$url" =~ ^https?://[^[:space:]]+$ ]]; then
        return 0
    else
        return 1
    fi
}

# ============================================================================
# Configuration Functions
# ============================================================================

write_env_file() {
    local token="$1"
    local allowed_users="$2"
    local proxy="$3"

    # Backup existing .env if it exists
    if [ -f "$ENV_FILE" ]; then
        BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$BACKUP_FILE"
        if [ $SILENT_MODE -eq 0 ]; then
            echo -e "${BLUE}📦 Backed up existing .env to $(basename "$BACKUP_FILE")${NC}"
        fi
    fi

    # Copy from .env.example if it doesn't exist
    if [ ! -f "$ENV_FILE" ] && [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    fi

    # Write configuration
    {
        echo "# Telegram Skill Bot Environment Configuration"
        echo ""
        echo "# Required: Get your bot token from @BotFather (https://t.me/BotFather)"
        echo "# Format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        echo "TELEGRAM_BOT_TOKEN=$token"
        echo ""
        echo "# Optional: Comma-separated list of allowed Telegram user IDs"
        echo "# Leave empty to allow all users"
        echo "# To get your user ID, send /start to @userinfobot"
        if [ -n "$allowed_users" ]; then
            echo "ALLOWED_USER_IDS=$allowed_users"
        else
            echo "# ALLOWED_USER_IDS=123456789,987654321"
        fi
        echo ""
        echo "# Logging and timeout"
        echo "# LOG_LEVEL=INFO"
        echo "# CLAUDE_PROCESS_TIMEOUT=600"
        echo ""
        echo "# Streaming configuration"
        echo "DRAFT_UPDATE_MIN_CHARS=30"
        echo "DRAFT_UPDATE_INTERVAL=1.0"
        echo ""
        echo "# Optional: absolute path to Claude CLI (auto-detected by default)"
        echo "# CLAUDE_CLI_PATH=/absolute/path/to/claude"
        echo ""
        echo "# Optional: path to Claude Code settings.json (defaults to ~/.claude/settings.json)"
        echo "# CLAUDE_SETTINGS_PATH=/absolute/path/to/settings.json"
        echo ""
        echo "# Network proxy (optional): start.sh will auto-configure http_proxy/https_proxy/all_proxy"
        if [ -n "$proxy" ]; then
            echo "PROXY_URL=$proxy"
        else
            echo "# PROXY_URL=http://127.0.0.1:7890"
        fi
    } > "$ENV_FILE"

    if [ $SILENT_MODE -eq 0 ]; then
        echo -e "${GREEN}✅ Configuration saved to .env${NC}"
    fi
}

interactive_config() {
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}Step 2 of 3: Bot Configuration${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Check if .env already exists
    if [ -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}⚠️  Configuration file already exists${NC}"
        echo ""

        # Load existing .env and check for required variables
        set +e  # Temporarily disable exit on error
        source "$ENV_FILE" 2>/dev/null
        set -e

        if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ "$TELEGRAM_BOT_TOKEN" != "your_bot_token_here" ]; then
            # Valid token found
            echo -e "${GREEN}✓ Found existing configuration:${NC}"
            echo ""
            echo "   Token: ${TELEGRAM_BOT_TOKEN:0:10}...${TELEGRAM_BOT_TOKEN: -5}"
            [ -n "$ALLOWED_USER_IDS" ] && echo "   Allowed users: $ALLOWED_USER_IDS"
            [ -n "$PROXY_URL" ] && echo "   Proxy: $PROXY_URL"
            echo ""

            read -p "Keep this configuration? (Y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Nn]$ ]]; then
                # User wants to reconfigure
                echo ""
            else
                # Use existing config, skip to completion
                echo ""
                echo -e "${GREEN}${BOLD}✓ Using existing configuration${NC}"
                echo ""
                read -p "Press Enter to continue..."
                echo ""
                return 0
            fi
        else
            # No valid token found
            echo -e "${YELLOW}⚠️  No valid token found in existing configuration${NC}"
            echo ""
            read -p "Create new configuration? (Y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Nn]$ ]]; then
                echo ""
                echo -e "${YELLOW}Installation cancelled${NC}"
                exit 0
            fi
            echo ""
        fi
    fi

    # Get Telegram Bot Token
    echo -e "${BOLD}📱 Telegram Bot Token (Required)${NC}"
    echo ""
    echo "To get your bot token:"
    echo -e "  1. Open Telegram and search for ${BOLD}@BotFather${NC}"
    echo -e "  2. Send the command: ${BOLD}/newbot${NC}"
    echo "  3. Follow the instructions to create your bot"
    echo "  4. Copy the token (format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)"
    echo ""

    while true; do
        read -e -p "Enter your bot token: " TOKEN

        if [ -z "$TOKEN" ]; then
            echo -e "${RED}❌ Token cannot be empty${NC}"
            echo ""
            continue
        fi

        if validate_token_format "$TOKEN"; then
            echo -e "${GREEN}✅ Token format is valid${NC}"
            echo ""
            break
        else
            echo -e "${RED}❌ Invalid token format${NC}"
            echo "   Expected format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
            echo ""
        fi
    done

    # Get allowed user IDs (optional)
    echo -e "${BOLD}👥 User Whitelist (Optional)${NC}"
    echo ""
    echo "You can restrict bot access to specific Telegram users."
    echo -e "Leave empty to allow ${BOLD}all users${NC} (not recommended for public bots)."
    echo ""
    echo "To get your Telegram user ID:"
    echo -e "  • Open Telegram and search for ${BOLD}@userinfobot${NC}"
    echo -e "  • Send ${BOLD}/start${NC} to get your user ID"
    echo ""

    while true; do
        read -e -p "Enter user IDs (comma-separated, or press Enter to skip): " ALLOWED_USERS

        if validate_user_ids "$ALLOWED_USERS"; then
            if [ -n "$ALLOWED_USERS" ]; then
                echo -e "${GREEN}✅ Whitelist enabled for: $ALLOWED_USERS${NC}"
            else
                echo -e "${BLUE}ℹ️  All users allowed (no whitelist)${NC}"
            fi
            echo ""
            break
        else
            echo -e "${RED}❌ Invalid format${NC}"
            echo "   Expected format: 123456789,987654321"
            echo ""
        fi
    done

    # Get proxy URL (optional)
    echo -e "${BOLD}🌐 Network Proxy (Optional)${NC}"
    echo ""
    echo "If you need to use a proxy to access Telegram or Claude API, enter it here."
    echo "Leave empty if no proxy is needed."
    echo ""

    while true; do
        read -e -p "Enter proxy URL (or press Enter to skip): " PROXY

        if validate_proxy_url "$PROXY"; then
            if [ -n "$PROXY" ]; then
                echo -e "${GREEN}✅ Proxy configured: $PROXY${NC}"
            else
                echo -e "${BLUE}ℹ️  No proxy configured${NC}"
            fi
            echo ""
            break
        else
            echo -e "${RED}❌ Invalid URL format${NC}"
            echo "   Expected format: http://127.0.0.1:7890"
            echo ""
        fi
    done

    write_env_file "$TOKEN" "$ALLOWED_USERS" "$PROXY"

    echo -e "${GREEN}${BOLD}✓ Configuration saved successfully!${NC}"
    echo ""
    read -p "Press Enter to continue..."
    echo ""
}

# ============================================================================
# Main Installation Flow
# ============================================================================

# Step 1: Environment checks
check_python_version
check_claude_cli
check_optional_deps

# Step 2: Configuration
if [ $SILENT_MODE -eq 1 ]; then
    if [ -z "$TOKEN" ]; then
        echo -e "${RED}❌ --token is required in silent mode${NC}"
        exit 1
    fi

    if ! validate_token_format "$TOKEN"; then
        echo -e "${RED}❌ Invalid token format${NC}"
        exit 1
    fi

    if ! validate_user_ids "$ALLOWED_USERS"; then
        echo -e "${RED}❌ Invalid user IDs format${NC}"
        exit 1
    fi

    if ! validate_proxy_url "$PROXY"; then
        echo -e "${RED}❌ Invalid proxy URL format${NC}"
        exit 1
    fi

    write_env_file "$TOKEN" "$ALLOWED_USERS" "$PROXY"
    echo -e "${GREEN}✅ Silent installation complete${NC}"
else
    interactive_config
fi

# Step 3: Setup Python environment
if [ $SILENT_MODE -eq 0 ]; then
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}Step 3 of 4: Python Environment Setup${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
fi

VENV_DIR="$SCRIPT_DIR/venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

# Create virtual environment
if [ -d "$VENV_DIR" ]; then
    echo "📦 Virtual environment already exists"
else
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Install dependencies
echo "📦 Installing Python dependencies (this may take a minute)..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$REQ_FILE"

# Save hash for future checks
REQ_HASH_FILE="$VENV_DIR/.req_hash"
REQ_HASH="$(md5 -q "$REQ_FILE" 2>/dev/null || md5sum "$REQ_FILE" | cut -d' ' -f1)"
echo "$REQ_HASH" > "$REQ_HASH_FILE"

echo -e "${GREEN}✅ All Python dependencies installed${NC}"
echo ""

if [ $SILENT_MODE -eq 0 ]; then
    read -p "Press Enter to continue..."
    echo ""
fi

# Step 4: Completion message
if [ $SILENT_MODE -eq 0 ]; then
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}Step 4 of 4: Installation Complete!${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${GREEN}${BOLD}✓ Installation successful!${NC}"
    echo ""
    echo -e "${BOLD}Usage:${NC}"
    echo ""
    echo -e "  ${BLUE}./start.sh --path <project_path> [options]${NC}"
    echo ""
    echo -e "${BOLD}Common Options:${NC}"
    echo "  -h, --help          Show full help message"
    echo "  -d, --daemon        Run in background"
    echo "  --debug             Enable debug logging"
    echo "  --status            Check if bot is running"
    echo "  --stop              Stop the bot"
    echo "  --install           Install as macOS startup service"
    echo "  --uninstall         Remove startup service"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo -e "  ${BLUE}./start.sh --help${NC}                        ${GREEN}# Show full help${NC}"
    echo -e "  ${BLUE}./start.sh --path ~/my-project${NC}          ${GREEN}# Start in foreground${NC}"
    echo -e "  ${BLUE}./start.sh --path ~/my-project -d${NC}       ${GREEN}# Start as daemon${NC}"
    echo -e "  ${BLUE}./start.sh --path ~/my-project --debug${NC}  ${GREEN}# Debug mode${NC}"
    echo ""
    echo -e "${BOLD}Next steps:${NC}"
    echo "  1. Start the bot with a project directory"
    echo -e "  2. Open Telegram and send ${BOLD}/start${NC} to your bot"
    echo ""
    echo -e "For more information, see ${BOLD}README.md${NC}"
    echo ""
    echo -e "${GREEN}${BOLD}Happy coding! 🚀${NC}"
    echo ""
fi
