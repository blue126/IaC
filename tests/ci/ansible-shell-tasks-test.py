#!/usr/bin/env python3
"""Exercise changed shell probes with fake commands; never contact a host."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


def task_named(path, name):
    def search(value):
        if isinstance(value, dict):
            if value.get("name") == name:
                return value
            for item in value.values():
                found = search(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = search(item)
                if found is not None:
                    return found
        return None

    task = search(yaml.safe_load((ROOT / path).read_text()))
    if task is None:
        raise AssertionError(f"Missing task: {name}")
    return task


class ShellProbeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bin = Path(self.temp.name)
        self.output = self.bin / "output.txt"
        for command in ["docker", "gitea", "journalctl"]:
            path = self.bin / command
            path.write_text('#!/bin/bash\ncat "$PROBE_OUTPUT"\nexit "$PROBE_RC"\n')
            path.chmod(0o755)
        systemctl = self.bin / "systemctl"
        systemctl.write_text('#!/bin/bash\nprintf "2026-09-05 12:00:00 UTC\\n"\nexit "${PROBE_SYSTEMCTL_RC:-0}"\n')
        systemctl.chmod(0o755)

    def run_probe(self, path, name, output="", rc=0, **extra_env):
        task = task_named(path, name)
        script = task.get("shell", task.get("ansible.builtin.shell"))
        replacements = {
            "gitea_binary_path | quote": str(self.bin / "gitea"),
            "(gitea_config_dir + '/app.ini') | quote": "/fixture/app.ini",
            "gitea_admin_user | quote": "admin",
        }
        script = re.sub(r"{{\s*(.*?)\s*}}",
                        lambda match: shlex.quote(replacements[match[1]]), script)
        self.output.write_text(output)
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                   PROBE_OUTPUT=str(self.output), PROBE_RC=str(rc), **extra_env)
        return subprocess.run(["/bin/bash", "-c", script], env=env,
                              text=True, capture_output=True, timeout=15)

    def test_container_counts_and_upstream_failures(self):
        probes = [
            ("ansible/playbooks/deploy-immich.yml", "Count running containers",
             "server Up\ndatabase Up\n", "2"),
            ("ansible/playbooks/deploy-netbox.yml", "Check for healthy containers",
             "netbox Up (healthy)\npostgres Up (healthy)\n", "1"),
        ]
        for path, name, output, expected in probes:
            with self.subTest(task=name):
                result = self.run_probe(path, name, output)
                self.assertEqual((result.returncode, result.stdout.strip()), (0, expected))
                result = self.run_probe(path, name)
                self.assertEqual((result.returncode, result.stdout.strip()), (0, "0"))
                self.assertEqual(self.run_probe(path, name, output, rc=7).returncode, 7)

    def test_gitea_exact_match_large_output_and_command_failure(self):
        path, name = "ansible/roles/gitea/tasks/main.yml", "Check if Gitea admin user exists"
        self.assertEqual(self.run_probe(path, name, "ID Username\n1 myadmin\n").returncode, 1)
        users = "ID Username\n1 admin\n" + "2 anotheruser\n" * 20000
        self.assertEqual(self.run_probe(path, name, users).returncode, 0)
        self.assertEqual(self.run_probe(path, name, rc=1).returncode, 2)

    def test_jenkins_count_and_read_failures(self):
        path = "ansible/roles/jenkins/tasks/upgrade-verify.yml"
        name = "Count failed plugins in the current Jenkins service invocation"
        result = self.run_probe(path, name, "Failed Loading plugin one\nStarted Jenkins\n")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "1"))
        self.assertEqual(self.run_probe(path, name, rc=7).returncode, 7)
        self.assertEqual(self.run_probe(path, name, PROBE_SYSTEMCTL_RC="8").returncode, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
