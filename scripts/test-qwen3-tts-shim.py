#!/usr/bin/env python3
"""Standard-library tests for the local Qwen3-TTS shim."""

from __future__ import annotations

import http.client
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SHIM_PATH = (
    REPOSITORY_ROOT
    / "ansible"
    / "roles"
    / "qwen3-tts"
    / "files"
    / "qwen3-tts-shim.py"
)
SPEC = importlib.util.spec_from_file_location("qwen3_tts_shim", SHIM_PATH)
assert SPEC and SPEC.loader
SHIM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHIM)


class MockUpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict[str, object]] = []

    def do_GET(self) -> None:  # noqa: N802
        payload = json.dumps({"path": self.path}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        self.requests.append(request)
        if request.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "audio/pcm")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in (b"first", b"second"):
                self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii") + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return

        if request.get("response_format") == "mp3":
            payload = b"ID3mockMP3"
            content_type = "audio/mpeg"
        else:
            payload = b"RIFFmockWAVE"
            content_type = "audio/wav"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string: str, *args: object) -> None:
        return


class ShimTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
        upstream_port = cls.upstream.server_address[1]
        SHIM.UPSTREAM = urlsplit(f"http://127.0.0.1:{upstream_port}")
        SHIM.UPSTREAM_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()

        cls.shim = SHIM.ShimHTTPServer(("127.0.0.1", 0), SHIM.ShimHandler)
        cls.shim_port = cls.shim.server_address[1]
        cls.shim_thread = threading.Thread(target=cls.shim.serve_forever, daemon=True)
        cls.shim_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.shim.shutdown()
        cls.shim.server_close()
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def setUp(self) -> None:
        MockUpstreamHandler.requests.clear()

    def request(self, method: str, path: str, body: dict[str, object] | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.shim_port, timeout=5)
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if encoded is not None else {}
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        response_headers = dict(response.getheaders())
        connection.close()
        return response.status, response_headers, payload

    def test_all_aliases_resolve_to_expected_speakers(self) -> None:
        for alias, speaker in SHIM.DEFAULT_VOICE_MAP.items():
            with self.subTest(alias=alias):
                self.assertEqual(SHIM.resolve_voice(alias.upper()), speaker)

    def test_native_voice_passes_through_and_unknown_falls_back(self) -> None:
        self.assertEqual(SHIM.resolve_voice("serena"), "Serena")
        self.assertEqual(SHIM.resolve_voice("unknown"), "Uncle_Fu")
        self.assertEqual(SHIM.resolve_voice(None), "Uncle_Fu")

    def test_non_streaming_request_rewrites_model_and_voice(self) -> None:
        request = {
            "model": "tts-1",
            "voice": "nova",
            "input": "你好。",
            "response_format": "wav",
            "speed": 1.25,
        }
        status, headers, payload = self.request("POST", "/v1/audio/speech", request)

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertEqual(payload, b"RIFFmockWAVE")
        self.assertEqual(
            MockUpstreamHandler.requests,
            [
                {
                    **request,
                    "model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                    "voice": "Vivian",
                }
            ],
        )

    def test_streaming_response_remains_chunked(self) -> None:
        status, headers, payload = self.request(
            "POST",
            "/v1/audio/speech",
            {"model": "tts-1", "voice": "alloy", "input": "Hello.", "stream": True},
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/pcm")
        self.assertEqual(headers["Transfer-Encoding"], "chunked")
        self.assertEqual(payload, b"firstsecond")
        self.assertEqual(
            MockUpstreamHandler.requests[0]["model"],
            "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        )
        self.assertEqual(MockUpstreamHandler.requests[0]["voice"], "Uncle_Fu")
        self.assertEqual(MockUpstreamHandler.requests[0]["stream_format"], "audio")

    def test_speech_central_aac_request_uses_supported_mp3_format(self) -> None:
        status, headers, payload = self.request(
            "POST",
            "/v1/audio/speech",
            {
                "model": "tts-1",
                "voice": "coral",
                "input": "你好。",
                "response_format": "aac",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/mpeg")
        self.assertEqual(payload, b"ID3mockMP3")
        self.assertEqual(MockUpstreamHandler.requests[0]["response_format"], "mp3")
        self.assertEqual(MockUpstreamHandler.requests[0]["voice"], "Vivian")

    def test_health_and_models_are_proxied(self) -> None:
        for path in ("/health", "/v1/models"):
            with self.subTest(path=path):
                status, headers, payload = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(json.loads(payload), {"path": path})

    def test_invalid_input_is_rejected_before_upstream(self) -> None:
        status, _, payload = self.request(
            "POST", "/v1/audio/speech", {"model": "tts-1", "voice": "alloy", "input": " "}
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(payload)["error"]["code"], "invalid_input")
        self.assertEqual(MockUpstreamHandler.requests, [])


if __name__ == "__main__":
    unittest.main()
