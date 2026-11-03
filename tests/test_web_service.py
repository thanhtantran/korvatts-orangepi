import io
import json
import unittest
from unittest.mock import patch

from web_service import App, MAX_TEXT_LENGTH


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
        self.app = App(tts_factory=FakeTTS)

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        headers = {"CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json"}
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
