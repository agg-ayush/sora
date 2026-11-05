"""Regression tests for the T3 PreToolUse deny guard."""

import json
import subprocess
import unittest
from pathlib import Path


HOOK = Path(__file__).resolve().parents[1] / "scripts" / "deny-guard.sh"


class DenyGuardTest(unittest.TestCase):
    def check_command(self, command, expected, tool_name="Bash"):
        payload = {"tool_name": tool_name, "tool_input": {"command": command}}
        result = subprocess.run(
            [str(HOOK)], input=json.dumps(payload), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(result.returncode, expected, (command, result.stderr))
        if expected == 2:
            self.assertIn("BLOCKED by deny-guard:", result.stderr)

    def test_git_push_global_options(self):
        for command in (
            "git -C /tmp/x push origin main", "git -c k=v push",
            "git --git-dir=x push", "git --work-tree=x push",
            "git --no-pager push", "git -P push", "git --bare push",
            "git\tpush", "git -C x -c k=v push", "git -C 'x y' push",
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_git_push_wrappers(self):
        for command in (
            "/usr/bin/git push", "env git push", "env A=b git push",
            "command git push", "nohup git push", "time git push",
            "xargs git push", "exec git push", "A=b git push",
            "env -i git push", "command -v git; git push",
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_git_push_shell_and_compounds(self):
        for command in (
            "bash -c 'git push'", 'sh -c "git push"',
            "zsh -c 'git push'", "bash -lc 'git push'",
            "git status; git push", "git status && git push",
            "git status || git push", "git status | git push",
            "git status\ngit push", "echo $(git push)",
            "echo `git push`", 'echo "$(git push)"',
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_gh_pr_mutations_with_global_options(self):
        for command in (
            "gh pr create", "gh pr merge", "gh pr close", "gh pr reopen",
            "gh pr edit", "gh -R owner/repo pr create",
            "gh --repo x pr merge", "gh --repo=x pr edit",
            "/usr/bin/gh -R x pr close",
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_gh_shared_infra_mutations(self):
        for command in (
            "gh release create v1", "gh release delete v1",
            "gh repo create x", "gh repo delete x", "gh -R x release delete v1",
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_rm_root_and_home(self):
        for target in ("/", "/*", "~", "~/", "$HOME", "${HOME}", "$HOME/"):
            for flags in ("-rf", "-fr", "-r -f", "--recursive --force", "-rf --no-preserve-root"):
                command = "rm {} {}".format(flags, target)
                with self.subTest(command=command):
                    self.check_command(command, 2)

    def test_rm_non_root_paths_are_allowed(self):
        for command in (
            "rm -rf /Users/ayush/.hermes/cache/scratch/foo",
            "rm -rf /tmp/some/scratch/dir", "rm -rf foo/bar",
            "rm -rf ~/somewhere", "rm -fr /var/tmp/dir",
        ):
            with self.subTest(command=command):
                self.check_command(command, 0)

    def test_git_read_and_commit_commands_are_allowed(self):
        for command in (
            "git status", "git commit -m 'message'", "git log",
            "git diff", "git -C x commit -m 'message'",
            "git -c k=v status", "echo 'git push'", 'echo "git push"',
            "grep -r 'git push' .", "echo '$(git push)'",
        ):
            with self.subTest(command=command):
                self.check_command(command, 0)

    def test_gh_read_commands_are_allowed(self):
        for command in ("gh pr view", "gh pr list", "gh pr checks", "gh -R x pr view"):
            with self.subTest(command=command):
                self.check_command(command, 0)

    def test_sudo_is_blocked(self):
        for command in ("sudo ls", "/usr/bin/sudo -n ls", "env sudo ls"):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_secret_reads_are_blocked(self):
        for filename in (".env", "credentials.json", "secrets.yaml", "id_rsa", "id_ed25519", "cert.pem", "cert.key"):
            for reader in ("cat", "less", "head", "tail", "more"):
                command = "{} {}".format(reader, filename)
                with self.subTest(command=command):
                    self.check_command(command, 2)

    def test_destructive_cloud_commands_are_blocked(self):
        for command in (
            "aws ec2 terminate-instances --instance-ids i-x",
            "gcloud compute instances delete x", "az group delete -n x",
            "aws iam remove-user-from-group --user-name x",
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_curl_wget_allowlisted_hosts(self):
        for command in (
            "curl https://github.com/x", "curl https://api.github.com/x",
            "wget https://raw.githubusercontent.com/x", "curl http://localhost:8080/x",
            "curl https://<model-gateway>/x",
            "curl https://<model-gateway>/x",
            "curl https://<llm-gateway>.truefoundry.cloud/x",
            "curl https://api.fireworks.ai/x", "curl https://api.anthropic.com/x",
            "curl http://127.0.0.1:1234/x",
        ):
            with self.subTest(command=command):
                self.check_command(command, 0)

    def test_curl_wget_non_allowlisted_hosts(self):
        for command in (
            "curl https://evil.example/x", "wget https://evil.example/x",
            "curl https://github.com.evil.example/x",
            "curl https://evil.example/?redirect=github.com",
            "curl -H 'Host: github.com' https://evil.example/x",
            "curl https://github.com/x https://evil.example/x",
            "curl https://evil.example/x; echo github.com",
        ):
            with self.subTest(command=command):
                self.check_command(command, 2)

    def test_non_bash_tool_is_allowed(self):
        self.check_command("git push", 0, tool_name="Read")

    def test_malformed_json_is_allowed(self):
        result = subprocess.run([str(HOOK)], input="{not json", text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_unbalanced_quotes_fail_closed_for_mutations(self):
        for command in ("git -C /tmp/x push 'oops", "gh -R x pr merge 'oops"):
            with self.subTest(command=command):
                self.check_command(command, 2)


if __name__ == "__main__":
    unittest.main()
