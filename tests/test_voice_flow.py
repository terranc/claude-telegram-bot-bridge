# ruff: noqa: E402
# mypy: disable-error-code=attr-defined

import asyncio
import sys
import types
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


config_module = types.ModuleType("telegram_bot.utils.config")
config_module.config = SimpleNamespace(
    telegram_bot_token="test-token",
    allowed_user_ids=[],
    claude_settings_path=Path("/tmp/settings.json"),
    max_voice_duration=300,
    bot_data_dir=Path("/tmp/telegram-bot-data"),
    transcription_provider="whisper",
    openai_api_key="test-key",
    openai_base_url=None,
    whisper_model="whisper-1",
    ffmpeg_path="ffmpeg",
    volcengine_app_id="test-app-id",
    volcengine_token="test-token",
    volcengine_access_key="test-ak",
    volcengine_secret_access_key="test-sk",
    volcengine_tos_bucket_name="voice-stage",
    volcengine_tos_endpoint="https://tos-cn-shanghai.volces.com",
    volcengine_tos_region="cn-shanghai",
    volcengine_tos_signed_url_ttl_seconds=900,
    volcengine_cluster="volcengine_streaming_common",
    volcengine_resource_id="volc.bigasr.auc",
    volcengine_model_name="bigmodel",
    volcengine_submit_endpoint="https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
    volcengine_query_endpoint="https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
    volcengine_timeout_seconds=20.0,
    volcengine_max_retries=3,
    volcengine_initial_backoff=1.0,
    volcengine_poll_interval_seconds=2.0,
    volcengine_max_poll_seconds=300.0,
    draft_update_min_chars=20,
    draft_update_interval=0.1,
)
sys.modules["telegram_bot.utils.config"] = config_module


session_module = types.ModuleType("telegram_bot.session.manager")


class _SessionManager:
    async def get_session(self, user_id):
        del user_id
        return {}

    async def update_session(self, user_id, data):
        del user_id, data
        return None

    async def get_pending_question(self, user_id):
        del user_id
        return None

    async def clear_pending_question(self, user_id):
        del user_id
        return None

    async def clear_approve_all(self, user_id):
        del user_id
        return None


session_module.session_manager = _SessionManager()
sys.modules["telegram_bot.session.manager"] = session_module


project_chat_module = types.ModuleType("telegram_bot.core.project_chat")


class _ChatResponse:
    def __init__(self, content="", session_id=None, has_options=False, streamed=False):
        self.content = content
        self.session_id = session_id
        self.has_options = has_options
        self.streamed = streamed


class _ProjectChatHandler:
    async def process_message(self, **kwargs):
        del kwargs
        return _ChatResponse(content="ok")

    async def stop(self, user_id):
        del user_id
        return False

    async def cancel_user_streaming(self, user_id):
        del user_id
        return False

    def list_sessions(self, limit=10):
        del limit
        return []

    def get_session_last_assistant_message(self, session_id):
        del session_id
        return None


project_chat_module.project_chat_handler = _ProjectChatHandler()
project_chat_module.ChatResponse = _ChatResponse
project_chat_module.PROJECT_ROOT = Path("/tmp")
project_chat_module.CONVERSATIONS_DIR = Path("/tmp/conversations")
sys.modules["telegram_bot.core.project_chat"] = project_chat_module


chat_logger_module = types.ModuleType("telegram_bot.utils.chat_logger")
chat_logger_module.log_debug = lambda *args, **kwargs: None
sys.modules["telegram_bot.utils.chat_logger"] = chat_logger_module


permission_module = types.ModuleType("claude_agent_sdk.types")
permission_module.PermissionResultAllow = type("PermissionResultAllow", (), {})
permission_module.PermissionResultDeny = type(
    "PermissionResultDeny", (), {"__init__": lambda self, message="": None}
)
sys.modules["claude_agent_sdk.types"] = permission_module


import telegram_bot.core.bot as bot_module
from telegram_bot.core.bot import TelegramBot
from telegram_bot.utils.tos_uploader import TOSUploadError
from telegram_bot.utils.transcription import EmptyTranscriptionError, TranscriptionError

_NOISY_LOGGERS = ["telegram_bot.core.bot"]
_ORIGINAL_LEVELS = {}


def setUpModule():
    for logger_name in _NOISY_LOGGERS:
        logger = logging.getLogger(logger_name)
        _ORIGINAL_LEVELS[logger_name] = logger.level
        logger.setLevel(logging.CRITICAL)


def tearDownModule():
    for logger_name, original_level in _ORIGINAL_LEVELS.items():
        logging.getLogger(logger_name).setLevel(original_level)


class _FakeMessage:
    def __init__(self, voice):
        self.voice = voice
        self.message_id = 1
        self.chat = SimpleNamespace(send_action=AsyncMock())
        self.replies = []

    async def reply_text(self, text, **kwargs):
        del kwargs
        self.replies.append(text)


def _build_update(user_id: int, voice):
    message = _FakeMessage(voice)
    return SimpleNamespace(
        message=message,
        callback_query=None,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=1001),
    )


class VoiceFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_ignores_unauthorized_voice_message(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=False)
        bot._enqueue_user_task = AsyncMock()
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        await bot._handle_voice_message(update, None)
        bot._enqueue_user_task.assert_not_called()

    async def test_rejects_when_duration_exceeds_limit(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        voice = SimpleNamespace(file_id="v1", duration=301, mime_type="audio/ogg")
        update = _build_update(11, voice)

        await bot._handle_voice_message(update, None)
        self.assertTrue(any("too long" in msg for msg in update.message.replies))

    async def test_reports_queue_overflow(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def overflow(user_id, run_task, on_overflow):
            del user_id, run_task
            await on_overflow()
            return False

        bot._enqueue_user_task = overflow
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        await bot._handle_voice_message(update, None)
        self.assertTrue(
            any("Voice queue is full" in msg for msg in update.message.replies)
        )

    async def test_reports_download_failure(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(side_effect=RuntimeError("download error"))
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        await bot._handle_voice_message(update, None)
        self.assertTrue(
            any("Failed to download" in msg for msg in update.message.replies)
        )

    async def test_reports_conversion_failure(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(return_value=None)
        bot._prepare_audio_for_whisper = AsyncMock(
            side_effect=RuntimeError("ffmpeg missing")
        )
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        await bot._handle_voice_message(update, None)
        self.assertTrue(
            any("Failed to convert audio" in msg for msg in update.message.replies)
        )

    async def test_reports_empty_transcription(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(return_value=None)
        bot._prepare_audio_for_whisper = AsyncMock(
            side_effect=lambda path, cleanup: path
        )
        transcriber = SimpleNamespace(
            transcribe_audio=AsyncMock(side_effect=EmptyTranscriptionError("empty"))
        )
        bot._get_whisper_transcriber = lambda: transcriber
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        with TemporaryDirectory() as td:
            bot._audio_dir = Path(td)
            await bot._handle_voice_message(update, None)
        self.assertTrue(
            any("No speech was detected" in msg for msg in update.message.replies)
        )

    async def test_successful_transcription_forwards_text(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(return_value=None)
        bot._prepare_audio_for_whisper = AsyncMock(
            side_effect=lambda path, cleanup: path
        )
        bot._process_user_message_text = AsyncMock()
        transcriber = SimpleNamespace(
            transcribe_audio=AsyncMock(return_value="hello from voice")
        )
        bot._get_whisper_transcriber = lambda: transcriber
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        with TemporaryDirectory() as td:
            bot._audio_dir = Path(td)
            await bot._handle_voice_message(update, None)

        bot._process_user_message_text.assert_awaited_once()
        called = bot._process_user_message_text.await_args
        called_text = called.args[2]
        self.assertEqual(called_text, "hello from voice")
        self.assertEqual(called.kwargs.get("message_source"), "voice")
        self.assertEqual(
            called.kwargs.get("voice_input_preview"), "🎤 Voice: hello from voice"
        )

    async def test_successful_volcengine_transcription_uses_tos_url(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        old_provider = bot_module.config.transcription_provider
        config_module.config.transcription_provider = "volcengine"
        bot_module.config.transcription_provider = "volcengine"

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(return_value=None)
        bot._prepare_audio_for_whisper = AsyncMock(
            side_effect=lambda path, cleanup: path
        )
        bot._process_user_message_text = AsyncMock()
        uploaded = SimpleNamespace(
            signed_url="https://tos.example.com/stage/voice.ogg?X-Tos-Signature=abc",
            object_key="telegram-voice/11/object.ogg",
        )
        uploader = SimpleNamespace(
            upload_file_with_object_key=MagicMock(return_value=uploaded),
            delete_object=MagicMock(return_value=None),
            redact_signed_url=lambda url: (
                "https://tos.example.com/stage/voice.ogg?***REDACTED***"
            ),
        )
        bot._get_volcengine_tos_uploader = lambda: uploader
        transcriber = SimpleNamespace(
            transcribe_audio=AsyncMock(return_value="hello from volcengine")
        )
        bot._get_volcengine_transcriber = lambda: transcriber
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        try:
            with TemporaryDirectory() as td:
                bot._audio_dir = Path(td)
                await bot._handle_voice_message(update, None)
        finally:
            config_module.config.transcription_provider = old_provider
            bot_module.config.transcription_provider = old_provider

        bot._download_voice_file.assert_awaited_once()
        self.assertEqual(uploader.upload_file_with_object_key.call_count, 1)
        transcriber.transcribe_audio.assert_awaited_once_with(
            "https://tos.example.com/stage/voice.ogg?X-Tos-Signature=abc",
            duration_seconds=30,
        )
        uploader.delete_object.assert_called_once_with("telegram-voice/11/object.ogg")
        bot._prepare_audio_for_whisper.assert_not_called()
        bot._process_user_message_text.assert_awaited_once()
        called = bot._process_user_message_text.await_args
        self.assertEqual(called.kwargs.get("message_source"), "voice")
        self.assertEqual(
            called.kwargs.get("voice_input_preview"),
            "🎤 Voice: hello from volcengine",
        )

    async def test_volcengine_delete_failure_does_not_break_successful_reply(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        old_provider = bot_module.config.transcription_provider
        config_module.config.transcription_provider = "volcengine"
        bot_module.config.transcription_provider = "volcengine"

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(return_value=None)
        bot._prepare_audio_for_whisper = AsyncMock(
            side_effect=lambda path, cleanup: path
        )
        bot._process_user_message_text = AsyncMock()
        uploader = SimpleNamespace(
            upload_file_with_object_key=MagicMock(
                return_value=SimpleNamespace(
                    signed_url="https://tos.example.com/stage/voice.ogg?X-Tos-Signature=abc",
                    object_key="telegram-voice/11/object.ogg",
                )
            ),
            delete_object=MagicMock(side_effect=TOSUploadError("delete failed")),
            redact_signed_url=lambda url: (
                "https://tos.example.com/stage/voice.ogg?***REDACTED***"
            ),
        )
        bot._get_volcengine_tos_uploader = lambda: uploader
        transcriber = SimpleNamespace(
            transcribe_audio=AsyncMock(return_value="hello from volcengine")
        )
        bot._get_volcengine_transcriber = lambda: transcriber
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        try:
            with TemporaryDirectory() as td:
                bot._audio_dir = Path(td)
                await bot._handle_voice_message(update, None)
        finally:
            config_module.config.transcription_provider = old_provider
            bot_module.config.transcription_provider = old_provider

        transcriber.transcribe_audio.assert_awaited_once()
        uploader.delete_object.assert_called_once_with("telegram-voice/11/object.ogg")
        bot._process_user_message_text.assert_awaited_once()

    async def test_volcengine_transcription_failure_still_deletes_tos_object(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        old_provider = bot_module.config.transcription_provider
        config_module.config.transcription_provider = "volcengine"
        bot_module.config.transcription_provider = "volcengine"

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now
        bot._download_voice_file = AsyncMock(return_value=None)
        uploader = SimpleNamespace(
            upload_file_with_object_key=MagicMock(
                return_value=SimpleNamespace(
                    signed_url="https://tos.example.com/stage/voice.ogg?X-Tos-Signature=abc",
                    object_key="telegram-voice/11/object.ogg",
                )
            ),
            delete_object=MagicMock(return_value=None),
            redact_signed_url=lambda url: (
                "https://tos.example.com/stage/voice.ogg?***REDACTED***"
            ),
        )
        bot._get_volcengine_tos_uploader = lambda: uploader
        transcriber = SimpleNamespace(
            transcribe_audio=AsyncMock(side_effect=TranscriptionError("asr failed"))
        )
        bot._get_volcengine_transcriber = lambda: transcriber
        bot._process_user_message_text = AsyncMock()
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        try:
            with TemporaryDirectory() as td:
                bot._audio_dir = Path(td)
                await bot._handle_voice_message(update, None)
        finally:
            config_module.config.transcription_provider = old_provider
            bot_module.config.transcription_provider = old_provider

        uploader.delete_object.assert_called_once_with("telegram-voice/11/object.ogg")
        bot._process_user_message_text.assert_not_awaited()
        self.assertTrue(
            any(
                "Failed to transcribe your voice message" in msg
                for msg in update.message.replies
            )
        )

    async def test_reports_missing_volcengine_configuration(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        old_provider = bot_module.config.transcription_provider
        config_module.config.transcription_provider = "volcengine"
        bot_module.config.transcription_provider = "volcengine"

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now

        def raise_missing_config():
            raise ValueError("missing Volcengine credentials")

        bot._get_volcengine_transcriber = raise_missing_config
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        try:
            with TemporaryDirectory() as td:
                bot._audio_dir = Path(td)
                await bot._handle_voice_message(update, None)
        finally:
            config_module.config.transcription_provider = old_provider
            bot_module.config.transcription_provider = old_provider

        self.assertTrue(
            any(
                "Voice transcription is not configured" in msg
                for msg in update.message.replies
            )
        )

    async def test_reports_missing_volcengine_dependency(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        old_provider = bot_module.config.transcription_provider
        config_module.config.transcription_provider = "volcengine"
        bot_module.config.transcription_provider = "volcengine"

        async def run_now(user_id, run_task, on_overflow):
            del user_id, on_overflow
            await run_task()
            return True

        bot._enqueue_user_task = run_now

        def raise_missing_dependency():
            raise RuntimeError("tos package is not installed")

        bot._get_volcengine_transcriber = lambda: SimpleNamespace(
            transcribe_audio=AsyncMock(return_value="unused")
        )
        bot._get_volcengine_tos_uploader = raise_missing_dependency
        voice = SimpleNamespace(file_id="v1", duration=30, mime_type="audio/ogg")
        update = _build_update(11, voice)

        try:
            with TemporaryDirectory() as td:
                bot._audio_dir = Path(td)
                await bot._handle_voice_message(update, None)
        finally:
            config_module.config.transcription_provider = old_provider
            bot_module.config.transcription_provider = old_provider

        self.assertTrue(
            any("dependency is missing" in msg for msg in update.message.replies)
        )

    async def test_stop_cancels_active_voice_tasks(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def long_task():
            await asyncio.sleep(60)

        task = asyncio.create_task(long_task())
        bot._track_voice_task(11, task)

        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock(), text="/stop"),
            callback_query=None,
            effective_user=SimpleNamespace(id=11),
            effective_chat=SimpleNamespace(id=1001),
        )
        await bot._cmd_stop(update, None)
        self.assertTrue(task.cancelled())

    async def test_new_cancels_active_voice_tasks(self):
        bot = TelegramBot()
        bot._check_access = AsyncMock(return_value=True)

        async def long_task():
            await asyncio.sleep(60)

        task = asyncio.create_task(long_task())
        bot._track_voice_task(11, task)

        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock(), text="/new"),
            callback_query=None,
            effective_user=SimpleNamespace(id=11),
            effective_chat=SimpleNamespace(id=1001),
        )
        await bot._cmd_new(update, None)
        self.assertTrue(task.cancelled())


if __name__ == "__main__":
    unittest.main()
