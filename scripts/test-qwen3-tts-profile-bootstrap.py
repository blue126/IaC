#!/usr/bin/env python3
"""Standard-library tests for the Qwen3-TTS profile bootstrap helper."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROFILE_BOOTSTRAP_PATH = (
    REPOSITORY_ROOT / "ansible" / "roles" / "qwen3-tts" / "files" / "qwen3-tts-profile-bootstrap.py"
)
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
            self.assertEqual(
                requests,
                [
                    (
                        "http://base.test/v1/audio/speech",
                        {
                            "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                            "input": "固定试听探针文本。",
                            "task_type": "Base",
                            "voice": candidate,
                            "language": "Chinese",
                            "response_format": "wav",
                        },
                    )
                ],
            )

    def test_candidate_cannot_overwrite_production_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            module = load_profile_bootstrap(EXPECTED_PROFILE, EXPECTED_PROFILE, Path(temporary_directory))
            with mock.patch.dict(os.environ, module._test_environment, clear=False):
                with self.assertRaisesRegex(RuntimeError, "must not overwrite"):
                    module.main()


if __name__ == "__main__":
    unittest.main()
