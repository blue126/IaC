#!/usr/bin/env python3
"""Validate BookOrbit offline with fake credentials."""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "ansible/roles/bookorbit"
APP_IMAGE = "ghcr.io/bookorbit/bookorbit:3.3.0@sha256:4c2a1b957a3c8aeb9f59bb27a7d8efb18fa42c758afed3dcfc62620c5bcd1831"
DB_IMAGE = "pgvector/pgvector:pg18@sha256:2358fcba361ed2233a5ed81b5fe4ca779ccb304120ce531a3bf51c0ed7e2bc11"
SECRET_NAMES = (
    "db_password",
    "jwt_secret",
    "podcast_encryption_key",
    "setup_bootstrap_token",
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load_yaml(path):
    return yaml.safe_load(path.read_text())


def flatten(tasks):
    for task in tasks:
        yield task
        for section in ("block", "rescue", "always"):
            yield from flatten(task.get(section, []))


def main():
    for command in ("ansible-playbook", "ansible-lint", "docker"):
        require(shutil.which(command), f"Required existing tool is unavailable: {command}")

    # Keep artifacts under this worktree. Never load its production inventory or Vault.
    (ROOT / "tmp").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="bookorbit-validation-", dir=ROOT / "tmp"))
    rendered = output / "rendered"
    rendered.mkdir(mode=0o700)
    inventory = output / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {"hosts": {"oracle-cloud-ubuntu2404": {
        "ansible_connection": "local",
        "ansible_host": "127.0.0.1",
        "ansible_python_interpreter": sys.executable,
        "bookorbit_public_domain": "bookorbit.example.test",
        "anki_writer_public_domain": "ankiwriter.example.test",
        "proxy_domain": "proxy.example.test",
    }}}}))
    config = output / "ansible.cfg"
    config.write_text(
        "[defaults]\n"
        f"inventory = {inventory}\n"
        f"roles_path = {ROOT / 'ansible/roles'}\n"
        f"collections_path = {ROOT / 'ansible/collections'}:~/.ansible/collections\n"
        "retry_files_enabled = False\n"
        "host_key_checking = True\n"
        f"local_tmp = {output / 'ansible-local'}\n"
        f"remote_tmp = {output / 'ansible-remote'}\n"
    )
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("ANSIBLE_", "COMPOSE_"))}
    environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_NOCOLOR="1")
    fake = {f"vault_bookorbit_{name}": str(index) * 64
            for index, name in enumerate(SECRET_NAMES, start=1)}
    fake.update(
        bookorbit_base_dir="/opt/bookorbit",
        bookorbit_public_domain="bookorbit.example.test",
        bookorbit_bootstrap_token_file=str(rendered / "bootstrap-token"),
    )

    def run(argv, *, expected_success=True, env=None):
        result = subprocess.run(argv, cwd=ROOT, env=env or environment,
                                text=True, capture_output=True, check=False)
        transcript = result.stdout + result.stderr
        # Even --diff must not reveal any of the secret-shaped fake values.
        require(not any(str(index) * 64 in transcript for index in range(1, 5)),
                f"Credential disclosure in output from {argv[0]}")
        if expected_success and result.returncode != 0:
            raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(map(str, argv))}\n{transcript}")
        if not expected_success:
            require(result.returncode != 0, "Invalid configuration was accepted")
        return result

    defaults = load_yaml(ROLE / "defaults/main.yml")
    for name in SECRET_NAMES:
        require(defaults[f"bookorbit_{name}"] == "{{ vault_bookorbit_" + name + " }}",
                "Secrets must be indirect Vault references")
    tasks = load_yaml(ROLE / "tasks/main.yml")
    env_task = next(task for task in tasks if task.get("ansible.builtin.template", {}).get("src") == "env.j2")
    compose_task = next(task for task in tasks if task.get("ansible.builtin.template", {}).get("src") == "docker-compose.yml.j2")
    token_task = next(task for task in tasks if "ansible.builtin.copy" in task)
    for task, module in ((env_task, "ansible.builtin.template"), (token_task, "ansible.builtin.copy")):
        require(task.get("no_log") is True and task.get("diff") is False,
                "Credential writes must suppress logs and diffs")
        require(task[module]["mode"] == "0600", "Credential files must use mode 0600")
    require(token_task.get("delegate_to") == "localhost" and token_task.get("become") is False,
            "Bootstrap token must be delivered to the local unprivileged account")
    compose_action = next(task for task in tasks if "community.docker.docker_compose_v2" in task)
    options = compose_action["community.docker.docker_compose_v2"]
    require(options.get("state") == "present" and options.get("recreate") == "auto"
            and options.get("pull") == "missing" and options.get("wait") is True,
            "Compose must preserve existing services and wait for health without forced recreation")
    require(compose_action.get("no_log") is True, "Compose output may contain sensitive environment data")
    for task in flatten(tasks):
        require(task.get("ansible.builtin.file", {}).get("state") != "absent", "Deployment must never remove data")
        require(not task.get("ansible.builtin.file", {}).get("recurse"), "Deployment must not recursively change existing data")
    postgres_directory = next(task["ansible.builtin.file"] for task in tasks
                              if task.get("ansible.builtin.file", {}).get("path") == "{{ bookorbit_base_dir }}/data/postgres")
    require("owner" not in postgres_directory and "group" not in postgres_directory,
            "Reruns must preserve PostgreSQL directory ownership")
    require(postgres_directory["mode"] == "0755", "The postgres user must traverse the mounted parent after dropping root")
    layout_guard_index = next(index for index, task in enumerate(tasks)
                              if task.get("ansible.builtin.import_tasks") == "validate-data-layout.yml")
    first_write_index = next(index for index, task in enumerate(tasks)
                             if any(key in task for key in ("ansible.builtin.file", "ansible.builtin.template",
                                                            "ansible.builtin.copy", "community.docker.docker_compose_v2")))
    require(layout_guard_index < first_write_index, "Legacy database detection must precede deployment writes")

    # Exercise the actual filesystem guard and parent-directory task. The private
    # child fixtures model entrypoint-owned PGDATA; no database container is started.
    layout_playbook = output / "layout.yml"
    layout_playbook.write_text(yaml.safe_dump([{
        "name": "Validate PostgreSQL layout with fake data", "hosts": "all", "gather_facts": False,
        "become": False, "tasks": [
            {"name": "Guard legacy data", "ansible.builtin.import_tasks": str(ROLE / "tasks/validate-data-layout.yml")},
            {"name": "Prepare the real PostgreSQL parent directory", "ansible.builtin.file": postgres_directory},
        ],
    }], sort_keys=False))
    for case in ("fresh", "failed-bootstrap", "initialized-legacy", "initialized-pg18"):
        base = output / f"layout-{case}"
        parent = base / "data/postgres"
        child = None
        marker = None
        if case != "fresh":
            parent.mkdir(parents=True, mode=0o700)
            child = parent / ("18/docker" if case == "initialized-pg18" else "pgdata")
            child.mkdir(parents=True, mode=0o700)
            child_before = (child.stat().st_mode, child.stat().st_uid, child.stat().st_gid)
            if case.startswith("initialized"):
                marker = child / "PG_VERSION"
                marker.write_text("18\n")
                marker_before = (marker.read_bytes(), marker.stat().st_mtime_ns)
        variables = output / f"layout-{case}-vars.yml"
        variables.write_text(yaml.safe_dump({"bookorbit_base_dir": str(base)}))
        command = ["ansible-playbook", str(layout_playbook), "--extra-vars", f"@{variables}"]
        result = run(command, expected_success=case != "initialized-legacy")
        if case == "initialized-legacy":
            require("An initialized database exists" in result.stdout, "Legacy data must fail at the migration guard")
            require(stat.S_IMODE(parent.stat().st_mode) == 0o700, "Rejected layout changed the existing parent")
        else:
            require(stat.S_IMODE(parent.stat().st_mode) == 0o755, "Mounted PostgreSQL parent is not traversable")
            repeated = run(command)
            require(re.search(r"changed=0\s+", repeated.stdout), "Layout preparation must be idempotent")
        if child is not None:
            require(child_before == (child.stat().st_mode, child.stat().st_uid, child.stat().st_gid),
                    "Layout preparation changed a private existing PGDATA directory")
        if marker is not None:
            require(marker_before == (marker.read_bytes(), marker.stat().st_mtime_ns), "Existing database marker changed")
    print("PASS: PG18 parent traversal, private child preservation, failed-bootstrap recovery and legacy database guard")

    # Render the real credential/template tasks locally, changing only destinations
    # and ownership; their modes and no_log/diff protection remain under test.
    local_tasks = [{"name": "Validate fake inputs", "ansible.builtin.import_tasks": str(ROLE / "tasks/validate.yml")}]
    for original, destination in ((env_task, ".env"), (compose_task, "docker-compose.yml")):
        task = copy.deepcopy(original)
        params = task["ansible.builtin.template"]
        params["src"] = str(ROLE / "templates" / params["src"])
        params["dest"] = str(rendered / destination)
        params.update(owner=str(os.getuid()), group=str(os.getgid()))
        local_tasks.append(task)
    local_tasks.append(copy.deepcopy(token_task))
    local_play = [{"name": "Validate BookOrbit with fake data", "hosts": "all", "gather_facts": False,
                   "become": False, "vars_files": [str(ROLE / "defaults/main.yml")], "tasks": local_tasks}]
    render_playbook = output / "render.yml"
    render_playbook.write_text(yaml.safe_dump(local_play, sort_keys=False))
    fake_file = output / "fake-vars.yml"
    fake_file.write_text(yaml.safe_dump(fake))
    render_command = ["ansible-playbook", str(render_playbook), "--extra-vars", f"@{fake_file}", "--diff"]
    run(render_command)
    secret_paths = [rendered / ".env", rendered / "bootstrap-token"]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in secret_paths}
    for path in secret_paths:
        require(stat.S_IMODE(path.stat().st_mode) == 0o600, "Rendered credentials have unsafe permissions")
    sentinel = rendered / "preserved-library.epub"
    sentinel.write_bytes(b"existing library data")
    rerun = run(render_command)
    require(re.search(r"changed=0\s+", rerun.stdout), "Identical configuration must not change on rerun")
    require(before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in secret_paths},
            "Rerun rewrote stable credentials")
    require(sentinel.read_bytes() == b"existing library data", "Rerun changed existing library data")
    print("PASS: real templates, local token delivery, secret masking and unchanged rerun")

    # Exercise the actual role assertions before any Docker or remote activity.
    guard_playbook = output / "guard.yml"
    guard_play = copy.deepcopy(local_play)
    guard_play[0]["tasks"] = local_tasks[:1]
    guard_playbook.write_text(yaml.safe_dump(guard_play, sort_keys=False))
    invalid = []
    missing = dict(fake)
    del missing["vault_bookorbit_jwt_secret"]
    invalid.append(("missing-secret", missing))
    for label, key, value in (
        ("empty-token", "vault_bookorbit_setup_bootstrap_token", ""),
        ("interpolation", "vault_bookorbit_db_password", "${UNSAFE}"),
        ("newline", "vault_bookorbit_db_password", "1" * 64 + "\n"),
        ("reused-key", "vault_bookorbit_podcast_encryption_key", "2" * 64),
        ("invalid-domain", "bookorbit_public_domain", "bad.example.test {\n}"),
        ("base-root", "bookorbit_base_dir", "/"),
        ("base-double-leading-slash", "bookorbit_base_dir", "//opt/bookorbit"),
        ("base-double-inner-slash", "bookorbit_base_dir", "/opt//bookorbit"),
        ("base-trailing-slash", "bookorbit_base_dir", "/opt/bookorbit/"),
        ("base-trailing-newline", "bookorbit_base_dir", "/opt/bookorbit\n"),
        ("uid-boolean", "bookorbit_uid", True),
        ("uid-fraction", "bookorbit_uid", 1000.5),
        ("gid-boolean", "bookorbit_gid", True),
        ("gid-fraction", "bookorbit_gid", 1000.5),
    ):
        invalid.append((label, {**fake, key: value}))
    for label, values in invalid:
        path = output / f"{label}.yml"
        path.write_text(yaml.safe_dump(values))
        run(["ansible-playbook", str(guard_playbook), "--extra-vars", f"@{path}"], expected_success=False)
    print("PASS: invalid secrets, domain, noncanonical base paths and noninteger UID/GID rejected")

    tagged_config = run([
        "ansible-playbook", str(ROOT / "ansible/playbooks/deploy-bookorbit-oci.yml"),
        "--tags", "config", "--extra-vars", f"@{output / 'invalid-domain.yml'}",
    ], expected_success=False)
    require("BookOrbit public domain must be a single valid DNS hostname" in tagged_config.stdout,
            "Config-tagged execution must reject an invalid domain at its own guard")
    require("TASK [Configure BookOrbit Caddy site]" not in tagged_config.stdout,
            "Invalid config-tagged domain reached Caddy")
    print("PASS: --tags config rejects invalid domains before entering Caddy")

    env_values = dict(line.split("=", 1) for line in (rendered / ".env").read_text().splitlines()
                      if line and not line.startswith("#"))
    compose_environment = {key: value for key, value in environment.items() if key not in env_values}
    compose = ["docker", "compose", "--project-name", "bookorbit-validation", "--env-file",
               str(rendered / ".env"), "-f", str(rendered / "docker-compose.yml"), "config"]
    run([*compose, "--quiet"], env=compose_environment)
    # Compose's normalized JSON contains only these known fake credentials. Keep it in memory.
    normalized = subprocess.run([*compose, "--format", "json"], cwd=ROOT, env=compose_environment,
                                text=True, capture_output=True, check=False)
    require(normalized.returncode == 0, "Cannot normalize rendered Compose")
    services = json.loads(normalized.stdout)["services"]
    require(set(services) == {"app", "postgres"}, "Exactly two services are required")
    app, database = services["app"], services["postgres"]
    require(app["image"] == APP_IMAGE and database["image"] == DB_IMAGE, "Approved image digests changed")
    require(len(app["ports"]) == 1 and app["ports"][0]["host_ip"] == "127.0.0.1"
            and str(app["ports"][0]["published"]) == "3000" and app["ports"][0]["target"] == 3000,
            "Application must bind only 127.0.0.1:3000")
    require(not database.get("ports"), "PostgreSQL must not publish a port")
    require(not app.get("network_mode") and not database.get("network_mode"), "Host networking is forbidden")
    for service, mounts in ((app, {"/books": "/opt/bookorbit/books", "/data": "/opt/bookorbit/data/app"}),
                            (database, {"/var/lib/postgresql": "/opt/bookorbit/data/postgres"})):
        require({mount["target"]: mount["source"] for mount in service["volumes"]} == mounts,
                "Persistent bind mounts changed")
        require(all(mount["type"] == "bind" for mount in service["volumes"]), "Data must persist under /opt/bookorbit")
        require(service["healthcheck"].get("test"), "Both services require health checks")
    require(database["environment"]["PGDATA"] == "/var/lib/postgresql/18/docker", "PostgreSQL must use the PG18 private child layout")
    require(app["read_only"] is True and "/tmp" in app["tmpfs"] and app["init"] is True,
            "Upstream application filesystem constraints changed")
    require(set(app["cap_drop"]) == {"ALL"} and set(app["cap_add"]) == {"CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"},
            "Upstream startup capabilities changed")
    require("no-new-privileges:true" in app["security_opt"] and "user" not in app,
            "Upstream privilege drop must remain in the entrypoint")
    require(app["depends_on"]["postgres"]["condition"] == "service_healthy", "App must wait for PostgreSQL")
    require(app["environment"] == env_values, "Compose must preserve the complete application environment")
    require((rendered / "bootstrap-token").read_text() == fake["vault_bookorbit_setup_bootstrap_token"] + "\n"
            and app["environment"]["SETUP_BOOTSTRAP_TOKEN"] == fake["vault_bookorbit_setup_bootstrap_token"],
            "Delivered token, fake Vault value and application bootstrap token must match")
    require(app["environment"]["APP_URL"] == "https://bookorbit.example.test"
            and app["environment"]["LIBRARY_BROWSE_ROOT"] == "/books"
            and app["environment"]["DISABLE_LOCAL_AUTH"] == "false", "Application URL or setup environment changed")
    print("PASS: docker compose config --quiet, private ports, persistent data and upstream permissions")

    proxy_tasks = list(flatten(load_yaml(ROOT / "ansible/roles/caddy/tasks/reverse-proxy.yml")))
    candidate_index = next(index for index, task in enumerate(proxy_tasks) if task["name"] == "Validate managed Caddy candidate")
    publishes = [index for index, task in enumerate(proxy_tasks) if "notify" in task]
    require(publishes and all(index > candidate_index for index in publishes), "Caddy must validate before publishing or reloading")
    candidate = proxy_tasks[candidate_index]
    require(candidate.get("check_mode") is False and not candidate.get("ignore_errors")
            and "failed_when" not in candidate, "Invalid Caddy candidates must stop publication")
    playbook = ROOT / "ansible/playbooks/deploy-bookorbit-oci.yml"
    plays = load_yaml(playbook)
    proxy = next(task["ansible.builtin.include_role"] for task in plays[1]["tasks"]
                 if "ansible.builtin.include_role" in task)
    require(proxy["name"] == "caddy" and proxy["tasks_from"] == "reverse-proxy", "Reuse existing-install Caddy tasks")
    require("verify" not in plays[0].get("tags", []) and "verify" not in plays[1].get("tags", []),
            "Verify tag must not deploy")
    verify_tasks = load_yaml(ROLE / "tasks/verify.yml")
    allowed = {"ansible.builtin.uri", "ansible.builtin.assert", "ansible.builtin.stat", "ansible.builtin.wait_for",
               "ansible.builtin.debug", "community.docker.docker_container_info"}
    for task in flatten(verify_tasks):
        modules = set(task) & allowed
        require(len(modules) == 1, "Verify may only use read-only modules")
        if "ansible.builtin.uri" in task:
            require(task["ansible.builtin.uri"].get("method", "GET") == "GET", "Verify must not create an administrator")
        if "community.docker.docker_container_info" in task:
            require(task.get("no_log") is True, "Container environment must never reach logs")
    print("PASS: Caddy candidate validation order and read-only verification boundary")

    run([sys.executable, str(ROOT / "scripts/test-bookorbit-public-ports.py")])
    print("PASS: public-port probe errors, HTTPS control and Sandbox rejection without network requests")
    run(["ansible-playbook", str(playbook), "--syntax-check", "--extra-vars", f"@{fake_file}"])
    print("PASS: ansible-playbook --syntax-check with isolated fake inventory")
    run(["ansible-lint", "--offline", "-c", str(ROOT / ".ansible-lint"), str(playbook), str(ROLE)])
    print("PASS: ansible-lint --offline")
    print(f"Validation artifacts: {output}")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
