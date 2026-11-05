"""Regression tests for Stop-hook receipts in the launcher activity poller."""

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_module("activity_test_launcher", _ROOT / "plugin" / "__init__.py")
stop_hook = _load_module("activity_test_stop_hook", _ROOT / "scripts" / "t3-stop-gate.py")


class ActivityReceiptTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.artifacts = Path(temp.name)
        self.activity_path = self.artifacts / "activity.json"
        artifact_patch = patch.object(launcher, "_artifact_dir", return_value=self.artifacts)
        artifact_patch.start()
        self.addCleanup(artifact_patch.stop)

    def test_poll_preserves_stop_receipt_and_unknown_fields(self):
        stop_hook.record_stop_receipt(self.artifacts, {"session_id": "sample-session"})
        receipt = json.loads(self.activity_path.read_text(encoding="utf-8"))
        receipt["external_metadata"] = {"owner": "other-writer"}
        self.activity_path.write_text(json.dumps(receipt), encoding="utf-8")

        now = time.time() + 1
        self.assertEqual(launcher._record_activity("sample-task", "working", now), now)

        saved = json.loads(self.activity_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["last_stop_at"], receipt["last_stop_at"])
        self.assertEqual(saved["claude_session_id"], "sample-session")
        self.assertEqual(saved["external_metadata"], {"owner": "other-writer"})
        self.assertEqual(saved["last_change_ts"], now)
        self.assertIn("fingerprint", saved)

    def test_poll_replaces_activity_file_atomically(self):
        stop_hook.record_stop_receipt(self.artifacts, {"session_id": "sample-session"})
        with self.activity_path.open("r", encoding="utf-8") as previous:
            original = previous.read()
            launcher._record_activity("sample-task", "working", time.time() + 1)
            previous.seek(0)
            self.assertEqual(previous.read(), original)

        saved = json.loads(self.activity_path.read_text(encoding="utf-8"))
        self.assertIn("fingerprint", saved)
        self.assertIn("last_stop_at", saved)
        self.assertEqual(sorted(path.name for path in self.artifacts.iterdir()), ["activity.json"])


if __name__ == "__main__":
    unittest.main()
