import importlib
import os
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError


class VoiceProviderConfigTests(unittest.TestCase):
    def _load_config_module(self, project_root: str):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ROOT": project_root,
                "TELEGRAM_BOT_TOKEN": "123456:abc",
                "TRANSCRIPTION_PROVIDER": "whisper",
            },
            clear=True,
        ):
            sys.modules.pop("telegram_bot.utils.config", None)
            return importlib.import_module("telegram_bot.utils.config")

    def test_default_provider_is_whisper(self):
        with TemporaryDirectory() as td:
            module = self._load_config_module(td)
            cfg = module.Config(telegram_bot_token="123456:abc", _env_file=None)
            self.assertEqual(cfg.transcription_provider, "whisper")

    def test_invalid_provider_is_rejected(self):
        with TemporaryDirectory() as td:
            module = self._load_config_module(td)
            with self.assertRaises(ValidationError):
                module.Config(
                    telegram_bot_token="123456:abc",
                    transcription_provider="invalid-provider",
                    _env_file=None,
                )

    def test_volcengine_provider_requires_credentials(self):
        with TemporaryDirectory() as td:
            module = self._load_config_module(td)
            with self.assertRaises(ValidationError):
                module.Config(
                    telegram_bot_token="123456:abc",
                    transcription_provider="volcengine",
                    volcengine_app_id="",
                    volcengine_token="",
                    _env_file=None,
                )

    def test_volcengine_provider_with_new_credentials_is_valid(self):
        with TemporaryDirectory() as td:
            module = self._load_config_module(td)
            cfg = module.Config(
                telegram_bot_token="123456:abc",
                transcription_provider="volcengine",
                volcengine_app_id="app-id",
                volcengine_token="token-value",
                _env_file=None,
            )
            self.assertEqual(cfg.transcription_provider, "volcengine")
            self.assertEqual(cfg.volcengine_cluster, "volc_auc_common")

    def test_volcengine_provider_uses_default_cluster_when_blank(self):
        with TemporaryDirectory() as td:
            module = self._load_config_module(td)
            cfg = module.Config(
                telegram_bot_token="123456:abc",
                transcription_provider="volcengine",
                volcengine_app_id="app-id",
                volcengine_token="token-value",
                volcengine_cluster="",
                _env_file=None,
            )
            self.assertEqual(cfg.volcengine_cluster, "volc_auc_common")


if __name__ == "__main__":
    unittest.main()
