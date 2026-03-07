import hashlib
import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


class TOSUploadError(RuntimeError):
    """Raised when uploading or signing a TOS object fails."""


class VolcengineTOSUploader:
    """Upload local voice files to Volcengine TOS and return signed URLs."""

    def __init__(
        self,
        access_key: Optional[str],
        secret_access_key: Optional[str],
        endpoint: str,
        region: str,
        bucket_name: Optional[str],
        signed_url_ttl_seconds: int = 900,
        client: Optional[Any] = None,
        client_factory: Optional[Callable[..., Any]] = None,
        http_method_get: Optional[Any] = None,
    ) -> None:
        self.access_key = (access_key or "").strip()
        self.secret_access_key = (secret_access_key or "").strip()
        self.endpoint = (endpoint or "").strip()
        self.region = (region or "").strip()
        self.bucket_name = (bucket_name or "").strip()
        self.signed_url_ttl_seconds = int(signed_url_ttl_seconds)

        if not self.access_key:
            raise ValueError("VOLCENGINE_ACCESS_KEY is required for TOS upload.")
        if not self.secret_access_key:
            raise ValueError("VOLCENGINE_SECRET_ACCESS_KEY is required for TOS upload.")
        if not self.bucket_name:
            raise ValueError("VOLCENGINE_TOS_BUCKET_NAME is required for TOS upload.")
        if not self.endpoint:
            raise ValueError("VOLCENGINE_TOS_ENDPOINT is required for TOS upload.")
        if not self.region:
            raise ValueError("VOLCENGINE_TOS_REGION is required for TOS upload.")
        if self.signed_url_ttl_seconds <= 0:
            raise ValueError("VOLCENGINE_TOS_SIGNED_URL_TTL_SECONDS must be positive.")

        self._client: Any = client
        self._http_method_get = http_method_get

        if self._client is None:
            if client_factory is not None:
                self._client = client_factory(
                    ak=self.access_key,
                    sk=self.secret_access_key,
                    endpoint=self.endpoint,
                    region=self.region,
                )
                self._http_method_get = self._http_method_get or "GET"
            else:
                try:
                    import tos  # type: ignore
                except ImportError as exc:
                    raise RuntimeError(
                        "tos package is not installed. Install dependency 'tos'."
                    ) from exc

                self._client = tos.TosClientV2(
                    ak=self.access_key,
                    sk=self.secret_access_key,
                    endpoint=self.endpoint,
                    region=self.region,
                )
                self._http_method_get = (
                    self._http_method_get or tos.HttpMethodType.Http_Method_Get
                )
        else:
            self._http_method_get = self._http_method_get or "GET"

    def upload_file(self, local_path: Path, user_id: int) -> str:
        source = Path(local_path)
        suffix = source.suffix or ".ogg"
        object_key = self._build_object_key(source, user_id, suffix)

        try:
            self._client.put_object_from_file(
                bucket=self.bucket_name,
                key=object_key,
                file_path=str(source),
            )
        except Exception as exc:
            raise TOSUploadError(
                "Failed to upload voice file to Volcengine TOS."
            ) from exc

        try:
            signed = self._client.pre_signed_url(
                self._http_method_get,
                bucket=self.bucket_name,
                key=object_key,
                expires=self.signed_url_ttl_seconds,
            )
        except Exception as exc:
            raise TOSUploadError(
                "Failed to create signed URL for Volcengine TOS object."
            ) from exc

        signed_url = self._extract_signed_url(signed)
        logger.debug(
            "Uploaded voice file to Volcengine TOS bucket=%s key=%s signed_url=%s",
            self.bucket_name,
            object_key,
            self.redact_signed_url(signed_url),
        )
        return signed_url

    @staticmethod
    def _build_object_key(source: Path, user_id: int, suffix: str) -> str:
        seed = (
            f"{user_id}:{source.name}:{time.time_ns()}:{uuid.uuid4().hex}:"
            f"{secrets.token_hex(16)}"
        ).encode("utf-8")
        hash_suffix = hashlib.sha256(seed).hexdigest()[:24]
        return f"telegram-voice/{user_id}/{hash_suffix}{suffix}"

    @staticmethod
    def _extract_signed_url(signed: Any) -> str:
        if isinstance(signed, str):
            value = signed
        else:
            value = str(getattr(signed, "signed_url", "") or "")

        if not value.strip():
            raise TOSUploadError("Volcengine TOS signed URL is empty.")
        return value.strip()

    @staticmethod
    def redact_signed_url(url: str) -> str:
        parsed = urlparse(url)
        redacted_query = "***REDACTED***" if parsed.query else ""
        return urlunparse(parsed._replace(query=redacted_query))
