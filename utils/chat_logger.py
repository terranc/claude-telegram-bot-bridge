"""Per-session chat logger - writes conversation logs under PROJECT_ROOT/.telegram_bot/logs/."""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from telegram_bot.utils.config import config

LOGS_DIR = config.logs_dir

logger = logging.getLogger(__name__)


def _ensure_logs_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _log_file(user_id: int, session_id: str | None) -> Path:
    _ensure_logs_dir()
    date_str = datetime.now().strftime("%Y%m%d")
    sid = session_id or "default"
    return LOGS_DIR / f"{user_id}_{sid}_{date_str}.log"


def log_chat(
    user_id: int,
    session_id: str | None,
    role: str,
    content: str,
    *,
    model: str | None = None,
    success: bool = True,
):
    """Append a chat entry to the session log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = _log_file(user_id, session_id)

    header = f"[{ts}] [{role}]"
    if model:
        header += f" [model={model}]"
    if not success:
        header += " [FAILED]"

    entry = f"{header}\n{content}\n"

    # Debug mode: also print to terminal
    if os.environ.get("BOT_DEBUG"):
        print(f"\n{'=' * 60}\n{entry}{'=' * 60}", file=sys.stderr, flush=True)

    # Session log file: debug mode only
    if os.environ.get("BOT_DEBUG"):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to write chat log: {e}")


def log_debug(user_id: int, role: str, content: str):
    """Print interaction to terminal in debug mode only (no file)."""
    if not os.environ.get("BOT_DEBUG"):
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"\n{'=' * 60}\n[{ts}] [{role}] [user={user_id}]\n{content}\n{'=' * 60}",
        file=sys.stderr,
        flush=True,
    )
