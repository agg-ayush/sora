"""The launcher starts a fresh tmux server outside the gateway's systemd unit."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("tmux_scope_launcher", _ROOT / "plugin" / "__init__.py")
assert _spec and _spec.loader
launcher = importlib.util.module_from_spec(_spec)
sys.modules["tmux_scope_launcher"] = launcher
_spec.loader.exec_module(launcher)

CMD = ["tmux", "new-session", "-d", "-s", "t2-x", "true"]


def _result(code):
    return subprocess.CompletedProcess([], code, "", "")


class DetachedTmuxLaunchTest(unittest.TestCase):
    def test_new_server_on_linux_gets_its_own_scope(self):
        with patch.object(launcher.sys, "platform", "linux"), \
             patch.object(launcher.shutil, "which", return_value="/usr/bin/systemd-run"), \
             patch.object(launcher, "_run", return_value=_result(1)):
            self.assertEqual(launcher._detached_tmux_launch(CMD),
                             ["systemd-run", "--user", "--scope", "--quiet", "--collect", *CMD])

    def test_running_server_is_reused_as_is(self):
        with patch.object(launcher.sys, "platform", "linux"), \
             patch.object(launcher.shutil, "which", return_value="/usr/bin/systemd-run"), \
             patch.object(launcher, "_run", return_value=_result(0)):
            self.assertEqual(launcher._detached_tmux_launch(CMD), CMD)

    def test_macos_is_unchanged(self):
        with patch.object(launcher.sys, "platform", "darwin"):
            self.assertEqual(launcher._detached_tmux_launch(CMD), CMD)

    def test_linux_without_systemd_run_is_unchanged(self):
        with patch.object(launcher.sys, "platform", "linux"), \
             patch.object(launcher.shutil, "which", return_value=None):
            self.assertEqual(launcher._detached_tmux_launch(CMD), CMD)


if __name__ == "__main__":
    unittest.main()
