"""Watchdog and auth-canary relay behavior without real network sends."""

import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WatchdogRelayTests(unittest.TestCase):
    def setUp(self):
        self.relay = load_script("_alert_relay", "_alert_relay.py")
        self.watchdog = load_script("watchdog", "watchdog.py")

    def test_ssh_channel_preserves_target(self):
        self.assertEqual(self.relay.relay_destination("ssh:devbox:telegram"), ("devbox", "telegram"))
        self.assertEqual(self.relay.relay_destination("ssh:devbox:telegram:thread"), ("devbox", "telegram:thread"))

    def test_plain_channel_is_local(self):
        self.assertIsNone(self.relay.relay_destination("telegram"))
        self.assertIsNone(self.relay.relay_destination("telegram:1234"))

    def test_invalid_ssh_channel_rejected(self):
        for channel in ("ssh:devbox:", "ssh::telegram", "ssh:devbox", "ssh:-evil:telegram"):
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                self.relay.relay_destination(channel)

    @mock.patch("subprocess.run")
    def test_watchdog_ssh_alert_quotes_body_in_remote_command(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "sent", "")
        body = "alert with 'quotes' and $(touch /bad)\nsecond line"
        with contextlib.redirect_stdout(io.StringIO()):
            self.watchdog.alert([body], "ssh:devbox:telegram", False)
        args, kwargs = run.call_args
        self.assertEqual(args[0][:6], ["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", "devbox"])
        self.assertIn('"$HOME/.local/bin/hermes" send -t telegram ', args[0][6])
        self.assertIn("'\"'\"'", args[0][6])
        self.assertIn("$(touch /bad)", args[0][6])
        self.assertEqual(kwargs["capture_output"], True)
        self.assertEqual(kwargs["text"], True)

    @mock.patch("subprocess.run")
    def test_watchdog_plain_target_keeps_local_send(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with contextlib.redirect_stdout(io.StringIO()):
            self.watchdog.alert(["problem"], "telegram:1234", False)
        self.assertEqual(run.call_args.args[0][1:4], ["send", "-t", "telegram:1234"])
        self.assertNotIn("ssh", run.call_args.args[0][0])

    @mock.patch("subprocess.run")
    def test_watchdog_ssh_failure_logs_and_still_notifies(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "delivery error")
        with mock.patch.object(self.watchdog._platform, "HAS_DESKTOP", True), mock.patch.object(self.watchdog._platform, "notify") as notify, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.watchdog.alert(["problem"], "ssh:devbox:telegram", True)
        self.assertIn("ALERT TO SSH:DEVBOX:TELEGRAM FAILED (exit 1)", stderr.getvalue())
        notify.assert_called_once()

    @mock.patch("subprocess.run")
    def test_gateway_status_requests_full_report(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "◆ Gateway Service\n  Status:       ✓ running\n", "")
        problems = []
        self.watchdog.check_gateway(problems)
        self.assertEqual(problems, [])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [str(Path.home() / ".local/bin/hermes"), "status", "--full"])

    @mock.patch("subprocess.run")
    def test_gateway_status_falls_back_when_full_is_rejected(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 2, "", "unrecognized arguments: --full"),
            subprocess.CompletedProcess([], 0, "◆ Gateway Service\n  Status:       ✓ running\n", ""),
        ]
        problems = []
        self.watchdog.check_gateway(problems)
        self.assertEqual(problems, [])
        self.assertEqual(run.call_args_list[1].args[0], [str(Path.home() / ".local/bin/hermes"), "status"])

    @mock.patch("subprocess.run")
    def test_gateway_summary_without_block_is_reported(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "  Gateway:      ✓ running\n", "")
        problems = []
        self.watchdog.check_gateway(problems)
        self.assertEqual(problems, ["could not find the Gateway Service status block in `hermes status` output"])

    @mock.patch("subprocess.run")
    def test_cron_list_uses_launcher(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.watchdog.check_jobs([], [], None, [])
        self.assertEqual(run.call_args.args[0], [str(Path.home() / ".local/bin/hermes"), "cron", "list"])


class CanaryRelayTests(unittest.TestCase):
    def setUp(self):
        self.wrapper = load_script("auth_canary_relay", "auth-canary-relay.py")

    @mock.patch("subprocess.run")
    def test_silent_canary_never_sends(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(self.wrapper, "send_alert") as send, contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.wrapper.main()
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "")
        send.assert_not_called()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [sys.executable, str(SCRIPTS / "auth-canary.py")])

    @mock.patch("subprocess.run")
    def test_nonempty_canary_relays_and_records_locally(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "## alarm\n", "")
        with mock.patch.object(self.wrapper, "send_alert", return_value=subprocess.CompletedProcess([], 0, "sent", "")) as send, contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.wrapper.main()
        self.assertEqual(status, 0)
        send.assert_called_once_with("ssh:devbox:telegram", "## alarm\n")
        self.assertEqual(output.getvalue(), "auth-canary-relay: sent via ssh:devbox:telegram\n")

    @mock.patch("subprocess.run")
    def test_canary_exit_code_preserved(self, run):
        run.return_value = subprocess.CompletedProcess([], 2, "", "database error\n")
        with mock.patch.object(self.wrapper, "send_alert") as send, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = self.wrapper.main()
        self.assertEqual(status, 2)
        self.assertEqual(stderr.getvalue(), "database error\n")
        send.assert_not_called()

    @mock.patch("subprocess.run")
    def test_relay_failure_logs_but_preserves_canary_exit(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "## alarm\n", "")
        with mock.patch.object(self.wrapper, "send_alert", return_value=subprocess.CompletedProcess([], 1, "", "send failure")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = self.wrapper.main()
        self.assertEqual(status, 0)
        self.assertIn("ALERT TO SSH:DEVBOX:TELEGRAM FAILED (exit 1)", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
