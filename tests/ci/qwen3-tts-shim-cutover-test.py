#!/usr/bin/env python3
"""Static deployment contract checks for the pinned Qwen3-TTS shim cutover."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ROLE_ROOT = REPOSITORY_ROOT / "ansible" / "roles" / "qwen3-tts"
CATALOG_PATH = ROLE_ROOT / "files" / "voice-catalog.json"
COMPOSE_PATH = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
CUTOVER_PATH = ROLE_ROOT / "tasks" / "shim-cutover.yml"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
JENKINS_PATH = REPOSITORY_ROOT / "Jenkinsfile"

IMAGE = "ghcr.io/blue126/qwen3-tts-service-shim@sha256:37cabe5713613ba719e47bc9c535d0443c58243fdd0e4404f560ba3b60b231a5"
CATALOG_SHA256 = "841bffa3cc473b9b220dbd91af8603bc85a6233b9ceaf26760af8e3c157a9fca"
EXPECTED_VOICES = {
    "alloy": "audiobook_narrator_zh",
    "ash": "voice_yunyang_zh_a49b1902cb45",
    "ballad": "voice_gdg_zh_29a6150487d8",
    "cedar": "voice_cedar_zh_ref_5fb0b64ef7",
    "coral": "voice_coral_zh_ref_5fb0b64ef7",
    "echo": "voice_jianghu_zh_adfcd2e45b5a",
    "fable": "voice_cctv_zh_d02515811467",
    "marin": "voice_xw_zh_5c4d736fc24d",
    "nova": "voice_nova_zh_2c3d176a377c",
    "onyx": "voice_gxs_zh_16fee2fe9d56",
    "sage": "voice_nzb_zh_b5f8baaaa43b",
    "shimmer": "voice_shimmer_zh_c514bd4e7968",
    "verse": "voice_111_zh_0e48961bbc7e",
}


def reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def section(text: str, start: str, end: str) -> str:
    try:
        return text.split(start, 1)[1].split(end, 1)[0]
    except IndexError as error:
        raise AssertionError(f"cannot isolate section {start!r}") from error


def main() -> int:
    catalog_raw = CATALOG_PATH.read_text(encoding="utf-8")
    catalog = json.loads(catalog_raw, object_pairs_hook=reject_duplicate_object)
    assert set(catalog) == {"schema_version", "default_alias", "voices"}
    assert type(catalog["schema_version"]) is int and catalog["schema_version"] == 1
    assert catalog["default_alias"] == "alloy"
    assert catalog["voices"] == EXPECTED_VOICES
    assert all(re.fullmatch(r"[a-z0-9_]+", value) for value in EXPECTED_VOICES.values())
    assert len({value.casefold() for value in EXPECTED_VOICES.values()}) == 13
    assert hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest() == CATALOG_SHA256

    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    assert "qwen3_tts_shim_image_repository: ghcr.io/blue126/qwen3-tts-service-shim" in defaults
    assert "qwen3_tts_shim_image_digest: sha256:37cabe5713613ba719e47bc9c535d0443c58243fdd0e4404f560ba3b60b231a5" in defaults
    assert "qwen3_tts_profile_bootstrap_image: python:3.12-slim" in defaults
    assert "qwen3_tts_voice_aliases" not in defaults
    assert not re.search(r"^qwen3_tts_mode:", defaults, flags=re.MULTILINE)

    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    shim = section(compose, "  shim:\n", "  voice-design:\n")
    assert 'image: "{{ qwen3_tts_shim_image }}"' in shim
    assert "VOICE_CATALOG_PATH: /etc/qwen3-tts/voice-catalog.json" in shim
    assert "UPSTREAM_URL:" in shim and "UPSTREAM_MODEL:" in shim
    assert "LOG_LEVEL: INFO" in shim
    assert "{{ qwen3_tts_voice_catalog_path }}:/etc/qwen3-tts/voice-catalog.json:ro" in shim
    for forbidden in (
        "qwen3-tts-shim.py",
        "VOICE_ALIASES_JSON",
        "BASE_PROFILE:",
        "TTS_MODE:",
        "qwen3_tts_profile_dir",
        "command:",
    ):
        assert forbidden not in shim
    bootstrap = compose.split("  profile-bootstrap:\n", 1)[1]
    assert 'image: "{{ qwen3_tts_profile_bootstrap_image }}"' in bootstrap

    cutover = CUTOVER_PATH.read_text(encoding="utf-8")
    assert "--no-deps" in cutover
    assert "--pull\n          - never" in cutover
    assert "check-profiles" in cutover
    assert "docker compose down" not in cutover
    assert "systemd_service:" not in cutover
    for boundary in (
        "qwen3_tts_service_name == 'qwen3-tts.service'",
        "qwen3_tts_compose_project == 'qwen3-tts'",
        "qwen3_tts_install_dir == '/opt/qwen3-tts'",
        "qwen3_tts_voice_catalog_path == '/opt/qwen3-tts/voice-catalog.json'",
        "qwen3_tts_shim_cutover_stage_dir == '/opt/qwen3-tts/.shim-cutover-stage'",
        "qwen3_tts_shim_rollback_dir == '/opt/qwen3-tts/shim-cutover-rollback'",
        "qwen3_tts_shim_cutover_lock_path == '/run/lock/qwen3-tts-shim-cutover.lock'",
    ):
        assert boundary in cutover
    for forbidden in (
        "restart\n          - server",
        "- server\n",
        "- voice-design\n",
        "- profile-bootstrap\n",
        "qwen3_tts_vllm_deploy_config_path",
        "qwen3_tts_profile_dir",
        "qwen3_tts_model_cache_dir",
        "qwen3_tts_vllm_cache_dir",
        "qwen3_tts_gpu_ordinal",
    ):
        assert forbidden not in cutover

    verify = (ROLE_ROOT / "tasks" / "shim-cutover-verify.yml").read_text(encoding="utf-8")
    assert "--connect-timeout" in verify
    assert "--max-time" in verify

    jenkins = JENKINS_PATH.read_text(encoding="utf-8")
    assert "if (roleName == 'qwen3-tts')" in jenkins
    assert "needs an explicit confirmation variable" in jenkins

    print("qwen3_tts_shim_cutover_contract=passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
