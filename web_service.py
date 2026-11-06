"""Small WSGI web service for KorvaTTS."""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
from pathlib import Path
import sys
import hmac
import hashlib
from http.cookies import SimpleCookie
from wsgiref.simple_server import make_server

APP_DIR = Path(__file__).parent
DEPS_DIR = APP_DIR / "deps"
if DEPS_DIR.is_dir():
    sys.path.insert(0, str(DEPS_DIR))

MAX_TEXT_LENGTH = 500
STATIC_DIR = APP_DIR / "web"


def load_env_file(path: Path) -> None:
    """Load a small KEY=VALUE config file without overriding process env."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


class App:
    def __init__(self, tts_factory=None, api_token: str | None = None, web_enabled: bool | None = None):
        self._tts_factory = tts_factory
        self._tts = None
        self._lock = threading.Lock()
        self._api_token = api_token if api_token is not None else os.environ.get("KORVATTS_API_TOKEN", "")
        self._web_enabled = web_enabled if web_enabled is not None else os.environ.get("KORVATTS_WEB_ENABLED", "true").lower() == "true"

    def _bearer_authorized(self, environ) -> bool:
        value = environ.get("HTTP_AUTHORIZATION", "")
        expected = f"Bearer {self._api_token}"
        return bool(self._api_token) and hmac.compare_digest(value, expected)

    def _web_authorized(self, environ) -> bool:
        if not self._web_enabled or not self._api_token:
            return False
        cookie = SimpleCookie(environ.get("HTTP_COOKIE", "")).get("korvatts_web_session")
        return bool(cookie) and hmac.compare_digest(cookie.value, self._session_value())

    def _session_value(self) -> str:
        return hmac.new(self._api_token.encode(), b"korvatts-web-session", hashlib.sha256).hexdigest()

    def _web_session_header(self) -> tuple[str, str]:
        return ("Set-Cookie", f"korvatts_web_session={self._session_value()}; Path=/; HttpOnly; SameSite=Strict")

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
        if path.startswith("/api/") and not self._bearer_authorized(environ):
            body = json.dumps({"error": "authorization required"}).encode("utf-8")
            start_response("401 Unauthorized", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("WWW-Authenticate", "Bearer")])
            return [body]
        if path.startswith("/web-api/") and not self._web_authorized(environ):
            return self._json(start_response, "401 Unauthorized", {"error": "web session required"})
        if method == "GET" and path == "/api/voices":
            return self._json(start_response, "200 OK", {"voices": self._get_tts().list_voices()})
        if method == "POST" and path == "/api/tts":
            return self._synthesize(environ, start_response)
        if method == "GET" and path == "/web-api/voices":
            return self._json(start_response, "200 OK", {"voices": self._get_tts().list_voices()})
        if method == "POST" and path == "/web-api/tts":
            return self._synthesize(environ, start_response)
        if method == "GET" and path == "/":
            if not self._web_enabled:
                body = "<!doctype html><html lang=\"vi\"><meta charset=\"utf-8\"><title>KorvaTTS</title><main><h1>Chế độ web đã tắt.</h1><p>API KorvaTTS vẫn đang hoạt động.</p></main></html>".encode("utf-8")
                start_response("403 Forbidden", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
                return [body]
            return self._file(start_response, STATIC_DIR / "index.html", "text/html; charset=utf-8", [self._web_session_header()])
        if method == "GET" and path == "/app.js":
            if not self._web_enabled:
                return self._json(start_response, "403 Forbidden", {"message": "Chế độ web đã tắt."})
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
    def _file(start_response, path, content_type, extra_headers=None):
        body = path.read_bytes()
        headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))]
        if extra_headers:
            headers.extend(extra_headers)
        start_response("200 OK", headers)
        return [body]


def main():
    load_env_file(APP_DIR / ".env")
    port = int(os.environ.get("PORT", "8080"))
    api_token = os.environ.get("KORVATTS_API_TOKEN", "")
    if not api_token:
        raise RuntimeError("KORVATTS_API_TOKEN must be set")
    with make_server("0.0.0.0", port, App(api_token=api_token)) as server:
        print(f"KorvaTTS web service listening on {port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
