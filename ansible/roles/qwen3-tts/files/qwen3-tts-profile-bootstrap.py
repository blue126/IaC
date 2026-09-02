#!/usr/bin/env python3
"""Create a synthetic reference and register its persistent Base profile."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PROFILE = os.environ["BASE_PROFILE"]
REFERENCE = Path(os.environ["PROFILE_REFERENCE_FILE"])
REFERENCE_TEXT = os.environ["PROFILE_REFERENCE_TEXT"]
VOICE_DESIGN_INSTRUCTIONS = os.environ["VOICE_DESIGN_INSTRUCTIONS"]
VOICE_DESIGN_MODEL = os.environ["VOICE_DESIGN_MODEL"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")
VOICE_DESIGN_URL = os.environ["VOICE_DESIGN_URL"].rstrip("/")
PRODUCTION_PROFILE = os.getenv("PRODUCTION_PROFILE", PROFILE)
PROBE_TEXT = os.getenv("PROFILE_PROBE_TEXT", "")
PROBE_FILE = Path(os.environ["PROFILE_PROBE_FILE"]) if os.getenv("PROFILE_PROBE_FILE") else None


def request_json(url: str, payload: dict[str, object]) -> bytes:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=600) as response:  # nosec B310 -- fixed Compose URLs
        if response.status != 200:
            raise RuntimeError(f"Unexpected status {response.status} from {url}")
        return response.read()


def create_reference() -> None:
    if reference_is_valid() and os.getenv("FORCE_REFERENCE") != "1":
        return
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    audio = request_json(
        f"{VOICE_DESIGN_URL}/v1/audio/speech",
        {
            "model": VOICE_DESIGN_MODEL,
            "input": REFERENCE_TEXT,
            "task_type": "VoiceDesign",
            "language": "Chinese",
            "instructions": VOICE_DESIGN_INSTRUCTIONS,
            "response_format": "wav",
        },
    )
    if not is_wav(audio):
        raise RuntimeError("VoiceDesign did not return a valid WAV reference")
    temporary = REFERENCE.with_suffix(".tmp")
    temporary.write_bytes(audio)
    temporary.replace(REFERENCE)


def is_wav(audio: bytes) -> bool:
    return len(audio) > 44 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"


def reference_is_valid() -> bool:
    try:
        return is_wav(REFERENCE.read_bytes())
    except OSError:
        return False


def registered_profile_exists() -> bool:
    try:
        with urlopen(f"{BASE_URL}/v1/audio/voices", timeout=30) as response:  # nosec B310 -- fixed Compose URL
            payload = json.loads(response.read())
    except (HTTPError, OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or not isinstance(payload.get("uploaded_voices"), list):
        return False
    return any(
        isinstance(voice, dict) and str(voice.get("name", "")).casefold() == PROFILE.casefold()
        for voice in payload["uploaded_voices"]
    )


def multipart_body() -> tuple[bytes, str]:
    boundary = f"----qwen3tts{uuid.uuid4().hex}"
    fields = {
        "consent": "synthetic-generated-by-operator",
        "name": PROFILE,
        "ref_text": REFERENCE_TEXT,
        "speaker_description": VOICE_DESIGN_INSTRUCTIONS,
    }
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend((f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode("utf-8"), b"\r\n"))
    chunks.extend((f"--{boundary}\r\n".encode(), b'Content-Disposition: form-data; name="audio_sample"; filename="synthetic-reference.wav"\r\n', b"Content-Type: audio/wav\r\n\r\n", REFERENCE.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode()))
    return b"".join(chunks), boundary


def register_profile() -> None:
    if registered_profile_exists():
        return
    payload, boundary = multipart_body()
    request = Request(
        f"{BASE_URL}/v1/audio/voices",
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:  # nosec B310 -- fixed Compose URL
            if response.status != 200:
                raise RuntimeError(f"Profile registration returned {response.status}")
            result = json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"Profile registration failed: {error.read().decode(errors='replace')}") from error
    if not result.get("success"):
        raise RuntimeError("Profile registration did not report success")


def create_probe() -> None:
    if PROBE_FILE is None or not PROBE_TEXT:
        raise RuntimeError("Candidate probe requires PROFILE_PROBE_FILE and PROFILE_PROBE_TEXT")
    audio = request_json(
        f"{BASE_URL}/v1/audio/speech",
        {
            "model": os.getenv("BASE_MODEL", ""),
            "input": PROBE_TEXT,
            "task_type": "Base",
            "voice": PROFILE,
            "language": "Chinese",
            "response_format": "wav",
        },
    )
    if not is_wav(audio):
        raise RuntimeError("Base did not return a valid WAV candidate probe")
    PROBE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = PROBE_FILE.with_suffix(".tmp")
    temporary.write_bytes(audio)
    temporary.replace(PROBE_FILE)


def main() -> None:
    mode = os.getenv("BOOTSTRAP_MODE", "register")
    if mode == "reference":
        create_reference()
    elif mode == "register":
        if not reference_is_valid():
            raise RuntimeError("Synthetic reference is missing; run reference bootstrap first")
        register_profile()
    elif mode == "candidate":
        if PROFILE == PRODUCTION_PROFILE:
            raise RuntimeError("Candidate profile must not overwrite the production profile")
        if not reference_is_valid():
            raise RuntimeError("Candidate reference is missing or invalid")
        register_profile()
        create_probe()
    else:
        raise ValueError("BOOTSTRAP_MODE must be reference, register, or candidate")


if __name__ == "__main__":
    main()
