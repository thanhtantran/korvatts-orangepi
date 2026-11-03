"""Small WSGI web service for KorvaTTS."""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
from pathlib import Path
from wsgiref.simple_server import make_server

MAX_TEXT_LENGTH = 500
STATIC_DIR = Path(__file__).with_name("web")


class App:
    def __init__(self, tts_factory=None):
        self._tts_factory = tts_factory
        self._tts = None
        self._lock = threading.Lock()

    def _get_tts(self):
        if self._tts is None:
            if self._tts_factory:
                self._tts = self._tts_factory()
            else:
                from korvatts import TTS

                self._tts = TTS(
                    assets_dir=os.environ.get("KORVATTS_ASSETS_DIR"),
                    device="cpu",
                    num_threads=int(os.environ.get("KORVATTS_THREADS", "2")),
                )
        return self._tts

    @staticmethod
    def _json(start_response, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        if method == "GET" and path == "/healthz":
            return self._json(start_response, "200 OK", {"status": "ok"})
        if method == "GET" and path == "/api/voices":
            return self._json(start_response, "200 OK", {"voices": self._get_tts().list_voices()})
        if method == "POST" and path == "/api/tts":
            return self._synthesize(environ, start_response)
        if method == "GET" and path == "/":
            return self._file(start_response, STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if method == "GET" and path == "/app.js":
            return self._file(start_response, STATIC_DIR / "app.js", "text/javascript; charset=utf-8")
        return self._json(start_response, "404 Not Found", {"error": "not found"})

    def _synthesize(self, environ, start_response):
        try:
            size = int(environ.get("CONTENT_LENGTH") or 0)
            data = json.loads(environ["wsgi.input"].read(size) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(start_response, "400 Bad Request", {"error": "invalid JSON"})
        text = str(data.get("text", "")).strip()
        if not text:
            return self._json(start_response, "400 Bad Request", {"error": "text is required"})
        if len(text) > MAX_TEXT_LENGTH:
            return self._json(start_response, "400 Bad Request", {"error": f"text is too long (max {MAX_TEXT_LENGTH})"})
        voice = str(data.get("voice", "khanh_vy"))
        speed = float(data.get("speed", 1.05))
        try:
            with self._lock:
                tts = self._get_tts()
                wav, _ = tts.synthesize(text, voice=voice, lang="vi", total_steps=16, speed=speed)
                with tempfile.NamedTemporaryFile(suffix=".wav") as output:
                    tts.save_audio(wav, output.name)
                    body = output.read()
        except (ValueError, FileNotFoundError) as error:
            return self._json(start_response, "400 Bad Request", {"error": str(error)})
        except Exception:
            return self._json(start_response, "500 Internal Server Error", {"error": "speech synthesis failed"})
        start_response("200 OK", [("Content-Type", "audio/wav"), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")])
        return [body]

    @staticmethod
    def _file(start_response, path, content_type):
        body = path.read_bytes()
        start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return [body]


def main():
    port = int(os.environ.get("PORT", "8080"))
    with make_server("0.0.0.0", port, App()) as server:
        print(f"KorvaTTS web service listening on {port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
