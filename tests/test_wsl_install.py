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
_WSL = _ROOT / "hosts" / "wsl"

WSL2_OSRELEASE = "5.15.167.4-microsoft-standard-WSL2\n"
WSL1_VERSION = "Linux version 4.4.0-19041-Microsoft (Microsoft@Microsoft.com) (gcc version 5.4.0) #1-Microsoft\n"
EC2_OSRELEASE = "6.8.0-1021-aws\n"
EC2_VERSION = "Linux version 6.8.0-1021-aws (buildd@lcy02-amd64-001) (x86_64-linux-gnu-gcc-13) #22-Ubuntu SMP\n"


def _write_exe(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class _Sandbox:
    """Scratch HOME, stub bin dir and fake /proc files for one shell run."""

    def __init__(self, tmp: Path, kernel: str = "Linux", osrelease: str = EC2_OSRELEASE, version: str = EC2_VERSION):
        self.tmp = tmp
        self.home = tmp / "home"
        self.bin = tmp / "stubs"
        self.calls = tmp / "calls.log"
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


class PreflightTest(_SandboxCase):
    def preflight(self, sb: _Sandbox, repo_dir: str = "/home/u/hermes-setup", persist: str = "", extra_env=None):
        return sb.run(f'. "{_PLATFORM}"; hermes_wsl_preflight "{repo_dir}" {persist}; echo "BROWSER=${{BROWSER:-}}"',
                      dict({"WSL_DISTRO_NAME": "Ubuntu"}, **(extra_env or {})))

    def test_windows_drive_checkout_warns(self):
        r = self.preflight(self.sandbox(), "/mnt/c/Users/u/hermes-setup")
        self.assertIn("Windows filesystem", r.stdout)
        self.assertIn("Linux home", r.stdout)

    def test_linux_home_checkout_does_not_warn(self):
        self.assertNotIn("Windows filesystem", self.preflight(self.sandbox()).stdout)

    def test_no_systemd_gives_one_actionable_hint(self):
        out = self.preflight(self.sandbox()).stdout
        self.assertEqual(out.count("systemd is not running"), 1)
        self.assertIn("systemd=true", out)
        self.assertIn("[boot]", out)
        self.assertIn("wsl --shutdown", out)

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
        self.assertIn("B=firefox", r.stdout)

    def test_without_persist_rc_files_are_untouched(self):
        sb = self.sandbox()
        sb.stub("wslview", "exit 0\n")
        self.preflight(sb)
        self.assertFalse((sb.home / ".bashrc").exists())

    def test_missing_wslu_leaves_browser_unset(self):
        r = self.preflight(self.sandbox())
        self.assertIn("BROWSER=\n", r.stdout)
        self.assertIn("wslu", r.stdout)


class HostProfileStepTest(_SandboxCase):
    def run_step(self, sb: _Sandbox, extra_env=None) -> subprocess.CompletedProcess:
        sb.stub("hermes", f'echo "hermes $*" >> {sb.calls}\nexit 0\n')
        env = {"WSL_DISTRO_NAME": "Ubuntu", "REPO_DIR": str(_ROOT), "HERMES_HOME": str(sb.home / ".hermes")}
        return sb.run(f'bash "{_HOST_PROFILE}"', dict(env, **(extra_env or {})))

    def test_wsl_selects_wsl_profile_and_skips_gateway_by_default(self):
        sb = self.sandbox()
        r = self.run_step(sb)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("host profile: wsl", r.stdout)
        self.assertIn("HERMES_INSTALL_GATEWAY=true", r.stdout)
        calls = sb.calls_text()
        self.assertNotIn("gateway install", calls)
        self.assertIn("plugins install obra/superpowers", calls)
        self.assertEqual(calls.count("hermes cron create"), 3)
        self.assertNotIn("--deliver telegram", calls)

    def test_gateway_opt_in_installs_and_warns_without_systemd(self):
        sb = self.sandbox()
        r = self.run_step(sb, {"HERMES_INSTALL_GATEWAY": "true"})
        self.assertIn("hermes gateway install --if-missing", sb.calls_text())
        self.assertIn("gateway will stop when its WSL session closes", r.stdout)

    def test_watchdog_points_drift_check_at_this_checkout(self):
        sb = self.sandbox()
        self.run_step(sb)
        wd = json.loads((sb.home / ".hermes" / "scripts" / "watchdog.json").read_text())
        self.assertEqual(wd["repo"], str(_ROOT))
        self.assertIs(wd["telegram"], False)
        self.assertNotIn("channel", wd)

    def test_plain_linux_still_selects_sora(self):
        sb = self.sandbox()
        r = sb.run(f'bash "{_HOST_PROFILE}"', {"REPO_DIR": str(_ROOT), "HERMES_HOME": str(sb.home / ".hermes")})
        self.assertIn("host profile: sora", r.stdout)


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


class BootstrapTest(_SandboxCase):
    """bootstrap-wsl.sh against stub installers: apt state lives in a file, installers drop stub binaries."""

    def make(self) -> _Sandbox:
        sb = self.sandbox(osrelease=WSL2_OSRELEASE)
        installed = sb.tmp / "dpkg-installed"
        installed.write_text("git\ncurl\nca-certificates\npython3\npython3-venv\njq\n")
        sb.stub("dpkg-query", f'for a in "$@"; do pkg="$a"; done\ngrep -qx "$pkg" {installed} && printf "install ok installed"\nexit 0\n')
        sb.stub("apt-get", f'echo "apt-get $*" >> {sb.calls}\n')
        sb.stub("sudo", textwrap.dedent(f"""\
            echo "sudo $*" >> {sb.calls}
            [ "$1" = -n ] && exit 1
            while [ $# -gt 0 ]; do case "$1" in install) shift; break ;; esac; shift; done
            for p in "$@"; do case "$p" in -*) ;; *) echo "$p" >> {installed} ;; esac; done
            exit 0
            """))
        bindir = sb.home / ".local" / "bin"
        inst = sb.tmp / "installers"
        tool = lambda name, body: f'mkdir -p {bindir}\ncat > {bindir}/{name} <<"EOF"\n#!/bin/sh\n{body}\nEOF\nchmod +x {bindir}/{name}\n'
        _write_exe(inst / "uv.sh", tool("uv", "exit 0"))
        _write_exe(inst / "nvm.sh", f'mkdir -p {sb.home}/.nvm\ncat > {sb.home}/.nvm/nvm.sh <<"OUTER"\n'
                   f'nvm() {{\n  [ "$1" = install ] || return 0\n{tool("node", "echo 22")}}}\nOUTER\n')
        _write_exe(inst / "hermes.sh", f'echo "hermes-installer $*" >> {sb.calls}\n'
                   + tool("hermes", f'echo "hermes $*" >> {sb.calls}'))
        _write_exe(inst / "claude.sh", tool("claude", 'case "$*" in *--json*) echo "[]" ;; esac'))
        sb.stub("curl", textwrap.dedent(f"""\
            for a in "$@"; do url="$a"; done
            echo "curl $url" >> {sb.calls}
            case "$url" in
              *astral.sh/uv*) cat {inst}/uv.sh ;;
              *nvm-sh/nvm*) cat {inst}/nvm.sh ;;
              *hermes-agent*) cat {inst}/hermes.sh ;;
              *claude.ai*) cat {inst}/claude.sh ;;
              *) exit 22 ;;
            esac
            """))
        sb.stub("npm", f'echo "npm $*" >> {sb.calls}\n')
        public = sb.tmp / "public_skills"
        (public / ".git").mkdir(parents=True)
        (public / "brainlift").mkdir()
        (public / "brainlift" / "SKILL.md").write_text("---\nname: brainlift\n---\n")
        sb.env.update({"WSL_DISTRO_NAME": "Ubuntu", "PUBLIC_SKILLS": str(public), "SMEM_REPO": str(sb.tmp / "no-smem"),
                       "HERMES_SKIP_PATCHES": "true"})
        return sb

    def test_dry_run_reports_plan_and_changes_nothing(self):
        sb = self.make()
        r = sb.run(f'bash "{_BOOTSTRAP}" --dry-run')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("will install with sudo apt-get: tmux", r.stdout)
        for what in ("uv", "Node.js", "Hermes Agent", "Claude Code"):
            self.assertIn(f"(dry run) would install {what}", r.stdout)
        self.assertIn("host profile: wsl", r.stdout)
        probes = ("systemctl --user show-environment",)
        self.assertEqual([c for c in sb.calls_text().splitlines() if not c.startswith(probes)], [])
        self.assertEqual(sorted(p.name for p in sb.home.iterdir()), [])

    def test_install_then_rerun_is_idempotent(self):
        sb = self.make()
        r = sb.run(f'bash "{_BOOTSTRAP}"', timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        calls = sb.calls_text()
        self.assertIn("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tmux", calls)
        self.assertIn("hermes-installer --non-interactive", calls)
        for url in ("astral.sh/uv", "nvm-sh/nvm", "hermes-agent.nousresearch.com", "claude.ai/install.sh"):
            self.assertIn(url, calls)
        self.assertNotIn("gateway install", calls)
        self.assertIn("[host-profile] host profile: wsl", r.stdout)
        self.assertEqual(r.stdout.count("systemd is not running"), 1)
        self.assertTrue((sb.home / ".claude" / "skills").is_dir())

        sb.calls.write_text("")
        r2 = sb.run(f'bash "{_BOOTSTRAP}"', timeout=300)
        self.assertEqual(r2.returncode, 0, r2.stdout[-3000:] + r2.stderr[-3000:])
        calls2 = sb.calls_text()
        self.assertNotIn("curl ", calls2)
        self.assertNotIn("apt-get", calls2)
        self.assertIn("apt packages present", r2.stdout)

    def test_refuses_outside_wsl(self):
        sb = self.sandbox()
        r = sb.run(f'bash "{_BOOTSTRAP}" --dry-run')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not running inside WSL", r.stderr)

    def test_refuses_root(self):
        sb = self.make()
        sb.stub("id", "echo 0\n")
        r = sb.run(f'bash "{_BOOTSTRAP}" --dry-run')
        self.assertNotEqual(r.returncode, 0)
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
