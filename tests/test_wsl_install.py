"""WSL2 install: platform detection, profile selection, WSL preflight, bootstrap and line endings.

Shell code runs under a fake `uname` and stub tools in a scratch HOME, so nothing touches the real
machine, network or service manager.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PLATFORM = _ROOT / "devbox" / "platform.sh"
_BOOTSTRAP = _ROOT / "devbox" / "bootstrap-wsl.sh"
_HOST_PROFILE = _ROOT / "devbox" / "host-profile.sh"
_SETUP = _ROOT / "devbox" / "setup-hermes.sh"
_WSL = _ROOT / "hosts" / "wsl"

WSL2_OSRELEASE = "5.15.167.4-microsoft-standard-WSL2\n"
WSL1_VERSION = "Linux version 4.4.0-19041-Microsoft (Microsoft@Microsoft.com) (gcc version 5.4.0) #1-Microsoft\n"
EC2_OSRELEASE = "6.8.0-1021-aws\n"
EC2_VERSION = "Linux version 6.8.0-1021-aws (buildd@lcy02-amd64-001) (x86_64-linux-gnu-gcc-13) #22-Ubuntu SMP\n"


def _write_exe(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _hermes_stub(calls: Path, state: Path) -> str:
    """A hermes CLI that remembers created cron jobs, installed plugins and pm packages.

    `gateway install` writes a user gateway unit; HERMES_STUB_GATEWAY_FAIL=1 makes it fail instead.
    """
    return textwrap.dedent(f"""\
        echo "hermes $*" >> {calls}
        mkdir -p {state}
        case "$1 $2" in
          "cron list") [ -f {state}/cron ] && sed 's/^/  Name: /' {state}/cron; exit 0 ;;
          "cron create") while [ $# -gt 0 ]; do [ "$1" = --name ] && echo "$2" >> {state}/cron; shift; done; exit 0 ;;
          "plugins list") [ -f {state}/plugins ] && sed 's/^/enabled local /' {state}/plugins; exit 0 ;;
          "plugins install") echo "${{3##*/}}" >> {state}/plugins; exit 0 ;;
          "pm install") mkdir -p "${{HERMES_HOME:-$HOME/.hermes}}/tools/$3-stub"; exit 0 ;;
          "gateway install") [ -z "${{HERMES_STUB_GATEWAY_FAIL:-}}" ] || {{ echo "gateway: boom" >&2; exit 1; }}
            mkdir -p "$HOME/.config/systemd/user" && echo "[Unit]" > "$HOME/.config/systemd/user/hermes-gateway.service"; exit 0 ;;
        esac
        exit 0
        """)


class _Sandbox:
    """Scratch HOME, stub bin dir and fake /proc files for one shell run."""

    def __init__(self, tmp: Path, kernel: str = "Linux", osrelease: str = EC2_OSRELEASE, version: str = EC2_VERSION):
        self.tmp = tmp
        self.home = tmp / "home"
        self.bin = tmp / "stubs"
        self.calls = tmp / "calls.log"
        self.state = tmp / "hermes-state"
        self.home.mkdir()
        self.calls.touch()
        (tmp / "osrelease").write_text(osrelease)
        (tmp / "version").write_text(version)
        _write_exe(self.bin / "uname", f'echo {kernel}\n')
        # Never reach the real user manager: its bus is not scoped by HOME.
        _write_exe(self.bin / "systemctl", f'echo "systemctl $*" >> {self.calls}\nexit 1\n')
        _write_exe(self.bin / "launchctl", f'echo "launchctl $*" >> {self.calls}\nexit 1\n')
        # Only python3 from the test interpreter: its bin dir may also hold a real hermes.
        _write_exe(self.bin / "python3", f'exec "{sys.executable}" "$@"\n')
        self.env = {
            "HOME": str(self.home),
            "PATH": os.pathsep.join([str(self.bin), "/usr/bin", "/bin"]),
            "HERMES_PROC_OSRELEASE": str(tmp / "osrelease"),
            "HERMES_PROC_VERSION": str(tmp / "version"),
            "LANG": "C",
            "GIT_TERMINAL_PROMPT": "0",
        }

    def stub(self, name: str, body: str) -> None:
        _write_exe(self.bin / name, body)

    def run(self, script: str, extra_env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
        env = dict(self.env, **(extra_env or {}))
        return subprocess.run(["bash", "-c", script], cwd=_ROOT, env=env, capture_output=True, text=True, timeout=timeout)

    def calls_text(self) -> str:
        return self.calls.read_text()

    def stub_hermes(self, where: Path | None = None) -> None:
        _write_exe((where or self.bin) / "hermes", _hermes_stub(self.calls, self.state))


class _SandboxCase(unittest.TestCase):
    def sandbox(self, **kw) -> _Sandbox:
        d = tempfile.mkdtemp(prefix="wsl-test-")
        self.addCleanup(shutil.rmtree, d, True)
        return _Sandbox(Path(d), **kw)

    def profile(self, sb: _Sandbox, extra_env: dict | None = None) -> str:
        r = sb.run(f'. "{_PLATFORM}"; hermes_host_profile', extra_env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()


class DetectionTest(_SandboxCase):
    def test_wsl2_osrelease_is_wsl(self):
        self.assertEqual(self.profile(self.sandbox(osrelease=WSL2_OSRELEASE)), "wsl")

    def test_wsl1_style_proc_version_is_wsl(self):
        self.assertEqual(self.profile(self.sandbox(version=WSL1_VERSION)), "wsl")

    def test_distro_env_var_alone_is_wsl(self):
        self.assertEqual(self.profile(self.sandbox(), {"WSL_DISTRO_NAME": "Ubuntu"}), "wsl")

    def test_plain_linux_stays_sora(self):
        self.assertEqual(self.profile(self.sandbox()), "sora")

    def test_unreadable_proc_files_stay_sora(self):
        sb = self.sandbox()
        self.assertEqual(self.profile(sb, {"HERMES_PROC_OSRELEASE": "/nonexistent", "HERMES_PROC_VERSION": "/nonexistent"}), "sora")

    def test_darwin_stays_mac_even_with_wsl_markers(self):
        sb = self.sandbox(kernel="Darwin", osrelease=WSL2_OSRELEASE)
        self.assertEqual(self.profile(sb, {"WSL_DISTRO_NAME": "Ubuntu"}), "mac")

    def test_wsl_markers_on_darwin_are_not_wsl(self):
        sb = self.sandbox(kernel="Darwin", osrelease=WSL2_OSRELEASE)
        r = sb.run(f'. "{_PLATFORM}"; hermes_is_wsl && echo yes || echo no', {"WSL_DISTRO_NAME": "Ubuntu"})
        self.assertEqual(r.stdout.strip(), "no")

    def test_override_wins_everywhere(self):
        self.assertEqual(self.profile(self.sandbox(osrelease=WSL2_OSRELEASE), {"HERMES_HOST_PROFILE": "sora"}), "sora")
        self.assertEqual(self.profile(self.sandbox(), {"HERMES_HOST_PROFILE": "wsl"}), "wsl")
        self.assertEqual(self.profile(self.sandbox(kernel="Darwin"), {"HERMES_HOST_PROFILE": "wsl"}), "wsl")


class WindowsDriveTest(_SandboxCase):
    def on_drive(self, path: str, mnt: str | None = None) -> bool:
        env = {"HERMES_WSL_MNT": mnt} if mnt else {}
        r = self.sandbox().run(f'. "{_PLATFORM}"; hermes_on_windows_drive "{path}" && echo yes || echo no', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip() == "yes"

    def test_drive_paths(self):
        for path in ("/mnt/c", "/mnt/c/Users/u/x", "/mnt/D/tools/node"):
            self.assertTrue(self.on_drive(path), path)

    def test_non_drive_paths(self):
        for path in ("/mnt/wsl/docker-desktop/bin/node", "/mnt/wslg/x", "/mnt/cd/x", "/home/u/mnt/c/x", "/usr/bin/node"):
            self.assertFalse(self.on_drive(path), path)

    def test_mount_root_override(self):
        self.assertTrue(self.on_drive("/win/c/x", mnt="/win"))
        self.assertFalse(self.on_drive("/mnt/c/x", mnt="/win"))


class PreflightTest(_SandboxCase):
    def preflight(self, sb: _Sandbox, repo_dir: str = "/home/u/hermes-setup", persist: str = "", extra_env=None):
        r = sb.run(f'. "{_PLATFORM}"; hermes_wsl_preflight "{repo_dir}" {persist}; echo "BROWSER=${{BROWSER:-}}"',
                   dict({"WSL_DISTRO_NAME": "Ubuntu"}, **(extra_env or {})))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_windows_drive_checkout_warns(self):
        r = self.preflight(self.sandbox(), "/mnt/c/Users/u/hermes-setup")
        self.assertIn("Windows filesystem", r.stdout)
        self.assertIn("Linux home", r.stdout)

    def test_linux_home_checkout_does_not_warn(self):
        self.assertNotIn("Windows filesystem", self.preflight(self.sandbox()).stdout)

    def test_wsl_internal_mount_does_not_warn(self):
        self.assertNotIn("Windows filesystem", self.preflight(self.sandbox(), "/mnt/wsl/shared/hermes-setup").stdout)

    def test_no_systemd_gives_one_actionable_hint(self):
        out = self.preflight(self.sandbox()).stdout
        self.assertEqual(out.count("systemd is not running"), 1)
        self.assertIn("systemd=true", out)
        self.assertIn("[boot]", out)
        self.assertIn("wsl --shutdown", out)
        self.assertIn("HERMES_INSTALL_GATEWAY=true", out)

    def test_systemd_present_gives_no_hint(self):
        sb = self.sandbox()
        sb.stub("systemctl", "exit 0\n")
        self.assertNotIn("systemd is not running", self.preflight(sb).stdout)

    def test_browser_defaults_to_wslview_and_persists_once(self):
        sb = self.sandbox()
        sb.stub("wslview", "exit 0\n")
        (sb.home / ".zshrc").write_text("# zsh\n")
        r1 = self.preflight(sb, persist="persist")
        self.preflight(sb, persist="persist")
        self.assertIn("BROWSER=wslview", r1.stdout)
        for rc in (".bashrc", ".zshrc"):
            text = (sb.home / rc).read_text()
            self.assertEqual(text.count("hermes-setup: WSL login browser"), 1, rc)
            self.assertIn('if [ -z "${BROWSER:-}" ]', text)

    def test_user_browser_is_not_overridden(self):
        sb = self.sandbox()
        sb.stub("wslview", "exit 0\n")
        r = self.preflight(sb, extra_env={"BROWSER": "firefox"})
        self.assertIn("BROWSER=firefox", r.stdout)
        r = sb.run(f'. "{_PLATFORM}"; hermes_wsl_preflight /home/u/x persist >/dev/null; . "$HOME/.bashrc"; echo "B=$BROWSER"',
                   {"WSL_DISTRO_NAME": "Ubuntu", "BROWSER": "firefox"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("B=firefox", r.stdout)

    def test_without_persist_rc_files_are_untouched(self):
        sb = self.sandbox()
        sb.stub("wslview", "exit 0\n")
        self.preflight(sb)
        self.assertFalse((sb.home / ".bashrc").exists())

    def test_unwritable_rc_file_warns_and_continues(self):
        sb = self.sandbox()
        sb.stub("wslview", "exit 0\n")
        (sb.home / ".bashrc").mkdir()
        r = sb.run(f'set -euo pipefail; . "{_PLATFORM}"; hermes_wsl_preflight /home/u/x persist; echo after',
                   {"WSL_DISTRO_NAME": "Ubuntu"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARNING: could not add the wslview BROWSER default", r.stdout)
        self.assertNotIn("added the wslview BROWSER default", r.stdout)
        self.assertIn("after", r.stdout)
        self.assertEqual(r.stderr, "")

    def test_missing_wslu_leaves_browser_unset(self):
        r = self.preflight(self.sandbox())
        self.assertIn("BROWSER=\n", r.stdout)
        self.assertIn("wslu", r.stdout)


class WatchdogGateTest(_SandboxCase):
    """hermes_wants_watchdog: the wsl profile schedules the watchdog only alongside a gateway."""

    def wants(self, sb: _Sandbox, env: dict) -> bool:
        r = sb.run(f'. "{_PLATFORM}"; hermes_wants_watchdog && echo yes || echo no', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip() == "yes"

    def test_wsl_without_gateway_skips_watchdog(self):
        self.assertFalse(self.wants(self.sandbox(), {"WSL_DISTRO_NAME": "Ubuntu"}))

    def test_wsl_gateway_opt_in_alone_skips_watchdog(self):
        self.assertFalse(self.wants(self.sandbox(), {"WSL_DISTRO_NAME": "Ubuntu", "HERMES_INSTALL_GATEWAY": "true"}))

    def test_wsl_with_installed_gateway_wants_watchdog(self):
        sb = self.sandbox()
        unit = sb.home / ".config" / "systemd" / "user" / "hermes-gateway.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Unit]\n")
        self.assertTrue(self.wants(sb, {"WSL_DISTRO_NAME": "Ubuntu"}))

    def test_other_profiles_always_want_watchdog(self):
        self.assertTrue(self.wants(self.sandbox(), {}))
        self.assertTrue(self.wants(self.sandbox(kernel="Darwin"), {}))


class HostProfileStepTest(_SandboxCase):
    def run_step(self, sb: _Sandbox, extra_env=None, wsl: bool = True, hermes: bool = True) -> subprocess.CompletedProcess:
        if hermes:
            sb.stub_hermes()
        env = {"REPO_DIR": str(_ROOT), "HERMES_HOME": str(sb.home / ".hermes")}
        if wsl:
            env["WSL_DISTRO_NAME"] = "Ubuntu"
        return sb.run(f'bash "{_HOST_PROFILE}"', dict(env, **(extra_env or {})))

    def assertOk(self, r: subprocess.CompletedProcess) -> None:
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("host step done", r.stdout)

    def installed_watchdog(self, sb: _Sandbox) -> Path:
        return sb.home / ".hermes" / "scripts" / "watchdog.json"

    def test_wsl_selects_wsl_profile_and_skips_gateway_by_default(self):
        sb = self.sandbox()
        r = self.run_step(sb)
        self.assertOk(r)
        self.assertIn("host profile: wsl", r.stdout)
        self.assertIn("HERMES_INSTALL_GATEWAY=true", r.stdout)
        calls = sb.calls_text()
        self.assertNotIn("gateway install", calls)
        self.assertIn("plugins install obra/superpowers", calls)
        self.assertEqual(calls.count("hermes cron create"), 3)
        self.assertNotIn("--deliver telegram", calls)

    def test_rerun_creates_no_cron_jobs_or_plugins(self):
        sb = self.sandbox()
        self.assertOk(self.run_step(sb))
        sb.calls.write_text("")
        r = self.run_step(sb)
        self.assertOk(r)
        calls = sb.calls_text()
        self.assertIn("hermes cron list --all", calls)
        self.assertNotIn("cron create", calls)
        self.assertNotIn("plugins install", calls)
        self.assertIn("plugin superpowers already present", r.stdout)
        self.assertIn("3 already present", r.stdout)

    def test_gateway_opt_in_installs_and_warns_without_systemd(self):
        sb = self.sandbox()
        r = self.run_step(sb, {"HERMES_INSTALL_GATEWAY": "true"})
        self.assertOk(r)
        self.assertIn("hermes gateway install --if-missing", sb.calls_text())
        self.assertIn("gateway will stop when its WSL session closes", r.stdout)

    def assertLoudGatewayFailure(self, r: subprocess.CompletedProcess, cause: str) -> None:
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertNotIn("host step done", r.stdout)
        self.assertIn("ERROR: HERMES_INSTALL_GATEWAY=true was set, but the gateway service was NOT installed", r.stderr)
        self.assertIn(cause, r.stderr)
        self.assertIn(f"HERMES_INSTALL_GATEWAY=true bash {_ROOT}/devbox/setup-hermes.sh", r.stderr)
        self.assertGreaterEqual(r.stderr.count("====="), 2)

    def test_gateway_opt_in_install_failure_is_loud(self):
        sb = self.sandbox()
        r = self.run_step(sb, {"HERMES_INSTALL_GATEWAY": "true", "HERMES_STUB_GATEWAY_FAIL": "1"})
        self.assertLoudGatewayFailure(r, "'hermes gateway install --if-missing' failed")
        self.assertIn("systemd is not running", r.stderr)
        self.assertEqual(sb.calls_text().count("hermes cron create"), 3, "the rest of the profile still installs")

    def test_gateway_opt_in_without_hermes_is_loud(self):
        sb = self.sandbox()
        r = self.run_step(sb, {"HERMES_INSTALL_GATEWAY": "true"}, hermes=False)
        self.assertLoudGatewayFailure(r, "the hermes CLI is not on PATH")

    def test_sora_gateway_failure_stays_a_warning(self):
        sb = self.sandbox()
        r = self.run_step(sb, {"HERMES_STUB_GATEWAY_FAIL": "1", "HERMES_INSTALL_GATEWAY": "true"}, wsl=False)
        self.assertOk(r)
        self.assertIn("WARNING: hermes gateway install failed", r.stdout)
        self.assertNotIn("ERROR", r.stderr)

    def gateway_unit(self, sb: _Sandbox) -> None:
        unit = sb.home / ".config" / "systemd" / "user" / "hermes-gateway.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Unit]\n")

    def test_gateway_unit_not_enabled_logs_enable_command(self):
        sb = self.sandbox()
        self.gateway_unit(sb)
        sb.stub("systemctl", f'echo "systemctl $*" >> {sb.calls}\ncase "$*" in *is-enabled*) exit 1 ;; esac\nexit 0\n')
        r = self.run_step(sb)
        self.assertOk(r)
        self.assertIn("gateway service already installed", r.stdout)
        self.assertIn("hermes-gateway.service is installed but not enabled", r.stdout)
        self.assertIn("systemctl --user enable --now hermes-gateway.service", r.stdout)
        self.assertNotIn("systemctl --user enable ", sb.calls_text(), "the step must not enable an existing unit")

    def test_enabled_gateway_unit_gives_no_hint(self):
        sb = self.sandbox()
        self.gateway_unit(sb)
        sb.stub("systemctl", "exit 0\n")
        r = self.run_step(sb)
        self.assertOk(r)
        self.assertNotIn("not enabled", r.stdout)

    def test_gateway_unit_without_systemd_gives_no_enable_hint(self):
        sb = self.sandbox()
        self.gateway_unit(sb)
        r = self.run_step(sb)
        self.assertOk(r)
        self.assertNotIn("not enabled", r.stdout)

    def test_watchdog_points_drift_check_at_this_checkout(self):
        sb = self.sandbox()
        self.assertOk(self.run_step(sb))
        wd = json.loads(self.installed_watchdog(sb).read_text())
        self.assertEqual(wd["repo"], str(_ROOT))
        self.assertIs(wd["telegram"], False)
        self.assertNotIn("channel", wd)

    def test_watchdog_repo_path_with_special_characters(self):
        sb = self.sandbox()
        odd = sb.tmp / 'a&b|c\\d"e'
        odd.symlink_to(_ROOT)
        sb.stub_hermes()
        r = sb.run(f'bash "{_HOST_PROFILE}"', {"WSL_DISTRO_NAME": "Ubuntu", "REPO_DIR": str(odd),
                                               "HERMES_HOME": str(sb.home / ".hermes")})
        self.assertOk(r)
        self.assertEqual(json.loads(self.installed_watchdog(sb).read_text())["repo"], str(odd))

    def test_wsl_warns_about_telegram_watchdog(self):
        for cfg in ({"expect": [], "channel": "telegram"}, {"expect": [], "channel": "ssh:devbox:telegram"},
                    {"expect": []}):
            with self.subTest(cfg=cfg):
                sb = self.sandbox()
                self.installed_watchdog(sb).parent.mkdir(parents=True)
                self.installed_watchdog(sb).write_text(json.dumps(cfg))
                r = self.run_step(sb)
                self.assertOk(r)
                self.assertIn("alerts via Telegram", r.stdout)
                self.assertEqual(json.loads(self.installed_watchdog(sb).read_text()), cfg, "never rewritten")

    def test_wsl_quiet_for_local_watchdog(self):
        for cfg in ({"expect": [], "telegram": False}, {"expect": [], "channel": None, "telegram": False}):
            with self.subTest(cfg=cfg):
                sb = self.sandbox()
                self.installed_watchdog(sb).parent.mkdir(parents=True)
                self.installed_watchdog(sb).write_text(json.dumps(cfg))
                r = self.run_step(sb)
                self.assertOk(r)
                self.assertNotIn("Telegram", r.stdout)

    def test_sora_telegram_watchdog_is_not_flagged(self):
        sb = self.sandbox()
        self.installed_watchdog(sb).parent.mkdir(parents=True)
        self.installed_watchdog(sb).write_text('{"expect": [], "channel": "telegram"}')
        r = self.run_step(sb, wsl=False)
        self.assertOk(r)
        self.assertNotIn("alerts via Telegram", r.stdout)

    def test_plain_linux_still_selects_sora(self):
        sb = self.sandbox()
        r = self.run_step(sb, wsl=False)
        self.assertOk(r)
        self.assertIn("host profile: sora", r.stdout)
        self.assertEqual(self.installed_watchdog(sb).read_bytes(), (_ROOT / "hosts" / "sora" / "watchdog.json").read_bytes())
        self.assertIn("hermes gateway install --if-missing", sb.calls_text())


class MacHostProfileStepTest(_SandboxCase):
    """The macOS path through host-profile.sh: launchd agents, --mac cron filter and the Telegram gateway guard."""

    def run_mac(self, sb: _Sandbox, env_file: str | None = None) -> subprocess.CompletedProcess:
        sb.stub_hermes()
        hermes_home = sb.home / ".hermes"
        if env_file is not None:
            hermes_home.mkdir(parents=True, exist_ok=True)
            (hermes_home / ".env").write_text(env_file)
        return sb.run(f'bash "{_HOST_PROFILE}"', {"REPO_DIR": str(_ROOT), "HERMES_HOME": str(hermes_home),
                                                  "WSL_DISTRO_NAME": "Ubuntu"})

    def test_mac_profile_installs_as_before(self):
        sb = self.sandbox(kernel="Darwin", osrelease=WSL2_OSRELEASE)
        r = self.run_mac(sb)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("host profile: mac", r.stdout)
        self.assertIn("host step done", r.stdout)
        mac = _ROOT / "hosts" / "mac"
        wd = sb.home / ".hermes" / "scripts" / "watchdog.json"
        self.assertEqual(wd.read_bytes(), (mac / "watchdog.json").read_bytes())
        for script in (mac / "scripts").iterdir():
            self.assertTrue((sb.home / ".hermes" / "scripts" / script.name).is_file(), script.name)
        agents = sb.home / "Library" / "LaunchAgents"
        for plist in (mac / "launchd").glob("*.plist"):
            text = (agents / plist.name).read_text()
            self.assertNotIn("__HOME__", text)
            if "__HOME__" in plist.read_text():
                self.assertIn(str(sb.home), text)
        calls = sb.calls_text()
        self.assertIn("launchctl bootstrap gui/", calls)
        jobs = json.loads((mac / "cron-jobs.json").read_text())["jobs"]
        local = [j for j in jobs if "telegram" not in str(j.get("deliver", ""))]
        self.assertEqual(calls.count("hermes cron create"), len(local))
        self.assertNotIn("--deliver telegram", calls)
        self.assertIn("hermes gateway install --if-missing", calls)
        self.assertNotIn("alerts via Telegram", r.stdout)

    def test_mac_with_telegram_token_skips_gateway(self):
        sb = self.sandbox(kernel="Darwin")
        r = self.run_mac(sb, env_file="OTHER=1\nTELEGRAM_BOT_TOKEN=placeholder\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Mac has TELEGRAM_BOT_TOKEN set; not installing the gateway", r.stdout)
        self.assertNotIn("gateway install", sb.calls_text())
        self.assertIn("host step done", r.stdout)

    def test_mac_with_empty_telegram_token_installs_gateway(self):
        sb = self.sandbox(kernel="Darwin")
        r = self.run_mac(sb, env_file="TELEGRAM_BOT_TOKEN=\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hermes gateway install --if-missing", sb.calls_text())


class WslProfileTest(unittest.TestCase):
    def test_profile_is_laptop_scoped(self):
        self.assertTrue(_WSL.is_dir())
        for server_only in ("systemd", "launchd", "scripts", "bin"):
            self.assertFalse((_WSL / server_only).exists(), server_only)

    def test_jobs_are_local_and_use_shared_scripts(self):
        data = json.loads((_WSL / "cron-jobs.json").read_text())
        expect = set(json.loads((_WSL / "watchdog.json").read_text())["expect"])
        self.assertEqual({j["name"] for j in data["jobs"]}, expect)
        for j in data["jobs"]:
            self.assertEqual(j["deliver"], "local", j["name"])
            self.assertTrue((_ROOT / "scripts" / j["script"]).is_file(), j["script"])
            self.assertNotIn("relay", j["script"], "the WSL laptop has no sora to relay through")

    def test_overrides_do_not_configure_telegram(self):
        import yaml

        over = yaml.safe_load((_WSL / "config-overrides.yaml").read_text())
        self.assertNotIn("platforms", over)


_NVM_LIB = """\
# nvm stand-in: installed versions, default alias and the active node live in files under NVM_DIR.
_stub_node() {
  mkdir -p "$HOME/.local/bin"
  printf '#!/bin/sh\\necho %s\\n' "$1" > "$HOME/.local/bin/node"
  chmod +x "$HOME/.local/bin/node"
}
nvm() {
  echo "nvm $*" >> "$NVM_STUB_CALLS"
  case "$1" in
    version) if [ -s "$NVM_DIR/default" ]; then cat "$NVM_DIR/default"; else echo N/A; fi ;;
    ls) cat "$NVM_DIR/installed" 2>/dev/null; true ;;
    install) echo v22.11.0 >> "$NVM_DIR/installed"; _stub_node 22 ;;
    alias) if [ "$3" = "lts/*" ]; then echo v22.11.0; else echo "$3"; fi > "$NVM_DIR/default" ;;
    use) v="$(cat "$NVM_DIR/default")"; v="${v#v}"; _stub_node "${v%%.*}" ;;
  esac
}
"""


class BootstrapTest(_SandboxCase):
    """bootstrap-wsl.sh against stub installers: apt state lives in a file, installers drop stub binaries."""

    def make(self) -> _Sandbox:
        sb = self.sandbox(osrelease=WSL2_OSRELEASE)
        installed = sb.tmp / "dpkg-installed"
        installed.write_text("git\ncurl\nca-certificates\npython3\npython3-venv\njq\n")
        sb.stub("dpkg-query", f'for a in "$@"; do pkg="$a"; done\ngrep -qx "$pkg" {installed} && printf "install ok installed"\nexit 0\n')
        sb.stub("apt-get", f'echo "apt-get $*" >> {sb.calls}\n')
        # Installing wslu drops a wslview stub, as the real package does.
        sb.stub("sudo", textwrap.dedent(f"""\
            echo "sudo $*" >> {sb.calls}
            [ "$1" = -n ] && exit 1
            while [ $# -gt 0 ]; do case "$1" in install) shift; break ;; esac; shift; done
            for p in "$@"; do case "$p" in -*) ;; *) echo "$p" >> {installed} ;; esac; done
            case " $* " in *" wslu "*) printf '#!/bin/sh\\nexit 0\\n' > {sb.bin}/wslview; chmod +x {sb.bin}/wslview ;; esac
            exit 0
            """))
        bindir = sb.home / ".local" / "bin"
        lib = sb.tmp / "lib"
        _write_exe(lib / "uv", "exit 0\n")
        _write_exe(lib / "claude", 'case "$*" in *--json*) echo "[]" ;; esac\n')
        sb.stub_hermes(lib)
        (lib / "nvm.sh").write_text(_NVM_LIB)
        self.inst = sb.tmp / "installers"
        drop = lambda name: f'mkdir -p {bindir}\ncp {lib}/{name} {bindir}/{name}\n'
        _write_exe(self.inst / "uv.sh", drop("uv"))
        _write_exe(self.inst / "nvm.sh", f'mkdir -p {sb.home}/.nvm\ncp {lib}/nvm.sh {sb.home}/.nvm/nvm.sh\n')
        _write_exe(self.inst / "hermes.sh", f'echo "hermes-installer $*" >> {sb.calls}\n' + drop("hermes"))
        _write_exe(self.inst / "claude.sh", drop("claude"))
        sb.stub("curl", textwrap.dedent(f"""\
            for a in "$@"; do url="$a"; done
            echo "curl $url" >> {sb.calls}
            case "$url" in
              *astral.sh/uv*) cat {self.inst}/uv.sh ;;
              *nvm-sh/nvm*) cat {self.inst}/nvm.sh ;;
              *hermes-agent*) cat {self.inst}/hermes.sh ;;
              *claude.ai*) cat {self.inst}/claude.sh ;;
              *) exit 22 ;;
            esac
            """))
        sb.stub("npm", f'echo "npm $*" >> {sb.calls}\n')
        public = sb.tmp / "public_skills"
        (public / ".git").mkdir(parents=True)
        (public / "brainlift").mkdir()
        (public / "brainlift" / "SKILL.md").write_text("---\nname: brainlift\n---\n")
        sb.env.update({"WSL_DISTRO_NAME": "Ubuntu", "PUBLIC_SKILLS": str(public), "SMEM_REPO": str(sb.tmp / "no-smem"),
                       "HERMES_SKIP_PATCHES": "true", "NVM_STUB_CALLS": str(sb.calls),
                       "HERMES_WSL_MNT": str(sb.tmp / "mnt")})
        return sb

    def bootstrap(self, sb: _Sandbox, *args: str, extra_env=None) -> subprocess.CompletedProcess:
        return sb.run(f'bash "{_BOOTSTRAP}" {" ".join(args)}', extra_env, timeout=300)

    def existing_nvm(self, sb: _Sandbox, installed: str = "", default: str = "") -> None:
        nvm = sb.home / ".nvm"
        nvm.mkdir()
        (nvm / "nvm.sh").write_text(_NVM_LIB)
        (nvm / "installed").write_text(installed)
        if default:
            (nvm / "default").write_text(default + "\n")

    def test_dry_run_reports_plan_changes_nothing_and_exits_2(self):
        sb = self.make()
        r = self.bootstrap(sb, "--dry-run")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("will install with sudo apt-get: tmux wslu", r.stdout)
        for what in ("uv", "Node.js", "Hermes Agent", "Claude Code"):
            self.assertIn(f"(dry run) would install {what}", r.stdout)
        self.assertIn("host profile: wsl", r.stdout)
        probes = ("systemctl --user show-environment",)
        self.assertEqual([c for c in sb.calls_text().splitlines() if not c.startswith(probes)], [])
        self.assertEqual(sorted(p.name for p in sb.home.iterdir()), [])

    def test_install_then_rerun_is_idempotent(self):
        sb = self.make()
        r = self.bootstrap(sb)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        calls = sb.calls_text()
        self.assertIn("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tmux wslu", calls)
        self.assertIn("hermes-installer --non-interactive", calls)
        for url in ("astral.sh/uv", "nvm-sh/nvm", "hermes-agent.nousresearch.com", "claude.ai/install.sh"):
            self.assertIn(url, calls)
        self.assertIn("nvm install --lts", calls)
        self.assertIn("nvm alias default lts/*", calls)
        self.assertNotIn("gateway install", calls)
        self.assertEqual(calls.count("hermes cron create"), 3)
        self.assertIn("plugins install obra/superpowers", calls)
        self.assertIn("[host-profile] host profile: wsl", r.stdout)
        self.assertEqual(r.stdout.count("systemd is not running"), 1)
        self.assertTrue((sb.home / ".claude" / "skills").is_dir())
        # wslu came from apt in this same run, so the preflight after apt configured the browser.
        self.assertIn("BROWSER=wslview for login flows", r.stdout)
        self.assertIn("hermes-setup: WSL login browser", (sb.home / ".bashrc").read_text())
        self.assertTrue(r.stdout.rstrip().splitlines()[-1].startswith("[bootstrap-wsl]   4. optional"))

        sb.calls.write_text("")
        r2 = self.bootstrap(sb)
        self.assertEqual(r2.returncode, 0, r2.stdout[-3000:] + r2.stderr[-3000:])
        calls2 = sb.calls_text()
        self.assertNotIn("curl ", calls2)
        self.assertNotIn("apt-get", calls2)
        self.assertNotIn("nvm ", calls2)
        self.assertNotIn("cron create", calls2)
        self.assertNotIn("plugins install", calls2)
        self.assertNotIn("hermes pm install", calls2)
        self.assertIn("apt packages present", r2.stdout)
        self.assertEqual((sb.home / ".bashrc").read_text().count("hermes-setup: WSL login browser"), 1)

        r3 = self.bootstrap(sb, "--dry-run")
        self.assertEqual(r3.returncode, 0, r3.stdout + r3.stderr)
        self.assertNotIn("would install", r3.stdout)

    def test_watchdog_timer_waits_for_the_gateway_opt_in(self):
        sb = self.make()
        self.assertEqual(self.bootstrap(sb).returncode, 0)
        sb.stub("systemctl", f'echo "systemctl $*" >> {sb.calls}\nexit 0\n')
        sb.calls.write_text("")
        r = sb.run(f'bash "{_SETUP}"', timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        self.assertIn("watchdog timer not installed", r.stdout)
        self.assertNotIn("hermes-watchdog", sb.calls_text())
        self.assertFalse((sb.home / ".config" / "systemd" / "user" / "hermes-watchdog.timer").exists())

        sb.calls.write_text("")
        r = sb.run(f'bash "{_SETUP}"', {"HERMES_INSTALL_GATEWAY": "true"}, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        calls = sb.calls_text()
        self.assertIn("systemctl --user enable --now hermes-watchdog.timer", calls)
        self.assertIn("hermes gateway install --if-missing", calls)

    def test_failed_gateway_opt_in_leaves_no_watchdog_timer(self):
        sb = self.make()
        self.assertEqual(self.bootstrap(sb).returncode, 0)
        sb.stub("systemctl", f'echo "systemctl $*" >> {sb.calls}\nexit 0\n')
        unit = sb.home / ".config" / "systemd" / "user" / "hermes-watchdog.timer"
        for env in ({"HERMES_INSTALL_GATEWAY": "true", "HERMES_STUB_GATEWAY_FAIL": "1"}, {}):
            sb.calls.write_text("")
            r = sb.run(f'bash "{_SETUP}"', env, timeout=300)
            self.assertEqual(r.returncode, 3 if env else 0, r.stdout[-3000:] + r.stderr[-3000:])
            self.assertNotIn("hermes-watchdog", sb.calls_text())
            self.assertFalse(unit.exists())

    def assertNoWatchdogTimer(self, sb: _Sandbox, r: subprocess.CompletedProcess) -> None:
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        self.assertNotIn("enable --now hermes-watchdog.timer", sb.calls_text())
        self.assertFalse((sb.home / ".config" / "systemd" / "user" / "hermes-watchdog.timer").exists())

    def test_skipped_host_profile_leaves_no_watchdog_timer(self):
        sb = self.make()
        self.assertEqual(self.bootstrap(sb).returncode, 0)
        sb.stub("systemctl", f'echo "systemctl $*" >> {sb.calls}\nexit 0\n')
        for env in ({"HERMES_INSTALL_GATEWAY": "true", "HERMES_SKIP_HOST_PROFILE": "true"}, {}):
            sb.calls.write_text("")
            self.assertNoWatchdogTimer(sb, sb.run(f'bash "{_SETUP}"', env, timeout=300))

    def test_host_profile_abort_before_the_gateway_leaves_no_watchdog_timer(self):
        sb = self.make()
        self.assertEqual(self.bootstrap(sb).returncode, 0)
        sb.stub("systemctl", f'echo "systemctl $*" >> {sb.calls}\nexit 0\n')
        real_bash = shutil.which("bash", path=os.pathsep.join(["/usr/bin", "/bin"]))
        sb.stub("bash", f'case "$1" in */devbox/host-profile.sh) echo "host-profile: aborted" >&2; exit 1 ;; esac\n'
                        f'exec "{real_bash}" "$@"\n')
        sb.calls.write_text("")
        r = sb.run(f'bash "{_SETUP}"', {"HERMES_INSTALL_GATEWAY": "true"}, timeout=300)
        self.assertIn("host profile step failed; continuing", r.stdout)
        self.assertNotIn("gateway install", sb.calls_text())
        self.assertNoWatchdogTimer(sb, r)

        (sb.bin / "bash").unlink()
        sb.calls.write_text("")
        self.assertNoWatchdogTimer(sb, sb.run(f'bash "{_SETUP}"', timeout=300))

    def test_failed_gateway_opt_in_is_the_last_thing_reported(self):
        sb = self.make()
        r = self.bootstrap(sb, extra_env={"HERMES_INSTALL_GATEWAY": "true", "HERMES_STUB_GATEWAY_FAIL": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ERROR: HERMES_INSTALL_GATEWAY=true was set, but the gateway service was NOT installed", r.stderr)
        self.assertIn(f"HERMES_INSTALL_GATEWAY=true bash {_ROOT}/devbox/setup-hermes.sh", r.stderr)
        self.assertIn("[setup-hermes] finished WITH ERRORS", r.stdout)
        self.assertNotIn("done — setup", r.stdout)
        self.assertNotIn("done. Next steps", r.stdout)
        self.assertEqual(r.stderr.rstrip().splitlines()[-1],
                         "[bootstrap-wsl] ERROR: the gateway requested with HERMES_INSTALL_GATEWAY=true was not installed; "
                         "see the ERROR block above")

    def test_failed_installer_dies_with_rerun_guidance(self):
        sb = self.make()
        (self.inst / "uv.sh").write_text("#!/bin/sh\necho 'uv installer: network down' >&2\nexit 7\n")
        r = self.bootstrap(sb)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("[bootstrap-wsl] ERROR: installing uv failed", r.stderr)
        self.assertIn(f"re-run: bash {_ROOT}/devbox/bootstrap-wsl.sh", r.stderr)
        self.assertNotIn("Node.js", r.stdout.split("installing uv")[-1])

    def test_installer_that_leaves_no_binary_is_caught(self):
        sb = self.make()
        (self.inst / "uv.sh").write_text("#!/bin/sh\nexit 0\n")
        r = self.bootstrap(sb)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("uv install finished but it is still not usable on PATH", r.stderr)

    def test_broken_nvm_script_is_reported(self):
        sb = self.make()
        (sb.home / ".nvm").mkdir()
        (sb.home / ".nvm" / "nvm.sh").write_text("nvm() {\n  echo trunc")
        r = self.bootstrap(sb)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"[bootstrap-wsl] ERROR: loading {sb.home}/.nvm/nvm.sh failed", r.stderr)

    def test_windows_binaries_do_not_count(self):
        sb = self.make()
        win = sb.tmp / "mnt" / "c" / "Program Files" / "tools"
        wsl_internal = sb.tmp / "mnt" / "wsl" / "shared"
        for name in ("uv", "claude"):
            _write_exe(win / name, "exit 0\n")
        _write_exe(win / "node", "echo 22\n")
        _write_exe(wsl_internal / "hermes", "exit 0\n")
        path = os.pathsep.join([sb.env["PATH"], str(win), str(wsl_internal)])
        r = self.bootstrap(sb, "--dry-run", extra_env={"PATH": path})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        for name in ("uv", "node", "claude"):
            self.assertIn(f"ignoring Windows {name} at {win}/{name}", r.stdout)
        self.assertIn("(dry run) would install uv", r.stdout)
        self.assertIn("(dry run) would install Node.js", r.stdout)
        self.assertIn("Hermes Agent present", r.stdout)

    def test_node_below_floor_is_not_enough(self):
        for major, ok in (("16", False), ("18", True), ("22", True)):
            with self.subTest(major=major):
                sb = self.make()
                sb.stub("node", f"echo {major}\n")
                r = self.bootstrap(sb, "--dry-run")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual("Node.js >= 18 present" in r.stdout, ok, r.stdout)
                self.assertEqual("would install Node.js" in r.stdout, not ok, r.stdout)

    def test_nvm_default_that_meets_the_floor_is_kept(self):
        sb = self.make()
        self.existing_nvm(sb, installed="v20.1.0\n", default="v20.1.0")
        r = self.bootstrap(sb, extra_env={"HERMES_SKIP_HOST_PROFILE": "true"})
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        self.assertIn("keeping the nvm default node v20.1.0", r.stdout)
        calls = sb.calls_text()
        self.assertNotIn("nvm-sh/nvm", calls)
        self.assertNotIn("nvm install", calls)
        self.assertNotIn("nvm alias", calls)
        self.assertEqual((sb.home / ".nvm" / "default").read_text().strip(), "v20.1.0")

    def test_installed_node_meeting_the_floor_becomes_default_without_install(self):
        sb = self.make()
        self.existing_nvm(sb, installed="v16.20.2\nv20.1.0\nv18.19.0\n", default="v16.20.2")
        r = self.bootstrap(sb, extra_env={"HERMES_SKIP_HOST_PROFILE": "true"})
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        calls = sb.calls_text()
        self.assertNotIn("nvm install", calls)
        self.assertIn("nvm alias default v20.1.0", calls)
        self.assertIn("pointing the nvm default at the installed node v20.1.0 (was: v16.20.2)", r.stdout)

    def test_refuses_outside_wsl(self):
        sb = self.sandbox()
        r = sb.run(f'bash "{_BOOTSTRAP}" --dry-run')
        self.assertEqual(r.returncode, 1)
        self.assertIn("not running inside WSL", r.stderr)

    def test_refuses_root(self):
        sb = self.make()
        sb.stub("id", "echo 0\n")
        r = self.bootstrap(sb, "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not root", r.stderr)


class ScriptsTest(unittest.TestCase):
    def test_new_shell_scripts_parse(self):
        for p in (_PLATFORM, _BOOTSTRAP):
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{p}: {r.stderr}")

    def test_bootstrap_is_executable(self):
        self.assertTrue(os.access(_BOOTSTRAP, os.X_OK))


@unittest.skipUnless(shutil.which("git") and (_ROOT / ".git").exists(), "needs a git checkout")
class LineEndingsTest(unittest.TestCase):
    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True, check=True).stdout

    def test_text_files_check_out_with_lf(self):
        files = [f for f in self.git("ls-files", "-z").split("\0") if f]
        attrs = self.git("check-attr", "-z", "text", "eol", "--", *files).split("\0")
        by_file: dict[str, dict[str, str]] = {}
        for i in range(0, len(attrs) - 2, 3):
            by_file.setdefault(attrs[i], {})[attrs[i + 1]] = attrs[i + 2]
        for f in files:
            a = by_file[f]
            if a.get("text") == "unset":
                continue
            self.assertEqual(a.get("eol"), "lf", f)
        for f in files:
            if f.endswith((".sh", ".py", ".json", ".yaml", ".yml", ".md", ".service", ".timer", ".template")):
                self.assertEqual(by_file[f].get("text"), "set", f)

    def test_no_crlf_in_index(self):
        bad = [line for line in self.git("ls-files", "--eol").splitlines() if line.split()[0] in ("i/crlf", "i/mixed")]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
