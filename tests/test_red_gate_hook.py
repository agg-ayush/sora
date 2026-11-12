import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "red-gate-hook.py"
spec = importlib.util.spec_from_file_location("red_gate", SCRIPT)
red_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(red_gate)

PYTEST_RED = "pytest tests/test_x.py\n=== 1 failed, 2 passed in 0.1s ===\nFAILED tests/test_x.py::test_a - AssertionError\n"
PYTEST_GREEN = "pytest tests/test_x.py\n=== 3 passed in 0.1s ===\n"


def edit(path, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": path}}


def save(task, name, text):
    ev = task / "evidence"
    ev.mkdir(exist_ok=True)
    (ev / name).write_text(text)


def test_source_edit_denied_without_red(tmp_path):
    assert "RED gate" in red_gate.decide(edit("/repo/src/app.py"), tmp_path)


def test_source_edit_allowed_with_failing_red(tmp_path):
    save(tmp_path, "red-parser.txt", PYTEST_RED)
    assert red_gate.decide(edit("/repo/src/app.py"), tmp_path) is None


def test_green_looking_red_file_does_not_open_gate(tmp_path):
    save(tmp_path, "red-parser.txt", PYTEST_GREEN)
    assert red_gate.decide(edit("/repo/src/app.py"), tmp_path) is not None


def test_command_line_alone_does_not_open_gate(tmp_path):
    save(tmp_path, "red-parser.txt", "pytest -k failed tests/\n")
    assert red_gate.decide(edit("/repo/src/app.py"), tmp_path) is not None


def test_jest_and_vitest_failure_output_open_gate(tmp_path):
    save(tmp_path, "red-a.txt", "npx jest a\nTests:       1 failed, 4 passed, 5 total\n")
    assert red_gate.decide(edit("/repo/src/a.ts"), tmp_path) is None
    other = tmp_path / "v"
    other.mkdir()
    save(other, "red-b.txt", "npx vitest run b\n × b.test.ts > does x\n")
    assert red_gate.decide(edit("/repo/src/b.ts"), other) is None


def test_tests_docs_config_and_task_dir_always_allowed(tmp_path):
    for p in ("/repo/tests/test_a.py", "/repo/src/a.test.tsx", "/repo/e2e/flow.ts",
              "/repo/README.md", "/repo/package.json", "/repo/src/styles.css",
              str(tmp_path / "evidence" / "helper.py")):
        assert red_gate.decide(edit(p), tmp_path) is None, p


def test_non_edit_tools_ignored(tmp_path):
    assert red_gate.decide({"tool_name": "Bash", "tool_input": {"command": "x"}}, tmp_path) is None


def run_hook(task, payload, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), str(task)], input=payload, text=True,
                          capture_output=True, env=env)


def test_cli_denies_with_hook_json_and_exit_zero(tmp_path):
    r = run_hook(tmp_path, json.dumps(edit("/repo/src/app.py")))
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "RED gate" in out["permissionDecisionReason"]


def test_cli_fails_open_on_bad_input(tmp_path):
    r = run_hook(tmp_path, "not json")
    assert r.returncode == 0 and r.stdout == "" and "allowing edit" in r.stderr


def test_cli_kill_switch(tmp_path):
    import os
    r = run_hook(tmp_path, json.dumps(edit("/repo/src/app.py")), env={**os.environ, "HERMES_RED_GATE": "off"})
    assert r.returncode == 0 and r.stdout == ""


CAPTURE = Path(__file__).resolve().parents[1] / "scripts" / "capture-evidence.sh"


def capture(kind, unit, task, *cmd):
    return subprocess.run(["bash", str(CAPTURE), kind, unit, "--task-dir", str(task), "--", *cmd],
                          capture_output=True, text=True)


def test_capture_red_saves_command_then_output_and_opens_gate(tmp_path):
    r = capture("red", "u", tmp_path, "bash", "-c", "echo '1 failed'; exit 1")
    assert r.returncode == 0
    lines = (tmp_path / "evidence" / "red-u.txt").read_text().splitlines()
    assert lines[0] == "bash -c echo '1 failed'; exit 1" and lines[1] == "1 failed"
    assert red_gate.decide(edit("/repo/src/app.py"), tmp_path) is None


def test_capture_red_that_passes_exits_3(tmp_path):
    assert capture("red", "u", tmp_path, "bash", "-c", "echo '2 passed'").returncode == 3


def test_capture_green_propagates_failure(tmp_path):
    assert capture("green", "u", tmp_path, "bash", "-c", "exit 2").returncode == 2
    assert capture("green", "u", tmp_path, "bash", "-c", "echo ok").returncode == 0
