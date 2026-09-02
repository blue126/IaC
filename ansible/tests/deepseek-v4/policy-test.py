#!/usr/bin/env python3
"""Offline policy checks for the controlled DeepSeek Phase 0 artifacts."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / "ansible"
failures = []


def require(condition, message):
    if not condition:
        failures.append(message)


compose = (ANSIBLE / "roles/deepseek-v4/templates/docker-compose.yml.j2").read_text()
unit = (ANSIBLE / "roles/deepseek-v4/templates/deepseek-v4.service.j2").read_text()
host_vars = (ANSIBLE / "inventory/host_vars/llm-server.yml").read_text()
defaults = (ANSIBLE / "roles/deepseek-v4/defaults/main.yml").read_text()
webui_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/webui.yml").read_text()
contract_runner = (ANSIBLE / "roles/deepseek-v4/files/contract-runner.py").read_text()
benchmark_runner = (ANSIBLE / "roles/deepseek-v4/files/benchmark-runner.py").read_text()
context_runner = (ANSIBLE / "roles/deepseek-v4/files/context-window-runner.py").read_text()
checkpoint_runner = (
    ANSIBLE / "roles/deepseek-v4/files/checkpoint-transition-runner.py"
).read_text()
experiment_verdict = (
    ANSIBLE / "roles/deepseek-v4/files/experiment-verdict.py"
).read_text()
evidence_validator = (ANSIBLE / "roles/deepseek-v4/files/evidence-validator.py").read_text()
lifecycle_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/lifecycle.yml").read_text()
verify_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/verify.yml").read_text()
activate_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/activate.yml").read_text()
ik_root = ANSIBLE / "roles/deepseek-v4-ik"
ik_compose = (ik_root / "templates/docker-compose.yml.j2").read_text()
ik_production = (ik_root / "tasks/production.yml").read_text()
ik_main = (ik_root / "tasks/main.yml").read_text()
ik_candidate = (ik_root / "tasks/candidate.yml").read_text()
ik_platform = (ik_root / "tasks/platform.yml").read_text()
ik_platform_grub = (ik_root / "templates/99-deepseek-v4-kernel.cfg.j2").read_text()
ik_handlers = (ik_root / "handlers/main.yml").read_text()
ik_qualification = (ANSIBLE / "playbooks/qualify-deepseek-v4-ik.yml").read_text()
ik_proxy_unit = (ik_root / "templates/deepseek-v4-ik-compat.service.j2").read_text()
ik_proxy = ik_root / "files/openai-compat-proxy.py"
fixture_dir = ANSIBLE / "roles/deepseek-v4/files"
fixture_documents = {
    path.name: json.loads(path.read_text())
    for path in fixture_dir.glob("*.json")
}
fixtures = fixture_documents["api-fixtures-v1.json"]

require(":/model:ro" in compose, "model volume is not read-only")
require("privileged: false" in compose, "container privilege is not explicitly disabled")
require("cap_drop:" in compose and "- ALL" in compose, "capabilities are not minimized")
require("nvidia.com/gpu=" in compose, "inference container does not reserve an NVIDIA GPU")
require("deepseek_v4_gpu_ordinals" in compose, "inference GPU identities are not explicit")
require("NCCL_P2P_DISABLE" in compose, "TP2 P2P fallback is not explicit")
require("deepseek_v4_profile: tp1" in defaults, "TP1 is not the default profile")
require("tp2:" in defaults and 'gpu_ordinals: ["0", "1"]' in defaults,
        "the strict TP2 GPU profile is missing")
require("deepseek_v4_profile in ['tp1', 'tp2']" in (ANSIBLE / "roles/deepseek-v4/tasks/validate.yml").read_text(),
        "profile validation does not reject unknown profiles")
require("profile:" in (ANSIBLE / "roles/deepseek-v4/templates/release-manifest.yml.j2").read_text(),
        "release manifest does not record the active profile")
require("Discover NVIDIA GPU ordinals before activation" in activate_tasks,
        "activation does not verify the requested GPU ordinals")
require("systemd-run --wait --collect" in activate_tasks,
        "activation does not wait for its guarded result")
require("no-new-privileges:true" in compose, "no-new-privileges is missing")
require("max-size:" in compose and "max-file:" in compose, "bounded logging is missing")
require("@{{ deepseek_v4_runtime_image_digest }}" in compose, "image digest is not rendered")
require("deepseek-private" in compose, "controlled Compose network is missing")
require("open-webui:" in compose, "Open WebUI is absent from the controlled Compose project")
require("deepseek_v4_webui_image_digest" in compose, "Open WebUI image is not digest-pinned")
require(compose.count("deepseek-private") >= 3, "Open WebUI and inference do not share the private network")
require("--context-length" not in compose, "runtime template guesses an unaudited context flag")
require("restart: unless-stopped" in compose, "Compose is not the container restart owner")
require("Restart=" not in unit, "systemd must not own a restart loop")
require("--pull never" in unit, "lifecycle could pull an image")
require("deepseek_v4_compose_services" in unit, "systemd cannot isolate inference from UI cutover")
require(
    not (ANSIBLE / "playbooks/deploy-llm-server.yml").exists(),
    "retired entrypoint playbook should have been deleted, not left in place",
)
require(
    not (ANSIBLE / "roles/llm-server").exists(),
    "the legacy multi-model role should have been deleted, not left in place",
)
require("llm_server_models" not in host_vars and "llm_server_boot_model" not in host_vars,
        "legacy desired state remains in host vars")
require(re.search(r"deepseek_v4_api_bind_address: 127\.0\.0\.1", defaults), "default API bind is not loopback")
require(
    "deepseek_v4_webui_host_gateway_address" in compose,
    "Open WebUI host-gateway API bind is missing",
)
require(any(not case["valid"] for case in fixtures["cases"]), "malformed fixtures are absent")
require("deepseek_v4_webui_database_path" in webui_tasks, "WebUI database is not inspected")
require("state: absent" not in webui_tasks, "default WebUI path deletes a seed file")
require(
    "Remove consumed one-time Open WebUI connection seed" in lifecycle_tasks,
    "approved cutover does not remove the consumed one-time seed",
)
require(
    "Restore the legacy Open WebUI writer" in lifecycle_tasks,
    "failed WebUI backup does not restore the stopped legacy writer",
)
required_contract_cases = {
    "sync-chat",
    "sse-chat",
    "single-tool",
    "parallel-tool",
    "tool-continuation",
}
require(
    all(case_id in contract_runner for case_id in required_contract_cases),
    "live contract runner is missing required API cases",
)
require(
    'for effort in ("low", "high", "max")' in contract_runner,
    "live contract runner is missing reasoning effort coverage",
)
require("done_count == 1" in contract_runner, "SSE terminator is not strict")
require("expected_tools" in contract_runner, "tool arguments are not validated")
require("target_prompt_tokens" in benchmark_runner, "benchmark token target is absent")
require("calibrated_prompt" in benchmark_runner, "benchmark input is not tokenizer-calibrated")
require(
    all(
        'f"{base_url}/tokenize"' in runner
        and "observed = token_count(base_url, prompt)" in runner
        for runner in (context_runner, checkpoint_runner)
    ),
    "a long-context runner calibrates by generating instead of tokenizing",
)
require(
    "recall_marker_present" in checkpoint_runner
    and "handoff_expected_present" in checkpoint_runner,
    "checkpoint evidence cannot distinguish verbose from missing answers",
)
require(
    "restore-result.json" in ik_candidate
    and "deepseek_v4_ik_exact_restore_verified" in ik_candidate,
    "checkpoint qualification can precede exact control restoration evidence",
)
require(
    "checkpoint diagnostic evidence cannot unlock 4 checkpoints"
    in experiment_verdict,
    "single-repeat checkpoint diagnostics can unlock checkpoint 4",
)
require(
    'default=10800' in checkpoint_runner
    and "deepseek_v4_ik_experiment_watchdog_timeout_seconds: 25200"
    in (ik_root / "defaults/main.yml").read_text()
    and "deepseek_v4_ik_experiment_watchdog_timeout_seconds | int) + 3600"
    in ik_candidate,
    "checkpoint route and watchdog budgets do not preserve restoration margin",
)
require(
    "deepseek_v4_ik_emit_ctx_checkpoints | bool and" in ik_main
    and "['baseline', 'ctx_checkpoints']" in ik_main
    and "deepseek_v4_ik_model_checksum_proof_stat.stat.pw_name" in ik_candidate
    and "deepseek_v4_ik_candidate_model_stat.stat.mtime" in ik_candidate,
    "verified model checksum reuse is not limited to fresh root-owned checkpoint evidence",
)
require("validate_benchmark" in evidence_validator, "benchmark evidence is not validated")
require("map(attribute='id')" in verify_tasks, "model identity check is not exact")
require(
    all(
        document.get("schema_version") or document.get("$schema")
        for document in fixture_documents.values()
    ),
    "a versioned JSON fixture is missing schema_version",
)
require(ik_proxy.exists(), "GGUF OpenAI compatibility proxy is absent")
require("deepseek_v4_ik_backend_api_port" in ik_compose, "GGUF backend port is not isolated")
require(
    "deepseek_v4_ik_backend_api_bind_address" in ik_compose,
    "GGUF candidate does not bind through the private backend address",
)
require(
    "deepseek_v4_ik_api_port" not in ik_compose.split("ports:", 1)[1],
    "GGUF candidate still publishes the stable frontend port directly",
)
require(
    "deepseek_v4_ik_compat_service_unit" in ik_production,
    "production tasks do not own the compatibility proxy",
)
require(
    "Requires={{ deepseek_v4_ik_service_unit }}" not in ik_proxy_unit
    and "PartOf={{ deepseek_v4_ik_service_unit }}" not in ik_proxy_unit,
    "compatibility proxy is still coupled to the production owner",
)
require("--timezone" not in ik_proxy_unit,
        "compatibility proxy must not inject trusted-date context")
require("--allow-cidrs" in ik_proxy_unit,
        "compatibility proxy does not restrict API source networks")
require("zero-thinking-chat" in contract_runner,
        "live contract runner is missing the zero-thinking regression")
require("/opt/deepseek-v4/harness" not in ik_candidate,
        "candidate workflow still depends on retired DeepSeek harnesses")
require("deepseek_v4_ik_service_unit" in ik_candidate,
        "candidate workflow does not stop and restore the active GGUF owner")
require("benchmark-runner.py" in ik_candidate,
        "candidate workflow does not install its benchmark runner")
require("deepseek_v4_ik_manage_webui: false" in (ik_root / "defaults/main.yml").read_text(),
        "parser compatibility deployment can still recreate Open WebUI by default")
require("deepseek_v4_ik_platform: false" in (ik_root / "defaults/main.yml").read_text(),
        "GPU platform lifecycle is not disabled by default")
require("deepseek_v4_ik_platform | bool" in ik_main and "platform.yml" in ik_main,
        "GPU platform is absent from the exactly-one lifecycle gate")
require("deepseek_v4_ik_platform_allow_reboot: false" in (ik_root / "defaults/main.yml").read_text(),
        "VM reboot is not fail-closed by default")
require("deepseek_v4_ik_platform_allow_reboot | bool" in ik_platform,
        "platform recovery lacks an explicit VM reboot gate")
require("${db:Status-Want}" in ik_platform
        and "${db:Status-Status}" in ik_platform,
        "platform package probes are not stable after apt-mark hold")
require(ik_platform.count("check_mode: false") >= 5,
        "read-only platform probes are skipped by Ansible check mode")
require(
    ik_platform.index("Require explicit approval before changing the VM boot target")
    < ik_platform.index("Pin the verified kernel as the GRUB default"),
    "GRUB can change before the explicit reboot gate passes",
)
require("selection: hold" in ik_platform and "Package-Blacklist" in ik_platform,
        "platform packages are not protected from automatic advancement")
require("unattended-upgrades.service" in ik_platform,
        "platform verification does not preserve unattended security updates")
require("apt-daily-upgrade.timer" in ik_platform
        and 'APT::Periodic::Unattended-Upgrade "1";' in ik_platform,
        "platform verification does not prove unattended upgrades are scheduled")
require("Re-query exact platform package versions after recovery" in ik_platform,
        "platform verification does not close the preflight-to-hold package race")
require("Reset the exact unattended-upgrade blacklist" in ik_platform,
        "platform blacklist facts are not deterministic across plays")
require("/updates/dkms/" in ik_platform and "dkms" not in ik_platform_grub,
        "platform recovery does not reject a DKMS module path")
require("state: absent" not in ik_platform and "purge" not in ik_platform,
        "platform recovery can remove the rescue kernel or packages")
require("Update GRUB menu" in ik_handlers and "GRUB_DEFAULT" in ik_platform_grub,
        "the pinned GRUB default is not regenerated through a handler")
require("platform-verify" in ik_qualification and "tags: [never, platform]" in ik_qualification,
        "qualification playbook lacks explicit platform entrypoints")
require("6.8.0-101-generic" in host_vars and "590.48.01-0ubuntu0.24.04.1" in host_vars,
        "host inventory lacks the exact verified kernel/NVIDIA bundle")
require("deepseek_v4_ik_platform_expected_gpu_count" in ik_platform
        and "deepseek_v4_ik_platform_expected_gpu_name" in ik_platform,
        "platform verification does not require two exact RTX 3090 identities")
proxy_self_test = subprocess.run(
    [sys.executable, str(ik_proxy), "--self-test"],
    capture_output=True,
    text=True,
)
require(proxy_self_test.returncode == 0,
        f"compatibility proxy self-test failed: {proxy_self_test.stdout.strip()}")

report = {"schema_version": 1, "status": "pass" if not failures else "fail", "failures": failures}
print(json.dumps(report, indent=2, sort_keys=True))
sys.exit(0 if not failures else 1)
