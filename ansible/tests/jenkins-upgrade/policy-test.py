#!/usr/bin/env python3
"""Offline policy checks for the fail-closed Jenkins LTS upgrade path."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / "ansible"
failures = []


def require(condition, message):
    if not condition:
        failures.append(message)


def version_key(value):
    """Order Jenkins plugin versions by alternating numeric and text runs."""
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.lower())
        for part in re.split(r"([0-9]+)", value)
        if part
    )


bom = yaml.safe_load((ROOT / "ci/toolchain-bom.yml").read_text())
defaults = (ANSIBLE / "roles/jenkins/defaults/main.yml").read_text()
upgrade = (ANSIBLE / "roles/jenkins/tasks/upgrade.yml").read_text()
phase = (ANSIBLE / "roles/jenkins/tasks/upgrade-phase.yml").read_text()
verify = (ANSIBLE / "roles/jenkins/tasks/upgrade-verify.yml").read_text()
reconcile = (ANSIBLE / "roles/jenkins/tasks/upgrade-reconcile.yml").read_text()
playbook = (ANSIBLE / "playbooks/upgrade-jenkins.yml").read_text()
java_override = (
    ANSIBLE / "roles/jenkins/templates/jenkins.service.java.conf.j2"
).read_text()

jenkins = bom["jenkins"]
plugin_upgrade = jenkins["plugin_upgrade"]
lock = plugin_upgrade["lock"]
by_id = {item["id"]: item for item in lock}
expected_roots = {
    "credentials-binding": "728.v902a_273b_8947",
    "email-ext": "2038.v7b_8817a_499d9",
    "git-client": "6.6.1",
    "github": "1.47.0",
    "github-branch-source": "1983.vfa_27ed961853",
    "ldap": "807.809.vd3a_4e5e4ec98",
    "matrix-auth": "3.3",
    "pipeline-groovy-lib": "798.v5cc688825312",
    "script-security": "1412.v7737b_3405f86",
    "workflow-cps": "4370.v49a_6937566b_6",
}

require(plugin_upgrade["roots"] == list(expected_roots),
        "the ten approved root plugins or their order changed")
require(len(lock) == 58 and len(by_id) == len(lock),
        "the exact 58-plugin closure is missing or duplicated")
computed_lock_sha256 = hashlib.sha256(
    json.dumps(lock, sort_keys=True).encode()
).hexdigest()
require(plugin_upgrade["canonical_lock_sha256"] == computed_lock_sha256,
        "canonical lock hash does not cover the approved dependency versions")
expected_core_managed = {
    "jquery3-api": "92f36b5b605c37d1518e2bb2166eac729cb0a18e5a89a320e82d0691cdd76cab",
    "junit": "716d2f706bd8238076e0b408bf3adeb07eae20d81e256a7fd40340c24f9d9d48",
    "plugin-util-api": "d0e687857a78a77d6e023844d5d4f06c3df37512a176cf4f646f0aea3a498e7e",
    "prism-api": "93fd4ebb761d525863c3b08b5274c7e58b7f94c41846f47253d1969a12ed1cbb",
    "jackson3-api": "07a8b6c31021c13c9cf3a2b5d1441c829ab44369927fdfd0ee47236d007ff0a0",
    "sshd": "aae61f39df9bfd46b24ad6b9f8cef10b3c23d85e7ab9cc7b3a5b7a02dea35c3c",
    "snakeyaml-engine-api": "dafc5fa060c9589d7b7e85aa8fc49239ad20841cba855e14a7bf7f064a257b0d",
    "command-launcher": "12bc6863fa3d2ce11c9f5d3f603d8c2eaf610d5d01950c94c2455fdd3fefdab8",
    "bootstrap5-api": "6b1ebd8dc1c4107a71e7f552faea6ff3501304df90a53076fb4c44b7b76179c7",
    "bouncycastle-api": "a31099c54d9b1ac6f88b1336088a73124831532313bf3280e3eb1610300382e1",
    "checks-api": "27e2728fcc5f1da82923e1b1cc65d14df075dc36f1e22de963432e3d8c0e537e",
    "echarts-api": "9ba462eb770da36074a56bd1bd195c59b0b50c9eb5920b4f29c008c0da24b4ee",
    "font-awesome-api": "64f769361df546d878363e705a855171cb1e79bd85320f009c94138faf28b6bc",
    "javax-activation-api": "e96e88c52edf07ba00fb45b26cc411a7a95fa3d4491aaa1a5d36637665880560",
    "jaxb": "38ddf4cf5db61a591044130c2f7ccb2b7aa9abebc8fcd8a6953f8da550d002ed",
}
core_managed = plugin_upgrade["core_managed_detached"]
require([item["id"] for item in core_managed] == list(expected_core_managed),
        "Core-managed detached plugin order drifted")
for item in core_managed:
    require(item["sha256"] == expected_core_managed[item["id"]],
            f"Core-managed detached plugin drifted: {item['id']}")
require(plugin_upgrade["reconcile_ids"]
        == ["cloudbees-folder", "json-path-api", "snakeyaml-api"],
        "post-upgrade reconciliation set drifted")
expected_reconcile_versions = {
    "cloudbees-folder": "6.1100.ve9eed61d16c4",
    "json-path-api": "2.9.0-190.veefca_05d5477",
    "snakeyaml-api": "2.3-125.v4d77857a_b_402",
}
for plugin_id, version in expected_reconcile_versions.items():
    require(by_id[plugin_id]["version"] == version,
            f"post-upgrade dependency target drifted: {plugin_id}")
for plugin_id, version in expected_roots.items():
    require(by_id.get(plugin_id, {}).get("version") == version,
            f"root target drifted: {plugin_id}")
for item in lock:
    require(bool(item.get("version")), f"{item['id']} has no exact version")
    require(re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")),
            f"{item['id']} has no exact SHA-256")
    require(item.get("url", "").startswith(
        "https://repo.jenkins-ci.org/artifactory/releases/"),
        f"{item['id']} does not use the official releases repository")
    require(re.fullmatch(r"\d+\.\d+(?:\.\d+)?", item.get("required_core", "")),
            f"{item['id']} has no exact required Core")
    for dependency in item.get("dependencies", []):
        require(dependency.get("id") in by_id,
                f"{item['id']} dependency is outside the lock: {dependency}")
        require(bool(dependency.get("minimum_version")),
                f"{item['id']} dependency has no minimum version")
        if dependency.get("id") in by_id and dependency.get("minimum_version"):
            require(
                version_key(by_id[dependency["id"]]["version"])
                >= version_key(dependency["minimum_version"]),
                f"{item['id']} dependency minimum is not satisfied: {dependency}",
            )

require([item["version"] for item in jenkins["core"]["upgrade_path"]]
        == ["2.541.3", "2.555.3", "2.568.2"],
        "Core phases are not the approved ordered path")
require(jenkins["core"]["version"] == "2.568.2"
        and jenkins["core"]["package_version"] == "2.568.2",
        "canonical Core does not describe the final state")
expected_core_sha256 = {
    "2.541.3": "38836b389b3a953e16ba2d2df07802c8a351be8b97129d54bc4086ade64b2c42",
    "2.555.3": "14c0692281e650666bd56f89ff98c5afac34b28a409ff5b964e219a0d09215d5",
    "2.568.2": "abaa015c3a39a8182eed136333d6d0ba055564df37584e699cc9693ad64ad7d5",
}
for core_phase in jenkins["core"]["upgrade_path"]:
    require(core_phase["sha256"] == expected_core_sha256[core_phase["version"]],
            f"Core checksum drifted: {core_phase['version']}")
require(jenkins["java"]["upgrade"]["package_version"]
        == "21.0.12.1.0+1-0", "Temurin package target drifted")
require(jenkins["java"]["upgrade"]["package_sha256"]
        == "6c36c5cae76391a558926db5b8df2114dc41ed2ba889edf962370083944588b3",
        "Temurin package checksum drifted")
expected_java_dependencies = {
    "p11-kit-modules": (
        "0.24.1-2",
        "cabb6903a2ec765216643b43de04e0d5fb687b10f8e9032cde7d48640fdde80f",
    ),
    "p11-kit": (
        "0.24.1-2",
        "ee45a531fe3b48fbeabaa21f724a8cd6cfd69703aaa9d1c8f73975710f3310e5",
    ),
    "adoptium-ca-certificates": (
        "1.0.6-1",
        "bd146cae76f600fedcaf0ca1776cf099b48bcd01fdaa42479c3b1f3dc0d5f2f0",
    ),
}
java_dependencies = jenkins["java"]["upgrade"]["package_dependencies"]
require([item["name"] for item in java_dependencies]
        == list(expected_java_dependencies),
        "Temurin package dependency order drifted")
for item in java_dependencies:
    require((item["version"], item["sha256"])
            == expected_java_dependencies[item["name"]],
            f"Temurin package dependency drifted: {item['name']}")
require(jenkins["controller_executors_bootstrap"] == 2,
        "built-in controller executor count changed")

require("jenkins_upgrade_authorized: false" in defaults,
        "upgrade authorization is not disabled by default")
require("jenkins_manage_casc: false" in defaults,
        "JCasC is not disabled by default")
gate_at = upgrade.index("Validate Jenkins upgrade authorization gates")
first_write_at = upgrade.index("Create root-owned Jenkins upgrade staging directory")
require(gate_at < first_write_at, "a mutating task can precede authorization")
for unit in ("upgrade-validate-gates.yml", "upgrade-validate-lock.yml",
             "upgrade-validate-source.yml", "upgrade-validate-duplicates.yml",
             "upgrade-validate-staged.yml"):
    require(unit in upgrade, f"production path does not reuse {unit}")
require("checksum: \"sha256:{{ item.sha256 }}\"" in upgrade,
        "plugin staging does not enforce the locked checksum")
require("package_sha256" in upgrade and "Download exact Temurin package" in upgrade,
        "Temurin package checksum is declared but not enforced")
require("Download exact Temurin package dependencies" in upgrade
        and "Install checksummed Temurin package dependencies" in upgrade,
        "Temurin dependencies are not checksummed and installed explicitly")
require("with_dependencies=false" in upgrade,
        "plugin activation does not explicitly disable dependency resolution")
require(upgrade.index("Validate every staged artifact before system mutation")
        < upgrade.index("Copy locked plugins"),
        "live plugin paths can change before all artifacts are checked")
artifact_gate_at = upgrade.index("Validate every staged artifact before system mutation")
for mutation in (
    "Create apt keyring directory",
    "Install verified Adoptium signing key",
    "Configure signed Adoptium apt repository",
    "Install checksummed Temurin runtime",
    "Install checksummed Temurin package dependencies",
    "Select exact Temurin runtime for Jenkins",
    "Stop Jenkins before plugin activation",
):
    require(artifact_gate_at < upgrade.index(mutation),
            f"system mutation precedes complete artifact validation: {mutation}")
require("Download every exact Jenkins Core phase" in upgrade,
        "Core phases are not driven by the ordered BOM")
require("jenkins_upgrade_phase_http.x_jenkins" in phase,
        "Core phase does not verify the live X-Jenkins version")
require("Restore complete original plugin collection" in upgrade
        and "Restore exact source Jenkins Core package" in upgrade,
        "first-phase rollback does not restore the original controller")
require("always:" in upgrade and "Remove this run Jenkins staging data" in upgrade,
        "staging data is not cleaned on every outcome")
require("JENKINS_JAVA_CMD" in java_override and "JAVA_HOME" in java_override,
        "Jenkins Java runtime is not selected explicitly")
require("jenkins_manage_casc" in verify and "initial_node_paths" in verify,
        "final verification does not preserve the node/JCasC boundary")
require("exact active plugin artifacts and checksums" in verify
        and "locked plugins are not disabled" in verify,
        "final verification does not prove exact active plugin artifacts")
require("jenkins_upgrade_final_java_executable" in verify,
        "final verification does not inspect the Jenkins process executable")
require("jenkins_upgrade_final_java_dependencies" in verify
        and "package_dependencies |" in verify,
        "final verification does not prove exact Temurin dependency versions")
require("jenkins_upgrade_final_failed_plugins" in verify
        and "Failed Loading plugin" in verify,
        "final verification does not reject failed plugin loading")
require("core_managed_detached" in verify,
        "final verification does not model Core-managed detached plugins")
require("with_dependencies=false" in reconcile
        and "Restore reconciliation plugins after failure" in reconcile,
        "post-upgrade reconciliation is not exact or rollback-safe")
require("tasks_from: upgrade-reconcile" in playbook
        and "tags: [never, reconcile]" in playbook,
        "reconciliation entry point is not isolated and opt-in")
require("common" not in playbook and "tailscale" not in playbook
        and "tasks_from: upgrade" in playbook,
        "upgrade playbook includes the full deployment path")

# Execute production-reused validation units for every matrix failure. An empty
# temporary config avoids the repository's legitimate, gitignored Vault helper.
with tempfile.NamedTemporaryFile(suffix=".cfg") as config_file:
    environment = os.environ.copy()
    environment["ANSIBLE_CONFIG"] = config_file.name
    environment["ANSIBLE_ROLES_PATH"] = str(ANSIBLE / "roles")
    gate_render = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            "localhost,",
            "tests/jenkins-upgrade/render.yml",
        ],
        cwd=ANSIBLE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
require(
    gate_render.returncode == 0,
    "real Ansible gate render failed: "
    + (gate_render.stdout + gate_render.stderr)[-2000:],
)

report = {
    "schema_version": 1,
    "status": "pass" if not failures else "fail",
    "lock_sha256": computed_lock_sha256,
    "plugin_count": len(lock),
    "matrix_cases": [
        "authorized-valid-lock",
        "missing-authorization",
        "missing-restore-evidence",
        "source-drift",
        "duplicate-artifact",
        "incomplete-lock",
        "checksum-mismatch",
    ],
    "failures": failures,
}
print(json.dumps(report, indent=2, sort_keys=True))
sys.exit(0 if not failures else 1)
