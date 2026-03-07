import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from telegram_bot.utils.tos_uploader import TOSUploadError, VolcengineTOSUploader


class _FakeTOSClient:
    def __init__(self, *, put_error=None, sign_error=None, signed_url=""):
        self.put_error = put_error
        self.sign_error = sign_error
        self.signed_url = signed_url
        self.put_calls = []
        self.sign_calls = []

    def put_object_from_file(self, **kwargs):
        self.put_calls.append(kwargs)
        if self.put_error is not None:
            raise self.put_error
        return SimpleNamespace()

    def pre_signed_url(self, http_method, **kwargs):
        self.sign_calls.append((http_method, kwargs))
        if self.sign_error is not None:
            raise self.sign_error
        return SimpleNamespace(signed_url=self.signed_url)


class TOSUploaderTests(unittest.TestCase):
    def test_upload_file_returns_signed_url(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "voice.ogg"
            path.write_bytes(b"OggS")

            client = _FakeTOSClient(
                signed_url="https://tos.example.com/bucket/voice.ogg?X-Tos-Signature=abc"
            )
            uploader = VolcengineTOSUploader(
                access_key="ak",
                secret_access_key="sk",
                endpoint="https://tos-cn-shanghai.volces.com",
                region="cn-shanghai",
                bucket_name="voice-stage",
                signed_url_ttl_seconds=1200,
                client=client,
                http_method_get="GET",
            )

            signed_url = uploader.upload_file(path, user_id=42)

            self.assertEqual(
                signed_url,
                "https://tos.example.com/bucket/voice.ogg?X-Tos-Signature=abc",
            )
            self.assertEqual(len(client.put_calls), 1)
            self.assertEqual(client.put_calls[0]["bucket"], "voice-stage")
            self.assertEqual(client.put_calls[0]["file_path"], str(path))
            object_key = client.put_calls[0]["key"]
            self.assertTrue(object_key.startswith("telegram-voice/42/"))
            self.assertTrue(object_key.endswith(".ogg"))

            self.assertEqual(len(client.sign_calls), 1)
            method, kwargs = client.sign_calls[0]
            self.assertEqual(method, "GET")
            self.assertEqual(kwargs["bucket"], "voice-stage")
            self.assertEqual(kwargs["key"], object_key)
            self.assertEqual(kwargs["expires"], 1200)

    def test_upload_file_raises_when_upload_fails(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "voice.ogg"
            path.write_bytes(b"OggS")

            client = _FakeTOSClient(put_error=RuntimeError("upload failed"))
            uploader = VolcengineTOSUploader(
                access_key="ak",
                secret_access_key="sk",
                endpoint="https://tos-cn-guangzhou.volces.com",
                region="cn-guangzhou",
                bucket_name="voice-stage",
                client=client,
            )

            with self.assertRaises(TOSUploadError):
                uploader.upload_file(path, user_id=7)

    def test_upload_file_raises_when_signing_fails(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "voice.ogg"
            path.write_bytes(b"OggS")

            client = _FakeTOSClient(sign_error=RuntimeError("sign failed"))
            uploader = VolcengineTOSUploader(
                access_key="ak",
                secret_access_key="sk",
                endpoint="https://tos-cn-shanghai.volces.com",
                region="cn-shanghai",
                bucket_name="voice-stage",
                client=client,
            )

            with self.assertRaises(TOSUploadError):
                uploader.upload_file(path, user_id=7)

    def test_requires_tos_endpoint(self):
        with self.assertRaises(ValueError):
            VolcengineTOSUploader(
                access_key="ak",
                secret_access_key="sk",
                endpoint="",
                region="cn-shanghai",
                bucket_name="voice-stage",
                client=_FakeTOSClient(),
            )

    def test_redact_signed_url(self):
        url = "https://tos.example.com/path/file.ogg?X-Tos-Algorithm=AWS4&X-Tos-Signature=abc"
        self.assertEqual(
            VolcengineTOSUploader.redact_signed_url(url),
            "https://tos.example.com/path/file.ogg?***REDACTED***",
        )


if __name__ == "__main__":
    unittest.main()
