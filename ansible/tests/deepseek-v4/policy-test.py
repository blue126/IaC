#!/usr/bin/env python3
"""Offline policy checks for the controlled DeepSeek Phase 0 artifacts."""

import json
import re
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
legacy_playbook = (ANSIBLE / "playbooks/deploy-llm-server.yml").read_text()
legacy_role = (ANSIBLE / "roles/llm-server/tasks/main.yml").read_text()
host_vars = (ANSIBLE / "inventory/host_vars/llm-server.yml").read_text()
defaults = (ANSIBLE / "roles/deepseek-v4/defaults/main.yml").read_text()
webui_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/webui.yml").read_text()
contract_runner = (ANSIBLE / "roles/deepseek-v4/files/contract-runner.py").read_text()
benchmark_runner = (ANSIBLE / "roles/deepseek-v4/files/benchmark-runner.py").read_text()
evidence_validator = (ANSIBLE / "roles/deepseek-v4/files/evidence-validator.py").read_text()
lifecycle_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/lifecycle.yml").read_text()
verify_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/verify.yml").read_text()
activate_tasks = (ANSIBLE / "roles/deepseek-v4/tasks/activate.yml").read_text()
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
require("role: llm-server" not in legacy_playbook and "    - llm-server\n" not in legacy_playbook,
        "retired entrypoint still references the legacy role")
require(
    "Reject the retired legacy LLM lifecycle" in legacy_role,
    "the legacy role can still reactivate retired models",
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
require("validate_benchmark" in evidence_validator, "benchmark evidence is not validated")
require("map(attribute='id')" in verify_tasks, "model identity check is not exact")
require(
    all(
        document.get("schema_version") or document.get("$schema")
        for document in fixture_documents.values()
    ),
    "a versioned JSON fixture is missing schema_version",
)

report = {"schema_version": 1, "status": "pass" if not failures else "fail", "failures": failures}
print(json.dumps(report, indent=2, sort_keys=True))
sys.exit(0 if not failures else 1)
