import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from telegram_bot.utils.config import config


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_reason(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(str(value).split())[:500]


class RuntimeHealthReporter:
    SCHEMA_VERSION = 1

    def __init__(self, bot_data_dir: Path):
        self._lock = threading.Lock()
        self._bot_data_dir = bot_data_dir
        self._pid_file = bot_data_dir / "bot.pid"
        self._health_file = bot_data_dir / "health.json"
        self._started_at = _utc_now_iso()
        self._process_mode = "foreground"
        self._token_lock_file = ""
        self._owns_token_lock = False
        self._state: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "updated_at": _utc_now_iso(),
            "process": {
                "pid": os.getpid(),
                "started_at": self._started_at,
                "mode": self._process_mode,
            },
            "service": {
                "state": "starting",
                "reason": "initializing bot",
            },
            "telegram": {
                "state": "degraded",
                "last_ok_at": None,
                "last_error_at": None,
                "last_error": "",
                "consecutive_failures": 0,
            },
            "claude": {
                "state": "degraded",
                "last_ok_at": None,
                "last_error_at": None,
                "last_error": "",
            },
        }

    @property
    def health_file(self) -> Path:
        return self._health_file

    @property
    def pid_file(self) -> Path:
        return self._pid_file

    def _ensure_runtime_dir(self) -> None:
        self._bot_data_dir.mkdir(parents=True, exist_ok=True)

    def _write_pid_locked(self) -> None:
        self._ensure_runtime_dir()
        self._pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

    def _write_health_locked(self) -> None:
        self._ensure_runtime_dir()
        self._state["updated_at"] = _utc_now_iso()
        temp_path = self._health_file.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(self._state, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, self._health_file)

    def _refresh_runtime_context_locked(self) -> None:
        self._process_mode = os.environ.get("BOT_PROCESS_MODE", "foreground")
        self._token_lock_file = os.environ.get("BOT_TOKEN_LOCK_FILE", "")
        self._owns_token_lock = os.environ.get("BOT_OWNS_TOKEN_LOCK") == "1"
        self._state["process"] = {
            "pid": os.getpid(),
            "started_at": self._started_at,
            "mode": self._process_mode,
        }

    def _recompute_service_locked(self) -> None:
        telegram_state = self._state["telegram"]["state"]
        claude_state = self._state["claude"]["state"]
        if telegram_state == "healthy" and claude_state == "healthy":
            self._state["service"]["state"] = "available"
            self._state["service"]["reason"] = ""
            return

        reasons: list[str] = []
        if telegram_state != "healthy":
            detail = self._state["telegram"].get("last_error") or "telegram unavailable"
            reasons.append(f"Telegram: {detail}")
        if claude_state != "healthy":
            detail = self._state["claude"].get("last_error") or "claude unavailable"
            reasons.append(f"Claude: {detail}")

        self._state["service"]["state"] = "degraded"
        self._state["service"]["reason"] = "; ".join(reasons)

    def initialize_process(self) -> None:
        with self._lock:
            self._refresh_runtime_context_locked()
            self._write_pid_locked()
            self._write_health_locked()

    def mark_starting(self, reason: str) -> None:
        with self._lock:
            self._state["service"]["state"] = "starting"
            self._state["service"]["reason"] = _normalize_reason(reason)
            self._write_health_locked()

    def mark_unavailable(self, reason: str) -> None:
        with self._lock:
            # In launchd mode, process exit means restart window, not final unavailable
            if self._process_mode == "launchd":
                self._state["service"]["state"] = "starting"
                self._state["service"]["reason"] = f"waiting for launchd restart ({_normalize_reason(reason)})"
            else:
                self._state["service"]["state"] = "unavailable"
                self._state["service"]["reason"] = _normalize_reason(reason)
            self._write_health_locked()

    def record_telegram_ok(self) -> None:
        with self._lock:
            self._state["telegram"]["state"] = "healthy"
            self._state["telegram"]["last_ok_at"] = _utc_now_iso()
            self._state["telegram"]["consecutive_failures"] = 0
            self._recompute_service_locked()
            self._write_health_locked()

    def record_telegram_error(
        self, error: str, consecutive_failures: Optional[int] = None
    ) -> None:
        with self._lock:
            self._state["telegram"]["state"] = "degraded"
            self._state["telegram"]["last_error_at"] = _utc_now_iso()
            self._state["telegram"]["last_error"] = _normalize_reason(error)
            if consecutive_failures is None:
                consecutive_failures = (
                    int(self._state["telegram"]["consecutive_failures"]) + 1
                )
            self._state["telegram"]["consecutive_failures"] = consecutive_failures
            self._recompute_service_locked()
            self._write_health_locked()

    def record_claude_ok(self) -> None:
        with self._lock:
            self._state["claude"]["state"] = "healthy"
            self._state["claude"]["last_ok_at"] = _utc_now_iso()
            self._recompute_service_locked()
            self._write_health_locked()

    def record_claude_error(self, error: str) -> None:
        with self._lock:
            self._state["claude"]["state"] = "degraded"
            self._state["claude"]["last_error_at"] = _utc_now_iso()
            self._state["claude"]["last_error"] = _normalize_reason(error)
            self._recompute_service_locked()
            self._write_health_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)

    def cleanup_runtime_files(self) -> None:
        with self._lock:
            self._refresh_runtime_context_locked()
            try:
                self._pid_file.unlink()
            except FileNotFoundError:
                pass
            if self._owns_token_lock and self._token_lock_file:
                try:
                    Path(self._token_lock_file).unlink()
                except FileNotFoundError:
                    pass


health_reporter = RuntimeHealthReporter(config.bot_data_dir)
