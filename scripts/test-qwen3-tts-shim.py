#!/usr/bin/env python3
"""Standard-library tests for the local Qwen3-TTS shim."""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SHIM_PATH = (
    REPOSITORY_ROOT
    / "ansible"
    / "roles"
    / "qwen3-tts"
    / "files"
    / "qwen3-tts-shim.py"
)
PROFILE_BOOTSTRAP_PATH = (
    REPOSITORY_ROOT
    / "ansible"
    / "roles"
    / "qwen3-tts"
    / "files"
    / "qwen3-tts-profile-bootstrap.py"
)
SPEC = importlib.util.spec_from_file_location("qwen3_tts_shim", SHIM_PATH)
assert SPEC and SPEC.loader
SHIM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHIM)

EXPECTED_VOICE_ALIASES = {
    "alloy": "Uncle_Fu",
    "echo": "Dylan",
    "fable": "Aiden",
    "onyx": "Uncle_Fu",
    "ash": "Eric",
    "ballad": "Dylan",
    "cedar": "Uncle_Fu",
    "verse": "Ryan",
    "coral": "Vivian",
    "marin": "Serena",
    "nova": "Sohee",
    "sage": "Serena",
    "shimmer": "Ono_Anna",
}
EXPECTED_PROFILE = "audiobook_narrator_zh"


def load_profile_bootstrap(profile: str, production_profile: str, directory: Path):
    environment = {
        "BASE_PROFILE": profile,
        "PROFILE_REFERENCE_FILE": str(directory / f"{profile}-reference.wav"),
        "PROFILE_REFERENCE_TEXT": "准确的候选参考转写。",
        "PROFILE_PROBE_FILE": str(directory / f"{profile}-clone.wav"),
        "PROFILE_PROBE_TEXT": "固定试听探针文本。",
        "VOICE_DESIGN_INSTRUCTIONS": "成熟、沉稳、低沉共鸣、自然的中文有声书旁白。",
        "VOICE_DESIGN_MODEL": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "BASE_MODEL": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "BASE_URL": "http://base.test",
        "VOICE_DESIGN_URL": "http://voice-design.test",
        "PRODUCTION_PROFILE": production_profile,
        "BOOTSTRAP_MODE": "candidate",
    }
    with mock.patch.dict(os.environ, environment, clear=False):
        spec = importlib.util.spec_from_file_location(f"profile_bootstrap_{profile}", PROFILE_BOOTSTRAP_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module._test_environment = environment
    return module


class MockUpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict[str, object]] = []
    profile_present = True
    malformed_voices = False
    voice_list_requests = 0

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/audio/voices":
            type(self).voice_list_requests += 1
            if self.malformed_voices:
                payload = json.dumps([]).encode("utf-8")
            else:
                uploaded = [{"name": EXPECTED_PROFILE}] if self.profile_present else []
                payload = json.dumps({"voices": [], "uploaded_voices": uploaded}).encode("utf-8")
        else:
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
        SHIM.UPSTREAM_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
        SHIM.BASE_PROFILE = EXPECTED_PROFILE
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
        MockUpstreamHandler.profile_present = True
        MockUpstreamHandler.malformed_voices = False
        MockUpstreamHandler.voice_list_requests = 0
        SHIM.reset_profile_ready_cache()

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

    def test_all_aliases_are_accepted_but_do_not_select_a_base_speaker(self) -> None:
        self.assertEqual(SHIM.DEFAULT_VOICE_ALIASES, EXPECTED_VOICE_ALIASES)
        for alias in EXPECTED_VOICE_ALIASES:
            with self.subTest(alias=alias):
                self.request("POST", "/v1/audio/speech", {"model": "tts-1", "voice": alias, "input": "你好。"})
                upstream = MockUpstreamHandler.requests[-1]
                self.assertEqual(upstream["task_type"], "Base")
                self.assertEqual(upstream["voice"], EXPECTED_PROFILE)
                self.assertEqual(upstream["language"], "Chinese")

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
                    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                    "voice": EXPECTED_PROFILE,
                    "task_type": "Base",
                    "language": "Chinese",
                }
            ],
        )

    def test_client_style_and_language_are_not_forwarded_to_base(self) -> None:
        self.request(
            "POST",
            "/v1/audio/speech",
            {
                "model": "tts-1",
                "voice": "alloy",
                "input": "你好。",
                "instructions": " ",
                "language": "English",
            },
        )
        self.assertNotIn("instructions", MockUpstreamHandler.requests[0])
        self.assertEqual(MockUpstreamHandler.requests[0]["language"], "Chinese")

    def test_unknown_alias_uses_the_same_base_profile(self) -> None:
        self.request("POST", "/v1/audio/speech", {"model": "tts-1", "voice": "unknown", "input": "你好。"})
        self.assertEqual(MockUpstreamHandler.requests[0]["voice"], EXPECTED_PROFILE)
        self.assertEqual(MockUpstreamHandler.requests[0]["task_type"], "Base")

    def test_profile_readiness_is_cached_across_adjacent_speech_requests(self) -> None:
        request = {"model": "tts-1", "voice": "alloy", "input": "你好。"}
        self.request("POST", "/v1/audio/speech", request)
        self.request("POST", "/v1/audio/speech", request)
        self.assertEqual(MockUpstreamHandler.voice_list_requests, 1)

    def test_missing_profile_returns_diagnostic_503_without_upstream_speech(self) -> None:
        MockUpstreamHandler.profile_present = False
        status, _, payload = self.request(
            "POST", "/v1/audio/speech", {"model": "tts-1", "voice": "alloy", "input": "你好。"}
        )
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(payload)["error"]["code"], "profile_unavailable")
        self.assertEqual(MockUpstreamHandler.requests, [])

    def test_health_reports_profile_unavailable(self) -> None:
        MockUpstreamHandler.profile_present = False
        status, _, payload = self.request("GET", "/health")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(payload)["error"]["code"], "profile_unavailable")

    def test_malformed_voice_listing_is_not_ready(self) -> None:
        MockUpstreamHandler.malformed_voices = True
        status, _, payload = self.request(
            "POST", "/v1/audio/speech", {"model": "tts-1", "voice": "alloy", "input": "你好。"}
        )
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(payload)["error"]["code"], "profile_unavailable")

    def test_https_profile_check_uses_default_port_443(self) -> None:
        class FakeResponse:
            status = 200

            def read(self):
                return json.dumps({"uploaded_voices": [{"name": EXPECTED_PROFILE}]}).encode()

        class FakeConnection:
            used_port = None

            def __init__(self, host, port, timeout):
                self.used_port = port
                FakeConnection.used_port = port

            def request(self, method, path):
                return None

            def getresponse(self):
                return FakeResponse()

            def close(self):
                return None

        original_upstream = SHIM.UPSTREAM
        original_connection = SHIM.http.client.HTTPSConnection
        try:
            SHIM.UPSTREAM = urlsplit("https://profile.example")
            SHIM.http.client.HTTPSConnection = FakeConnection
            handler = object.__new__(SHIM.ShimHandler)
            self.assertTrue(handler._profile_is_ready())
            self.assertEqual(FakeConnection.used_port, 443)
        finally:
            SHIM.UPSTREAM = original_upstream
            SHIM.http.client.HTTPSConnection = original_connection

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
            "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        )
        self.assertEqual(MockUpstreamHandler.requests[0]["voice"], EXPECTED_PROFILE)
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
        self.assertEqual(MockUpstreamHandler.requests[0]["voice"], EXPECTED_PROFILE)

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


class CandidateProfileBootstrapTestCase(unittest.TestCase):
    def test_candidate_uses_its_own_profile_and_fixed_probe_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            candidate = "audiobook_narrator_candidate_low_resonance"
            module = load_profile_bootstrap(candidate, EXPECTED_PROFILE, directory)
            module.REFERENCE.write_bytes(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 40)
            requests: list[tuple[str, dict[str, object]]] = []

            def fake_request(url: str, payload: dict[str, object]) -> bytes:
                requests.append((url, payload))
                return b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 40

            with mock.patch.dict(os.environ, module._test_environment, clear=False):
                with mock.patch.object(module, "registered_profile_exists", return_value=True):
                    with mock.patch.object(module, "request_json", side_effect=fake_request):
                        module.main()

            self.assertTrue(module.PROBE_FILE.is_file())
            self.assertEqual(module.PROBE_FILE.read_bytes()[:12], b"RIFF\x00\x00\x00\x00WAVE")
            self.assertEqual(requests, [("http://base.test/v1/audio/speech", {
                "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                "input": "固定试听探针文本。",
                "task_type": "Base",
                "voice": candidate,
                "language": "Chinese",
                "response_format": "wav",
            })])

    def test_candidate_cannot_overwrite_production_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            module = load_profile_bootstrap(EXPECTED_PROFILE, EXPECTED_PROFILE, Path(temporary_directory))
            with mock.patch.dict(os.environ, module._test_environment, clear=False):
                with self.assertRaisesRegex(RuntimeError, "must not overwrite"):
                    module.main()


if __name__ == "__main__":
    unittest.main()
