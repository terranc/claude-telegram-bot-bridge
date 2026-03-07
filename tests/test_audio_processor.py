import sys
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from telegram_bot.utils.audio_processor import AudioProcessor

_NOISY_LOGGERS = ["telegram_bot.utils.audio_processor"]
_ORIGINAL_LEVELS = {}


def setUpModule():
    for logger_name in _NOISY_LOGGERS:
        logger = logging.getLogger(logger_name)
        _ORIGINAL_LEVELS[logger_name] = logger.level
        logger.setLevel(logging.CRITICAL)


def tearDownModule():
    for logger_name, original_level in _ORIGINAL_LEVELS.items():
        logging.getLogger(logger_name).setLevel(original_level)


class _FakeProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


class AudioProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_detect_audio_format_by_magic_bytes(self):
        with TemporaryDirectory() as td:
            td_path = Path(td)

            ogg_file = td_path / "voice.bin"
            ogg_file.write_bytes(b"OggSabcdef")

            amr_file = td_path / "voice2.bin"
            amr_file.write_bytes(b"#!AMR\n12345")

            mp3_file = td_path / "voice3.bin"
            mp3_file.write_bytes(b"ID3abcdef")

            processor = AudioProcessor()
            self.assertEqual(await processor.detect_audio_format(ogg_file), "ogg")
            self.assertEqual(await processor.detect_audio_format(amr_file), "amr")
            self.assertEqual(await processor.detect_audio_format(mp3_file), "mp3")

    async def test_convert_audio_uses_whisper_defaults(self):
        with TemporaryDirectory() as td:
            td_path = Path(td)
            input_file = td_path / "in.ogg"
            output_file = td_path / "out.mp3"
            input_file.write_bytes(b"OggS123")

            processor = AudioProcessor(ffmpeg_path="/usr/local/bin/ffmpeg")

            mock_exec = AsyncMock(return_value=_FakeProcess(returncode=0))
            with patch("asyncio.create_subprocess_exec", mock_exec):
                result = await processor.convert_audio(input_file, output_file)

            self.assertEqual(result, output_file)
            called = mock_exec.await_args.args
            self.assertEqual(called[0], "/usr/local/bin/ffmpeg")
            self.assertIn("-ac", called)
            self.assertIn("1", called)
            self.assertIn("-ar", called)
            self.assertIn("16000", called)

    async def test_convert_audio_raises_when_ffmpeg_fails(self):
        with TemporaryDirectory() as td:
            td_path = Path(td)
            input_file = td_path / "in.ogg"
            output_file = td_path / "out.mp3"
            input_file.write_bytes(b"OggS123")

            processor = AudioProcessor()
            mock_exec = AsyncMock(
                return_value=_FakeProcess(returncode=1, stderr=b"conversion failed")
            )
            with patch("asyncio.create_subprocess_exec", mock_exec):
                with self.assertRaises(RuntimeError) as ctx:
                    await processor.convert_audio(input_file, output_file)
            self.assertIn("conversion failed", str(ctx.exception))

    async def test_cleanup_audio_files_removes_existing_paths(self):
        with TemporaryDirectory() as td:
            td_path = Path(td)
            f1 = td_path / "a.mp3"
            f2 = td_path / "b.ogg"
            f1.write_text("x", encoding="utf-8")
            f2.write_text("x", encoding="utf-8")

            processor = AudioProcessor()
            await processor.cleanup_audio_files([f1, f2, td_path / "missing.amr"])

            self.assertFalse(f1.exists())
            self.assertFalse(f2.exists())

    async def test_check_ffmpeg_available_uses_path_or_system_lookup(self):
        processor = AudioProcessor(ffmpeg_path="/custom/ffmpeg")
        with patch("shutil.which", return_value="/custom/ffmpeg"):
            self.assertTrue(await processor.check_ffmpeg_available())

        processor2 = AudioProcessor(ffmpeg_path="ffmpeg")
        with patch("shutil.which", return_value=None):
            self.assertFalse(await processor2.check_ffmpeg_available())


if __name__ == "__main__":
    unittest.main()
