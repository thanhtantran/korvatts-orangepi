import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from web_service import App, MAX_TEXT_LENGTH
from korvatts.assets import resolve_assets_dir


class FakeTTS:
    sample_rate = 44_100

    def list_voices(self):
        return ["bao_kim", "khanh_vy"]

    def synthesize(self, text, voice, lang, total_steps, speed):
        return b"fake-wave", 1.25

    def save_audio(self, wav, output):
        with open(output, "wb") as handle:
            handle.write(wav)


class WebServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = App(tts_factory=FakeTTS, api_token="test-token")

    def request(self, method, path, payload=None, token="test-token"):
        body = json.dumps(payload).encode() if payload is not None else b""
        headers = {"CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json"}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        status = {}

        def start_response(code, response_headers):
            status["code"] = code
            status["headers"] = dict(response_headers)

        result = b"".join(self.app({"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO(body), **headers}, start_response))
        return status, result

    def browser_request(self, method, path, payload=None, cookie=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        headers = {"CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json"}
        if cookie:
            headers["HTTP_COOKIE"] = cookie
        status = {}

        def start_response(code, response_headers):
            status["code"] = code
            status["headers"] = dict(response_headers)

        result = b"".join(self.app({"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO(body), **headers}, start_response))
        return status, result

    def test_health_endpoint_is_ready_without_loading_model(self):
        status, body = self.request("GET", "/healthz")

        self.assertEqual("200 OK", status["code"])
        self.assertEqual({"status": "ok"}, json.loads(body))

    def test_api_rejects_missing_bearer_token(self):
        status, body = self.request("GET", "/api/voices", token=None)

        self.assertEqual("401 Unauthorized", status["code"])
        self.assertEqual("Bearer", status["headers"]["WWW-Authenticate"])
        self.assertIn("authorization", json.loads(body)["error"])

    def test_api_rejects_invalid_bearer_token(self):
        status, body = self.request("GET", "/api/voices", token="wrong")

        self.assertEqual("401 Unauthorized", status["code"])
        self.assertIn("authorization", json.loads(body)["error"])

    def test_enabled_web_ui_sets_session_that_can_call_api_without_bearer(self):
        status, _ = self.browser_request("GET", "/")
        cookie = status["headers"]["Set-Cookie"].split(";", 1)[0]

        status, body = self.browser_request("GET", "/web-api/voices", cookie=cookie)

        self.assertEqual("200 OK", status["code"])
        self.assertEqual(["bao_kim", "khanh_vy"], json.loads(body)["voices"])

        status, _ = self.browser_request("GET", "/api/voices", cookie=cookie)
        self.assertEqual("401 Unauthorized", status["code"])

    def test_disabled_web_returns_message_but_api_remains_available(self):
        app = App(tts_factory=FakeTTS, api_token="test-token", web_enabled=False)
        status = {}

        def start_response(code, response_headers):
            status["code"] = code

        body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/", "wsgi.input": io.BytesIO()}, start_response))
        self.assertEqual("403 Forbidden", status["code"])
        self.assertIn("Chế độ web đã tắt.", body.decode("utf-8"))

    def test_offline_model_mode_rejects_missing_local_assets(self):
        with TemporaryDirectory() as directory:
            previous_online = os.environ.get("HF_MODEL_ONLINE")
            previous_assets = os.environ.pop("KORVATTS_ASSETS_DIR", None)
            previous_cwd = Path.cwd()
            os.environ["HF_MODEL_ONLINE"] = "false"
            os.chdir(directory)
            try:
                with self.assertRaises(FileNotFoundError):
                    resolve_assets_dir(auto_download=True)
            finally:
                os.chdir(previous_cwd)
                if previous_online is None:
                    os.environ.pop("HF_MODEL_ONLINE", None)
                else:
                    os.environ["HF_MODEL_ONLINE"] = previous_online
                if previous_assets is not None:
                    os.environ["KORVATTS_ASSETS_DIR"] = previous_assets

    def test_voices_endpoint_returns_available_voices(self):
        status, body = self.request("GET", "/api/voices")

        self.assertEqual("200 OK", status["code"])
        self.assertEqual(["bao_kim", "khanh_vy"], json.loads(body)["voices"])

    def test_synthesis_returns_wav_data(self):
        status, body = self.request("POST", "/api/tts", {"text": "Xin chào", "voice": "khanh_vy"})

        self.assertEqual("200 OK", status["code"])
        self.assertEqual("audio/wav", status["headers"]["Content-Type"])
        self.assertEqual(b"fake-wave", body)

    def test_synthesis_rejects_text_over_limit(self):
        status, body = self.request("POST", "/api/tts", {"text": "a" * (MAX_TEXT_LENGTH + 1), "voice": "khanh_vy"})

        self.assertEqual("400 Bad Request", status["code"])
        self.assertIn("too long", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
