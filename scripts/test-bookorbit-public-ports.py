#!/usr/bin/env python3
"""Test public-port probe classification without opening network connections."""

from contextlib import redirect_stderr, redirect_stdout
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


SPEC = importlib.util.spec_from_file_location(
    "bookorbit_public_ports", Path(__file__).with_name("check-bookorbit-public-ports.py")
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class PublicPortProbeTests(unittest.TestCase):
    def probe(self, results):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(sys, "argv", ["probe", "--host", "192.0.2.1"]), \
                patch.object(PROBE.socket, "create_connection", side_effect=results) as connect, \
                redirect_stdout(output):
            code = PROBE.main()
        return code, json.loads(output.getvalue()), connect

    def test_timeout_and_refusal_are_closed_after_https_control(self):
        code, report, connect = self.probe([
            MagicMock(), TimeoutError(), OSError(errno.ECONNREFUSED, "refused"),
        ])
        self.assertEqual(code, 0)
        self.assertTrue(report["control_reachable"])
        self.assertTrue(report["success"])
        self.assertEqual([item["reachable"] for item in report["ports"]], [False, False])
        self.assertEqual([call.args[0][1] for call in connect.call_args_list], [443, 3000, 5432])

    def test_legacy_socket_timeout_is_closed(self):
        # Python 3.9 on macOS uses a distinct socket.timeout class.
        class LegacySocketTimeout(OSError):
            pass

        with patch.object(PROBE.socket, "timeout", LegacySocketTimeout):
            code, report, _ = self.probe([
                MagicMock(), LegacySocketTimeout("timed out"),
                OSError(errno.ECONNREFUSED, "refused"),
            ])
        self.assertEqual(code, 0)
        self.assertTrue(report["success"])

    def test_etimedout_is_closed(self):
        code, report, _ = self.probe([
            MagicMock(), OSError(errno.ETIMEDOUT, "timed out"), TimeoutError(),
        ])
        self.assertEqual(code, 0)
        self.assertTrue(report["success"])

    def test_local_and_network_errors_are_indeterminate_after_https_control(self):
        for error in (PermissionError(errno.EACCES, "denied"),
                      OSError(errno.ENETUNREACH, "network unreachable"),
                      OSError(errno.EHOSTUNREACH, "host unreachable"),
                      OSError(errno.ENETDOWN, "network down"),
                      OSError("unclassified failure")):
            with self.subTest(error=repr(error)):
                code, report, connect = self.probe([MagicMock(), error, TimeoutError()])
                self.assertEqual(code, 2)
                self.assertTrue(report["control_reachable"])
                self.assertFalse(report["success"])
                self.assertIsNone(report["ports"][0]["reachable"])
                self.assertEqual(report["ports"][0]["status"], "indeterminate")
                self.assertEqual(connect.call_count, 3)

    def test_open_port_fails(self):
        code, report, _ = self.probe([MagicMock(), MagicMock(), TimeoutError()])
        self.assertEqual(code, 1)
        self.assertFalse(report["success"])

    def test_failed_https_control_stops_probe(self):
        code, report, connect = self.probe([TimeoutError()])
        self.assertEqual(code, 2)
        self.assertFalse(report["control_reachable"])
        self.assertEqual(report["ports"], [])
        self.assertEqual(connect.call_count, 1)

    def test_sandbox_is_rejected_before_any_connection(self):
        with patch.dict(os.environ, {"SANDBOX_ID": "test"}), \
                patch.object(sys, "argv", ["probe", "--host", "192.0.2.1"]), \
                patch.object(PROBE.socket, "create_connection") as connect, \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
            PROBE.main()
        self.assertEqual(failure.exception.code, 2)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
