import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib import parse as urllib_parse
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

WHISPER_PRICE_PER_MINUTE_USD = 0.006
VOLCENGINE_SUBMIT_ENDPOINT = (
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
)
VOLCENGINE_QUERY_ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
VOLCENGINE_DEFAULT_CLUSTER = "volc_auc_common"
VOLCENGINE_DEFAULT_RESOURCE_ID = "volc.bigasr.auc"
VOLCENGINE_DEFAULT_MODEL_NAME = "bigmodel"
VOLCENGINE_SUCCESS_CODE = 20000000
VOLCENGINE_PROCESSING_CODES = {20000001, 20000002}


class TranscriptionError(RuntimeError):
    """Raised when transcription fails after retries."""


class EmptyTranscriptionError(TranscriptionError):
    """Raised when provider returns empty or whitespace-only text."""


class WhisperTranscriber:
    """Whisper transcription wrapper with retry and structured errors."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "whisper-1",
        base_url: Optional[str] = None,
        client: Optional[Any] = None,
        client_factory: Optional[Callable[..., Any]] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = model
        self.base_url = (base_url or "").strip() or None
        self.max_retries = max(1, int(max_retries))
        self.initial_backoff = max(0.1, float(initial_backoff))

        if client is not None:
            self.client = client
            return

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for voice transcription.")

        if client_factory is not None:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.client = client_factory(**kwargs)
            return

        try:
            import openai  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "openai package is not installed. Please add it to requirements."
            ) from exc

        if hasattr(openai, "AsyncOpenAI"):
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.client = openai.AsyncOpenAI(**kwargs)
        else:
            openai.api_key = self.api_key
            if self.base_url:
                if hasattr(openai, "api_base"):
                    openai.api_base = self.base_url
                if hasattr(openai, "base_url"):
                    openai.base_url = self.base_url
            self.client = openai

    async def transcribe_audio(
        self, audio_path: Path, duration_seconds: Optional[int] = None
    ) -> str:
        """Transcribe an audio file with retries and validation."""
        start = time.perf_counter()
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = await self._call_whisper(audio_path)
                text = self._extract_text(raw).strip()
                if not text:
                    raise EmptyTranscriptionError(
                        "No speech detected in the voice message."
                    )

                elapsed_ms = int((time.perf_counter() - start) * 1000)
                estimated_cost = self._estimate_cost(duration_seconds)
                logger.info(
                    "Whisper transcription succeeded (%sms), model=%s, file=%s, estimated_cost_usd=%.6f",
                    elapsed_ms,
                    self.model,
                    audio_path.name,
                    estimated_cost,
                )
                return text
            except EmptyTranscriptionError:
                raise
            except Exception as exc:
                if attempt >= self.max_retries:
                    logger.error(
                        "Whisper transcription failed after %s attempt(s): %s",
                        self.max_retries,
                        exc,
                        exc_info=True,
                    )
                    raise TranscriptionError(
                        "Unable to transcribe audio right now. Please try again."
                    ) from exc

                backoff = self.initial_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Whisper transcription attempt %s/%s failed: %s. Retrying in %.2fs.",
                    attempt,
                    self.max_retries,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

        raise TranscriptionError(
            "Unable to transcribe audio right now. Please try again."
        )

    async def _call_whisper(self, audio_path: Path) -> Any:
        if hasattr(self.client, "audio") and hasattr(
            self.client.audio, "transcriptions"
        ):
            with audio_path.open("rb") as audio_file:
                return await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                )

        if hasattr(self.client, "Audio") and hasattr(self.client.Audio, "atranscribe"):
            with audio_path.open("rb") as audio_file:
                return await self.client.Audio.atranscribe(self.model, audio_file)

        raise TranscriptionError(
            "Unsupported OpenAI client interface for Whisper transcription."
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            return str(response.get("text", ""))
        text = getattr(response, "text", "")
        return str(text)

    @staticmethod
    def _estimate_cost(duration_seconds: Optional[int]) -> float:
        if not duration_seconds or duration_seconds <= 0:
            return 0.0
        minutes = duration_seconds / 60
        return minutes * WHISPER_PRICE_PER_MINUTE_USD


class VolcengineFileFastTranscriber:
    """Volcengine bigmodel file ASR wrapper using submit/query workflow."""

    def __init__(
        self,
        app_id: Optional[str],
        token: Optional[str],
        cluster: Optional[str] = VOLCENGINE_DEFAULT_CLUSTER,
        resource_id: str = VOLCENGINE_DEFAULT_RESOURCE_ID,
        model_name: str = VOLCENGINE_DEFAULT_MODEL_NAME,
        submit_endpoint: str = VOLCENGINE_SUBMIT_ENDPOINT,
        query_endpoint: str = VOLCENGINE_QUERY_ENDPOINT,
        request_timeout: float = 20.0,
        request_sender: Optional[
            Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]
        ] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        poll_interval_seconds: float = 2.0,
        max_poll_seconds: float = 300.0,
    ) -> None:
        self.app_id = (app_id or "").strip()
        self.token = (token or "").strip()
        self.cluster = (cluster or "").strip() or VOLCENGINE_DEFAULT_CLUSTER
        self.resource_id = (resource_id or "").strip() or VOLCENGINE_DEFAULT_RESOURCE_ID
        self.model_name = (model_name or "").strip() or VOLCENGINE_DEFAULT_MODEL_NAME
        self.submit_endpoint = (
            submit_endpoint or ""
        ).strip() or VOLCENGINE_SUBMIT_ENDPOINT
        self.query_endpoint = (
            query_endpoint or ""
        ).strip() or VOLCENGINE_QUERY_ENDPOINT
        self.request_timeout = max(1.0, float(request_timeout))
        self.max_retries = max(1, int(max_retries))
        self.initial_backoff = max(0.1, float(initial_backoff))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self.max_poll_seconds = max(1.0, float(max_poll_seconds))
        self.request_sender = request_sender or self._default_request_sender

        if not self.app_id:
            raise ValueError(
                "VOLCENGINE_APP_ID is required for Volcengine transcription."
            )
        if not self.token:
            raise ValueError(
                "VOLCENGINE_TOKEN is required for Volcengine transcription."
            )

    async def transcribe_audio(
        self, audio_url: str, duration_seconds: Optional[int] = None
    ) -> str:
        """Transcribe an audio URL with retries and validation."""
        normalized_url = (audio_url or "").strip()
        if not normalized_url:
            raise ValueError("audio_url is required for Volcengine transcription.")

        start = time.perf_counter()
        for attempt in range(1, self.max_retries + 1):
            try:
                task_id = await self._submit_task(normalized_url)
                response = await self._poll_task_result(task_id)
                text = self._extract_text(response).strip()
                if not text:
                    raise EmptyTranscriptionError(
                        "No speech detected in the voice message."
                    )

                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.info(
                    "Volcengine transcription succeeded (%sms), task_id=%s",
                    elapsed_ms,
                    task_id,
                )
                return text
            except EmptyTranscriptionError:
                raise
            except Exception as exc:
                if attempt >= self.max_retries:
                    logger.error(
                        "Volcengine transcription failed after %s attempt(s): %s",
                        self.max_retries,
                        exc,
                        exc_info=True,
                    )
                    raise TranscriptionError(
                        "Unable to transcribe audio right now. Please try again."
                    ) from exc

                backoff = self.initial_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Volcengine transcription attempt %s/%s failed: %s. Retrying in %.2fs.",
                    attempt,
                    self.max_retries,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

        raise TranscriptionError(
            "Unable to transcribe audio right now. Please try again."
        )

    def _build_headers(self, request_id: str, include_sequence: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": self.app_id,
            "X-Api-Access-Key": self.token,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id,
        }
        if include_sequence:
            headers["X-Api-Sequence"] = "-1"
        return headers

    async def _submit_task(self, audio_url: str) -> str:
        task_id = str(uuid.uuid4())
        payload = {
            "user": {"uid": f"telegram-{uuid.uuid4().hex}"},
            "audio": {
                "url": audio_url,
                "format": self._infer_audio_format(audio_url),
            },
            "request": {"model_name": self.model_name},
        }
        headers = self._build_headers(task_id, include_sequence=True)
        response = await self._call_volcengine(self.submit_endpoint, headers, payload)
        code = self._normalize_code(response.get("api_status_code"))
        message = str(response.get("api_message", "")).strip() or "Unknown error"
        if code != VOLCENGINE_SUCCESS_CODE:
            raise RuntimeError(
                f"Volcengine ASR submit failed with status {code}: {message}"
            )
        return task_id

    async def _poll_task_result(self, task_id: str) -> dict[str, Any]:
        deadline = time.perf_counter() + self.max_poll_seconds
        payload: dict[str, Any] = {}
        headers = self._build_headers(task_id, include_sequence=False)

        while True:
            response = await self._call_volcengine(
                self.query_endpoint, headers, payload
            )
            code = self._normalize_code(response.get("api_status_code"))
            message = str(response.get("api_message", "")).strip() or "Unknown error"

            if code == VOLCENGINE_SUCCESS_CODE:
                body = response.get("body")
                if not isinstance(body, dict):
                    raise RuntimeError("Volcengine ASR query response body is invalid.")
                return body
            if code in VOLCENGINE_PROCESSING_CODES:
                if time.perf_counter() >= deadline:
                    raise TimeoutError(
                        f"Volcengine ASR query timed out after {self.max_poll_seconds:.1f}s."
                    )
                await asyncio.sleep(self.poll_interval_seconds)
                continue
            raise RuntimeError(
                f"Volcengine ASR query failed with status {code}: {message}"
            )

    async def _call_volcengine(
        self, endpoint: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        sender = self.request_sender
        if asyncio.iscoroutinefunction(sender):
            response = await sender(endpoint, headers, payload, self.request_timeout)
        else:
            response = await asyncio.to_thread(
                sender, endpoint, headers, payload, self.request_timeout
            )

        if not isinstance(response, dict):
            raise RuntimeError("Volcengine ASR response is invalid.")

        return response

    @staticmethod
    def _default_request_sender(
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        request_body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **headers}
        request = urllib_request.Request(
            endpoint,
            data=request_body,
            headers=request_headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
                if raw_text.strip():
                    try:
                        body = json.loads(raw_text)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            f"Invalid JSON response from Volcengine: {raw_text}"
                        ) from exc
                else:
                    body = {}

                return {
                    "body": body,
                    "api_status_code": response.headers.get("X-Api-Status-Code", ""),
                    "api_message": response.headers.get("X-Api-Message", ""),
                }
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Volcengine ASR HTTP error {exc.code}: {detail}"
            ) from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"Volcengine ASR network error: {exc.reason}") from exc

    @staticmethod
    def _normalize_code(raw_code: Any) -> Optional[int]:
        if raw_code is None:
            return None
        if isinstance(raw_code, int):
            return raw_code
        text = str(raw_code).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        result = response.get("result")
        if isinstance(result, dict):
            return str(result.get("text", ""))
        return ""

    @staticmethod
    def _infer_audio_format(audio_url: str) -> str:
        path = urllib_parse.urlparse(audio_url).path or ""
        ext = Path(path).suffix.lower().lstrip(".")
        if ext in {"wav", "ogg", "mp3", "mp4"}:
            return ext
        if ext in {"oga", "opus"}:
            return "ogg"
        return "ogg"
