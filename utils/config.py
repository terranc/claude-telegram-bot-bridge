import os
import logging
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BOT_PACKAGE_DIR = Path(__file__).resolve().parent.parent

# Project root directory (where the bot operates)
PROJECT_ROOT = Path(os.environ["PROJECT_ROOT"]).resolve()
BOT_DATA_DIR = PROJECT_ROOT / ".telegram_bot"
ENV_FILE_PATH = BOT_DATA_DIR / ".env"  # project config (priority)
BOT_ENV_FILE_PATH = BOT_PACKAGE_DIR / ".env"  # global fallback (e.g. CLAUDE_CLI_PATH)

_PLACEHOLDER_TOKENS = {"your_bot_token_here", ""}

load_dotenv(dotenv_path=ENV_FILE_PATH)  # project .env first (higher priority)
# If project .env has a placeholder token, clear it so bot source .env fallback works
if os.environ.get("TELEGRAM_BOT_TOKEN", "") in _PLACEHOLDER_TOKENS:
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
load_dotenv(
    dotenv_path=BOT_ENV_FILE_PATH
)  # global fallback (won't override already-set vars)

LOGS_DIR = BOT_DATA_DIR / "logs"
SESSION_STORE_PATH = BOT_DATA_DIR / "sessions.json"
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


class Config(BaseSettings):
    """Bot configuration"""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=[str(ENV_FILE_PATH), str(BOT_ENV_FILE_PATH)],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    claude_cli_path: Optional[Path] = Field(
        default=None,
        description="Optional absolute path to Claude CLI binary (defaults to system PATH)",
    )
    claude_settings_path: Path = Field(
        default=CLAUDE_SETTINGS_PATH, description="Path to Claude Code settings.json"
    )

    # Telegram Bot
    telegram_bot_token: str = Field(..., description="Telegram Bot API Token")

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def validate_bot_token(cls, v):
        if not v or v.strip() in _PLACEHOLDER_TOKENS:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not configured. "
                "Set it in the project .env or bot source .env file."
            )
        return v.strip()

    # Runtime data
    bot_data_dir: Path = Field(
        default=BOT_DATA_DIR, description="Runtime data directory"
    )
    logs_dir: Path = Field(default=LOGS_DIR, description="Runtime logs directory")
    session_store_path: Path = Field(
        default=SESSION_STORE_PATH,
        description="Local session JSON storage path",
    )

    # Access Control - comma-separated list of allowed user IDs (if empty, allow all)
    allowed_user_ids: List[int] = Field(
        default_factory=list,
        description="List of allowed Telegram user IDs (empty = allow all)",
    )

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v):
        """Parse allowed_user_ids from string or list"""
        if isinstance(v, str):
            if not v or v.strip() == "":
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v

    # Streaming configuration
    draft_update_min_chars: int = Field(
        default=150,
        description="Minimum characters to accumulate before sending draft update",
    )
    draft_update_interval: float = Field(
        default=1.0, description="Minimum seconds between draft updates"
    )

    # Voice message configuration
    transcription_provider: str = Field(
        default="whisper",
        description=(
            "Voice transcription provider. Supported values: whisper, volcengine"
        ),
    )
    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key used for Whisper transcription"
    )
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Optional OpenAI-compatible API base URL for Whisper transcription",
    )
    whisper_model: str = Field(
        default="whisper-1", description="Whisper model name for voice transcription"
    )
    max_voice_duration: int = Field(
        default=300, description="Maximum accepted voice duration in seconds"
    )
    ffmpeg_path: Optional[str] = Field(
        default=None,
        description="Optional absolute path to ffmpeg binary (defaults to system PATH)",
    )
    # Volcengine bigmodel file ASR fields (v3 submit/query)
    volcengine_app_id: Optional[str] = Field(
        default=None, description="Volcengine appid for bigmodel file ASR"
    )
    volcengine_token: Optional[str] = Field(
        default=None, description="Volcengine token for bigmodel file ASR"
    )
    volcengine_cluster: str = Field(
        default="volc_auc_common",
        description="Volcengine cluster (reserved for compatibility)",
    )
    volcengine_resource_id: str = Field(
        default="volc.bigasr.auc",
        description="Volcengine X-Api-Resource-Id for bigmodel file ASR",
    )
    volcengine_model_name: str = Field(
        default="bigmodel",
        description="Volcengine request.model_name for bigmodel file ASR",
    )
    volcengine_submit_endpoint: str = Field(
        default="https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
        description="Volcengine bigmodel ASR submit endpoint URL",
    )
    volcengine_query_endpoint: str = Field(
        default="https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
        description="Volcengine bigmodel ASR query endpoint URL",
    )
    volcengine_timeout_seconds: float = Field(
        default=20.0,
        description="Volcengine request timeout in seconds",
    )
    volcengine_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for Volcengine transcription",
    )
    volcengine_initial_backoff: float = Field(
        default=1.0,
        description="Initial retry backoff seconds for Volcengine transcription",
    )
    volcengine_poll_interval_seconds: float = Field(
        default=2.0,
        description="Polling interval in seconds for Volcengine query",
    )
    volcengine_max_poll_seconds: float = Field(
        default=300.0,
        description="Maximum polling duration in seconds for Volcengine query",
    )

    @field_validator("transcription_provider", mode="before")
    @classmethod
    def normalize_transcription_provider(cls, v):
        provider = str(v or "whisper").strip().lower()
        allowed = {"whisper", "volcengine"}
        if provider not in allowed:
            raise ValueError(
                "TRANSCRIPTION_PROVIDER must be one of: whisper, volcengine."
            )
        return provider

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_openai_key(cls, v):
        if v is None:
            return None
        value = str(v).strip()
        return value or None

    @field_validator("openai_base_url", mode="before")
    @classmethod
    def normalize_openai_base_url(cls, v):
        if v is None:
            return None
        value = str(v).strip()
        return value or None

    @field_validator(
        "volcengine_app_id",
        "volcengine_token",
        "volcengine_cluster",
        mode="before",
    )
    @classmethod
    def normalize_volcengine_secret(cls, v, info):
        if info.field_name == "volcengine_cluster":
            value = str(v or "").strip()
            return value or "volc_auc_common"
        if v is None:
            return None
        value = str(v).strip()
        return value or None

    @field_validator(
        "volcengine_submit_endpoint",
        "volcengine_query_endpoint",
        "volcengine_resource_id",
        "volcengine_model_name",
    )
    @classmethod
    def validate_volcengine_required_text(cls, v, info):
        value = str(v).strip()
        if not value:
            env_name = info.field_name.upper()
            raise ValueError(f"{env_name} must not be empty.")
        return value

    @field_validator("max_voice_duration")
    @classmethod
    def validate_max_voice_duration(cls, v):
        if v <= 0:
            raise ValueError("MAX_VOICE_DURATION must be a positive integer.")
        return v

    @field_validator("volcengine_timeout_seconds")
    @classmethod
    def validate_volcengine_timeout_seconds(cls, v):
        if v <= 0:
            raise ValueError("VOLCENGINE_TIMEOUT_SECONDS must be positive.")
        return v

    @field_validator("volcengine_max_retries")
    @classmethod
    def validate_volcengine_max_retries(cls, v):
        if v <= 0:
            raise ValueError("VOLCENGINE_MAX_RETRIES must be a positive integer.")
        return v

    @field_validator("volcengine_initial_backoff")
    @classmethod
    def validate_volcengine_initial_backoff(cls, v):
        if v <= 0:
            raise ValueError("VOLCENGINE_INITIAL_BACKOFF must be positive.")
        return v

    @field_validator("volcengine_poll_interval_seconds")
    @classmethod
    def validate_volcengine_poll_interval_seconds(cls, v):
        if v <= 0:
            raise ValueError("VOLCENGINE_POLL_INTERVAL_SECONDS must be positive.")
        return v

    @field_validator("volcengine_max_poll_seconds")
    @classmethod
    def validate_volcengine_max_poll_seconds(cls, v):
        if v <= 0:
            raise ValueError("VOLCENGINE_MAX_POLL_SECONDS must be positive.")
        return v

    @model_validator(mode="after")
    def validate_provider_specific_config(self):
        if self.transcription_provider != "volcengine":
            return self

        missing = []
        if not self.volcengine_app_id:
            missing.append("VOLCENGINE_APP_ID")
        if not self.volcengine_token:
            missing.append("VOLCENGINE_TOKEN")
        if missing:
            raise ValueError(
                "Volcengine transcription provider requires: "
                + ", ".join(missing)
                + "."
            )
        return self

    # Logging
    log_level: str = Field("INFO", description="Logging level")
    log_format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format"
    )


# Global config instance
config = Config()


def setup_logging() -> None:
    """Setup logging configuration with console and file output"""
    log_level = getattr(logging, config.log_level.upper())
    formatter = logging.Formatter(config.log_format)

    is_debug = os.environ.get("BOT_DEBUG")

    # Console handler - WARNING+ in non-debug, full level in debug
    console_level = log_level if is_debug else logging.WARNING
    logging.basicConfig(level=console_level, format=config.log_format)

    # File handler - write to project-root scoped runtime logs.
    logs_dir = config.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    # Always write to file, not just in debug mode
    fh = logging.FileHandler(logs_dir / "bot.log", encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(formatter)
    logging.getLogger().addHandler(fh)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.ExtBot").setLevel(logging.WARNING)

    # Daily error log with stack traces and clear separators
    from datetime import datetime

    err_path = logs_dir / f"error_{datetime.now().strftime('%Y-%m-%d')}.log"
    efh = logging.FileHandler(err_path, encoding="utf-8")
    efh.setLevel(logging.ERROR)
    sep = "=" * 60
    efh.setFormatter(
        logging.Formatter(
            f"\n{sep}\n[%(asctime)s] %(name)s - %(levelname)s\n%(message)s\n{sep}"
        )
    )
    logging.getLogger().addHandler(efh)
