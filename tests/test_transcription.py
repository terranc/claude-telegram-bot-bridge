import sys
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from telegram_bot.utils.transcription import (
    EmptyTranscriptionError,
    TranscriptionError,
    VolcengineFileFastTranscriber,
    WhisperTranscriber,
)

_NOISY_LOGGERS = ["telegram_bot.utils.transcription"]
_ORIGINAL_LEVELS = {}


def setUpModule():
    for logger_name in _NOISY_LOGGERS:
        logger = logging.getLogger(logger_name)
        _ORIGINAL_LEVELS[logger_name] = logger.level
        logger.setLevel(logging.CRITICAL)


def tearDownModule():
    for logger_name, original_level in _ORIGINAL_LEVELS.items():
        logging.getLogger(logger_name).setLevel(original_level)


class _FakeTranscriptions:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def create(self, **kwargs):
        del kwargs
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes):
        self.transcriptions = _FakeTranscriptions(outcomes)
        self.audio = SimpleNamespace(transcriptions=self.transcriptions)


class WhisperTranscriberTests(unittest.IsolatedAsyncioTestCase):
    def test_passes_base_url_to_client_factory(self):
        captured = {}

        def factory(**kwargs):
            captured.update(kwargs)
            return _FakeClient([SimpleNamespace(text="ok")])

        transcriber = WhisperTranscriber(
            api_key="test-key",
            model="whisper-1",
            base_url="https://whisper-proxy.example.com/v1",
            client_factory=factory,
        )

        self.assertIsNotNone(transcriber.client)
        self.assertEqual(captured["api_key"], "test-key")
        self.assertEqual(captured["base_url"], "https://whisper-proxy.example.com/v1")

    async def test_transcribe_audio_retries_and_succeeds(self):
        with TemporaryDirectory() as td:
            audio_file = Path(td) / "voice.mp3"
            audio_file.write_bytes(b"ID3fake")

            client = _FakeClient(
                [RuntimeError("boom"), SimpleNamespace(text="hello world")]
            )
            transcriber = WhisperTranscriber(
                api_key="test-key",
                model="whisper-1",
                client=client,
                max_retries=2,
                initial_backoff=0.01,
            )

            sleep_mock = AsyncMock()
            with patch("asyncio.sleep", sleep_mock):
                text = await transcriber.transcribe_audio(
                    audio_file, duration_seconds=10
                )

            self.assertEqual(text, "hello world")
            self.assertEqual(client.transcriptions.calls, 2)
            sleep_mock.assert_awaited_once()

    async def test_transcribe_audio_rejects_empty_result(self):
        with TemporaryDirectory() as td:
            audio_file = Path(td) / "voice.mp3"
            audio_file.write_bytes(b"ID3fake")

            client = _FakeClient([SimpleNamespace(text="   ")])
            transcriber = WhisperTranscriber(
                api_key="test-key",
                model="whisper-1",
                client=client,
            )

            with self.assertRaises(EmptyTranscriptionError):
                await transcriber.transcribe_audio(audio_file)

    async def test_transcribe_audio_raises_transcription_error_after_retries(self):
        with TemporaryDirectory() as td:
            audio_file = Path(td) / "voice.mp3"
            audio_file.write_bytes(b"ID3fake")

            client = _FakeClient(
                [RuntimeError("err-1"), RuntimeError("err-2"), RuntimeError("err-3")]
            )
            transcriber = WhisperTranscriber(
                api_key="test-key",
                model="whisper-1",
                client=client,
                max_retries=3,
                initial_backoff=0.01,
            )

            with self.assertRaises(TranscriptionError) as ctx:
                await transcriber.transcribe_audio(audio_file)
            self.assertIn("Unable to transcribe audio", str(ctx.exception))

    def test_requires_api_key_when_client_not_injected(self):
        with self.assertRaises(ValueError):
            WhisperTranscriber(api_key="", client=None)


class VolcengineFileFastTranscriberTests(unittest.IsolatedAsyncioTestCase):
    def test_requires_app_id(self):
        with self.assertRaises(ValueError):
            VolcengineFileFastTranscriber(
                app_id="",
                token="token",
                cluster="volcengine_streaming_common",
            )

    def test_requires_token(self):
        with self.assertRaises(ValueError):
            VolcengineFileFastTranscriber(
                app_id="app",
                token="",
                cluster="volcengine_streaming_common",
            )

    def test_uses_default_cluster_when_not_provided(self):
        transcriber = VolcengineFileFastTranscriber(
            app_id="app",
            token="token",
            cluster="",
        )
        self.assertEqual(transcriber.cluster, "volc_auc_common")

    async def test_transcribe_audio_submits_and_queries_successfully(self):
        calls = []
        responses = [
            {
                "api_status_code": "20000000",
                "api_message": "OK",
                "body": {},
            },
            {
                "api_status_code": "20000001",
                "api_message": "Processing",
                "body": {},
            },
            {
                "api_status_code": "20000000",
                "api_message": "OK",
                "body": {"result": {"text": "hello volcengine"}},
            },
        ]

        def sender(endpoint, headers, payload, timeout):
            calls.append((endpoint, headers, payload, timeout))
            return responses.pop(0)

        transcriber = VolcengineFileFastTranscriber(
            app_id="app-id",
            token="token-value",
            cluster="volcengine_streaming_common",
            submit_endpoint="https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
            query_endpoint="https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
            request_timeout=18.0,
            request_sender=sender,
            poll_interval_seconds=0.01,
            max_poll_seconds=2.0,
        )

        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            text = await transcriber.transcribe_audio("https://example.com/audio.oga")

        self.assertEqual(text, "hello volcengine")

        submit_endpoint, submit_headers, submit_payload, submit_timeout = calls[0]
        query_endpoint, query_headers, query_payload, query_timeout = calls[1]
        self.assertEqual(
            submit_endpoint,
            "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
        )
        self.assertEqual(
            query_endpoint, "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
        )
        self.assertEqual(submit_headers["Content-Type"], "application/json")
        self.assertEqual(submit_headers["X-Api-App-Key"], "app-id")
        self.assertEqual(submit_headers["X-Api-Access-Key"], "token-value")
        self.assertEqual(submit_headers["X-Api-Resource-Id"], "volc.bigasr.auc")
        self.assertEqual(submit_headers["X-Api-Sequence"], "-1")
        self.assertIn("X-Api-Request-Id", submit_headers)
        self.assertEqual(
            submit_payload["audio"]["url"], "https://example.com/audio.oga"
        )
        self.assertEqual(submit_payload["audio"]["format"], "ogg")
        self.assertTrue(submit_payload["user"]["uid"])
        self.assertEqual(submit_payload["request"]["model_name"], "bigmodel")
        self.assertEqual(query_payload, {})
        self.assertEqual(
            query_headers["X-Api-Request-Id"], submit_headers["X-Api-Request-Id"]
        )
        self.assertNotIn("X-Api-Sequence", query_headers)
        self.assertEqual(submit_timeout, 18.0)
        self.assertEqual(query_timeout, 18.0)
        sleep_mock.assert_awaited_once()

    async def test_transcribe_audio_retries_and_succeeds(self):
        responses = [
            RuntimeError("transient"),
            {
                "api_status_code": "20000000",
                "api_message": "OK",
                "body": {},
            },
            {
                "api_status_code": "20000000",
                "api_message": "OK",
                "body": {"result": {"text": "ok"}},
            },
        ]

        def sender(endpoint, headers, payload, timeout):
            del endpoint, headers, payload, timeout
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        transcriber = VolcengineFileFastTranscriber(
            app_id="app-id",
            token="token-value",
            cluster="volcengine_streaming_common",
            request_sender=sender,
            max_retries=2,
            initial_backoff=0.01,
            poll_interval_seconds=0.01,
            max_poll_seconds=2.0,
        )
        sleep_mock = AsyncMock()
        with patch("asyncio.sleep", sleep_mock):
            text = await transcriber.transcribe_audio("https://example.com/audio.ogg")

        self.assertEqual(text, "ok")
        sleep_mock.assert_awaited_once()

    async def test_transcribe_audio_raises_empty_transcription_error(self):
        def sender(endpoint, headers, payload, timeout):
            del headers, payload, timeout
            if endpoint.endswith("/submit"):
                return {"api_status_code": "20000000", "api_message": "OK", "body": {}}
            return {
                "api_status_code": "20000000",
                "api_message": "OK",
                "body": {"result": {"text": "   "}},
            }

        transcriber = VolcengineFileFastTranscriber(
            app_id="app-id",
            token="token-value",
            cluster="volcengine_streaming_common",
            request_sender=sender,
            poll_interval_seconds=0.01,
            max_poll_seconds=2.0,
        )

        with self.assertRaises(EmptyTranscriptionError):
            await transcriber.transcribe_audio("https://example.com/audio.ogg")

    async def test_transcribe_audio_raises_transcription_error_after_retries(self):
        def sender(endpoint, headers, payload, timeout):
            del endpoint, headers, payload, timeout
            return {
                "api_status_code": "45000001",
                "api_message": "permission denied",
                "body": {},
            }

        transcriber = VolcengineFileFastTranscriber(
            app_id="app-id",
            token="token-value",
            cluster="volcengine_streaming_common",
            request_sender=sender,
            max_retries=2,
            initial_backoff=0.01,
        )

        with self.assertRaises(TranscriptionError) as ctx:
            await transcriber.transcribe_audio("https://example.com/audio.ogg")
        self.assertIn("Unable to transcribe audio", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
