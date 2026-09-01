#!/usr/bin/env python3
"""Map Speech Central voice aliases and proxy Qwen3-TTS responses."""

from __future__ import annotations

import http.client
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import SplitResult, urlsplit


DEFAULT_VOICE_MAP = {
    "alloy": "Uncle_Fu",
    "echo": "Dylan",
    "fable": "Eric",
    "onyx": "Uncle_Fu",
    "ash": "Dylan",
    "ballad": "Eric",
    "cedar": "Uncle_Fu",
    "verse": "Dylan",
    "coral": "Vivian",
    "marin": "Serena",
    "nova": "Vivian",
    "sage": "Serena",
    "shimmer": "Vivian",
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
REQUEST_HEADER_ALLOWLIST = {"accept", "authorization", "user-agent"}
RESPONSE_HEADER_DENYLIST = HOP_BY_HOP_HEADERS | {"date", "server"}

LOGGER = logging.getLogger("qwen3-tts-shim")


def load_voice_map(raw_json: str | None) -> dict[str, str]:
    """Load an optional full or partial alias override."""
    voice_map = dict(DEFAULT_VOICE_MAP)
    if not raw_json:
        return voice_map

    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("VOICE_MAP_JSON must be a JSON object")

    for alias, speaker in parsed.items():
        if not isinstance(alias, str) or not alias.strip():
            raise ValueError("VOICE_MAP_JSON aliases must be non-empty strings")
        if not isinstance(speaker, str) or not speaker.strip():
            raise ValueError("VOICE_MAP_JSON speakers must be non-empty strings")
        voice_map[alias.casefold()] = speaker.strip()
    return voice_map


VOICE_MAP = load_voice_map(os.getenv("VOICE_MAP_JSON"))
NATIVE_VOICES = {speaker.casefold(): speaker for speaker in set(VOICE_MAP.values())}
RESPONSE_FORMAT_ALIASES = {"aac": "mp3"}


def resolve_voice(value: object) -> str:
    """Resolve an alias or native speaker and fall back to alloy."""
    requested = "" if value is None else str(value).strip()
    normalized = requested.casefold()
    if normalized in VOICE_MAP:
        return VOICE_MAP[normalized]
    if normalized in NATIVE_VOICES:
        return NATIVE_VOICES[normalized]
    return VOICE_MAP["alloy"]


def parse_upstream(raw_url: str) -> SplitResult:
    """Validate the fixed upstream configured by the operator."""
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("UPSTREAM_URL must be an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment:
        raise ValueError("UPSTREAM_URL must not contain a query or fragment")
    return parsed


UPSTREAM = parse_upstream(os.getenv("UPSTREAM_URL", "http://server:8880"))
UPSTREAM_MODEL = os.getenv(
    "UPSTREAM_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
).strip()
if not UPSTREAM_MODEL:
    raise ValueError("UPSTREAM_MODEL must be a non-empty model identifier")
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(1024 * 1024)))
READ_CHUNK_BYTES = 64 * 1024


class ShimHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ShimHandler(BaseHTTPRequestHandler):
    """Minimal HTTP/1.1 reverse proxy that rewrites only the voice field."""

    protocol_version = "HTTP/1.1"
    server_version = "qwen3-tts-shim"

    def do_GET(self) -> None:  # noqa: N802
        if self._path_only() not in {"/health", "/v1/models"}:
            self._json_error(404, "not_found", "Endpoint not found")
            return
        self._proxy_request("GET", None)

    def do_POST(self) -> None:  # noqa: N802
        if self._path_only() != "/v1/audio/speech":
            self._json_error(404, "not_found", "Endpoint not found")
            return

        body = self._read_json_body()
        if body is None:
            return
        if not isinstance(body, dict):
            self._json_error(400, "invalid_request", "JSON body must be an object")
            return
        if not isinstance(body.get("input"), str) or not body["input"].strip():
            self._json_error(400, "invalid_input", "input must be a non-empty string")
            return

        body["model"] = UPSTREAM_MODEL
        body["voice"] = resolve_voice(body.get("voice"))
        response_format = body.get("response_format")
        if isinstance(response_format, str):
            body["response_format"] = RESPONSE_FORMAT_ALIASES.get(
                response_format.casefold(), response_format
            )
        if body.get("stream") is True:
            body.setdefault("response_format", "pcm")
            if body["response_format"] == "pcm":
                body.setdefault("stream_format", "audio")
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._proxy_request("POST", encoded)

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.address_string(), format_string % args)

    def _path_only(self) -> str:
        return urlsplit(self.path).path

    def _read_json_body(self) -> object | None:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").casefold()
        if transfer_encoding:
            self._json_error(400, "unsupported_transfer_encoding", "Chunked requests are not supported")
            return None

        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            self._json_error(411, "length_required", "Content-Length is required")
            return None
        if length > MAX_REQUEST_BYTES:
            self._json_error(413, "request_too_large", "Request body is too large")
            return None

        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json_error(400, "invalid_json", "Request body must be valid UTF-8 JSON")
            return None

    def _proxy_request(self, method: str, body: bytes | None) -> None:
        connection_class = (
            http.client.HTTPSConnection if UPSTREAM.scheme == "https" else http.client.HTTPConnection
        )
        port = UPSTREAM.port or (443 if UPSTREAM.scheme == "https" else 80)
        connection = connection_class(UPSTREAM.hostname, port, timeout=600)
        response_started = False

        upstream_path = f"{UPSTREAM.path.rstrip('/')}{self.path}"
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.casefold() in REQUEST_HEADER_ALLOWLIST
        }
        headers["Host"] = UPSTREAM.netloc
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))

        try:
            connection.request(method, upstream_path, body=body, headers=headers)
            upstream_response = connection.getresponse()
            upstream_length = upstream_response.getheader("Content-Length")

            self.send_response(upstream_response.status, upstream_response.reason)
            for name, value in upstream_response.getheaders():
                if name.casefold() not in RESPONSE_HEADER_DENYLIST and name.casefold() != "content-length":
                    self.send_header(name, value)
            if upstream_length is not None:
                self.send_header("Content-Length", upstream_length)
            else:
                self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            response_started = True

            while chunk := upstream_response.read(READ_CHUNK_BYTES):
                if upstream_length is None:
                    self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                else:
                    self.wfile.write(chunk)
                self.wfile.flush()
            if upstream_length is None:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.info("Client disconnected while proxying %s", self.path)
        except (OSError, http.client.HTTPException) as exc:
            LOGGER.error("Upstream request failed: %s", exc)
            if not response_started:
                self._json_error(502, "upstream_unavailable", "Qwen3-TTS backend is unavailable")
        finally:
            self.close_connection = True
            connection.close()

    def _json_error(self, status: int, error: str, message: str) -> None:
        payload = json.dumps(
            {"error": {"code": error, "message": message, "type": "invalid_request_error"}},
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    bind_host = os.getenv("HOST", "0.0.0.0")
    bind_port = int(os.getenv("PORT", "8090"))
    server = ShimHTTPServer((bind_host, bind_port), ShimHandler)
    LOGGER.info("Listening on %s:%d and proxying to %s", bind_host, bind_port, UPSTREAM.geturl())
    server.serve_forever()


if __name__ == "__main__":
    main()
