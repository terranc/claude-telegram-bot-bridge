# Testing

**Analysis Date:** 2026-03-22

## Overview

The Telegram Bot project uses Python's built-in `unittest` framework with async support. Tests are co-located in a dedicated `tests/` directory alongside the source code. The testing philosophy emphasizes:

- **Unit tests** for business logic and utility functions
- **Mock-based testing** for external dependencies (Telegram API, OpenAI, Volcengine)
- **Isolated async tests** using `IsolatedAsyncioTestCase`
- **No integration tests** - all external I/O is mocked

## Test Framework

### Framework and Version
- **Framework:** Python `unittest` (built-in)
- **Async Support:** `unittest.IsolatedAsyncioTestCase`
- **Mocking:** `unittest.mock` (AsyncMock, patch, MagicMock)
- **Python Version:** 3.11+

### Test Configuration
Tests are discovered automatically by `unittest` when run from the project root:

```bash
# Run all tests
python -m unittest discover -s tests

# Run specific test file
python -m unittest tests.test_audio_processor

# Run with verbose output
python -m unittest discover -s tests -v
```

## Test Structure

### File Organization
Tests are organized in `/Users/terranc/www/telegram_bot/tests/` directory:

```
tests/
├── test_audio_processor.py       # Audio format detection and conversion
├── test_config_voice_provider.py # Voice provider configuration
├── test_connection_resilience.py # Connection retry logic
├── test_health.py                # Health reporter functionality
├── test_revert.py                # Session revert functionality
├── test_session_manager.py       # Session management
├── test_start_status.py          # Start/stop status logic
├── test_streaming.py             # Streaming message handler
├── test_tos_uploader.py          # TOS upload functionality
├── test_transcription.py         # Whisper/Volcengine transcription
├── test_tts.py                   # macOS TTS synthesis
├── test_voice_flow.py            # Voice message flow
├── test_voice_handler.py         # Voice message handling
├── test_voice_reply_mode.py      # Voice reply mode settings
└── test_watchdog.py              # Watchdog functionality
```

### Test Class Naming
- Test classes use `PascalCase` with `Tests` suffix
- Async test classes inherit from `unittest.IsolatedAsyncioTestCase`
- Sync test classes inherit from `unittest.TestCase`

Example from `/Users/terranc/www/telegram_bot/tests/test_audio_processor.py`:
```python
class AudioProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_detect_audio_format_by_magic_bytes(self):
        ...
```

### Test Method Naming
- Test methods use `snake_case` with `test_` prefix
- Descriptive names explaining what is being tested
- Include the expected outcome in the name

Example:
```python
async def test_transcribe_audio_retries_and_succeeds(self):
async def test_transcribe_audio_rejects_empty_result(self):
async def test_transcribe_audio_raises_transcription_error_after_retries(self):
```

## Test Types

### Unit Tests
Unit tests focus on isolated business logic without external dependencies.

**Scope:**
- Audio format detection and conversion (`test_audio_processor.py`)
- Transcription logic (`test_transcription.py`)
- TTS synthesis (`test_tts.py`)
- Configuration validation (`test_config_voice_provider.py`)

**Example from `/Users/terranc/www/telegram_bot/tests/test_audio_processor.py`:**
```python
async def test_detect_audio_format_by_magic_bytes(self):
    with TemporaryDirectory() as td:
        td_path = Path(td)

        ogg_file = td_path / "voice.bin"
        ogg_file.write_bytes(b"OggSabcdef")

        processor = AudioProcessor()
        self.assertEqual(await processor.detect_audio_format(ogg_file), "ogg")
```

### Mock-Based Tests
Most tests mock external I/O operations (network, filesystem, subprocess).

**Mocking Patterns:**
- `AsyncMock` for async functions
- `unittest.mock.patch` for module-level patches
- `SimpleNamespace` for creating fake objects
- `_FakeProcess` helper for subprocess mocking

**Example from `/Users/terranc/www/telegram_bot/tests/test_transcription.py`:**
```python
class _FakeClient:
    def __init__(self, outcomes):
        self.transcriptions = _FakeTranscriptions(outcomes)
        self.audio = SimpleNamespace(transcriptions=self.transcriptions)

async def test_transcribe_audio_retries_and_succeeds(self):
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
        text = await transcriber.transcribe_audio(audio_file, duration_seconds=10)

    self.assertEqual(text, "hello world")
```

### Configuration Tests
Tests for configuration validation using mocked environment.

**Example from `/Users/terranc/www/telegram_bot/tests/test_session_manager.py`:**
```python
def _load_session_manager_module(self, project_root: str, **extra_env):
    with patch.dict(
        os.environ,
        {
            "PROJECT_ROOT": project_root,
            "TELEGRAM_BOT_TOKEN": "123456:abc",
            **extra_env,
        },
        clear=True,
    ):
        for name in (
            "telegram_bot.utils.config",
            "telegram_bot.session.store",
            "telegram_bot.session.manager",
        ):
            sys.modules.pop(name, None)
        return importlib.import_module("telegram_bot.session.manager")
```

## Mocking

### Common Mock Helpers

**`_FakeProcess` for subprocess mocking:**
```python
class _FakeProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr
```

**`_FakeClient` for API client mocking:**
```python
class _FakeClient:
    def __init__(self, outcomes):
        self.transcriptions = _FakeTranscriptions(outcomes)
        self.audio = SimpleNamespace(transcriptions=self.transcriptions)
```

### Patch Patterns

**Patching async functions:**
```python
sleep_mock = AsyncMock()
with patch("asyncio.sleep", sleep_mock):
    result = await async_function()
```

**Patching subprocess:**
```python
with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=_FakeProcess())):
    result = await processor.convert_audio(input_path, output_path)
```

**Module-level patching for tests:**
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Mock config before importing modules that depend on it
config_module = types.ModuleType("telegram_bot.utils.config")
config_module.config = SimpleNamespace(
    draft_update_min_chars=20,
    draft_update_interval=0.1,
)
sys.modules["telegram_bot.utils.config"] = config_module

# Now import the module under test
from telegram_bot.core.streaming import StreamingMessageHandler
```

## Coverage

### Coverage Goals
- **Target Coverage:** Not explicitly enforced
- **Focus Areas:** Business logic, utility functions, configuration validation
- **Exclusions:** External API clients (mocked), Telegram bot handlers (mocked integration)

### Coverage Gaps
- No integration tests with real Telegram API
- No integration tests with real OpenAI/Volcengine APIs
- Some async error paths not fully covered

## Running Tests

### Run All Tests
```bash
# From project root
python -m unittest discover -s tests

# With verbose output
python -m unittest discover -s tests -v
```

### Run Specific Test File
```bash
python -m unittest tests.test_audio_processor
python -m unittest tests.test_transcription
python -m unittest tests.test_session_manager
```

### Run Specific Test Method
```bash
python -m unittest tests.test_audio_processor.AudioProcessorTests.test_detect_audio_format_by_magic_bytes
```

### Module Path Setup
Tests use this pattern to ensure imports work:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
```

---

*Testing analysis: 2026-03-22*
