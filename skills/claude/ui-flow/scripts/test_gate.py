#!/usr/bin/env python3
"""Regression tests for the ui-flow gate CLI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


GATE = Path(__file__).with_name("gate.py")


class GateTests(unittest.TestCase):
    def run_gate(self, directory, *args):
        return subprocess.run([sys.executable, "-I", str(GATE), *args], cwd=directory,
                              capture_output=True, text=True)

    def test_prefs_requires_every_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = self.run_gate(directory, "prefs", "0", "1")
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("checked must equal 12", invalid.stderr)
            self.assertFalse((Path(directory) / ".ui-flow").exists())
            passing = self.run_gate(directory, "prefs", "0", "12")
            self.assertEqual(passing.returncode, 0)
            self.assertEqual(json.loads(passing.stdout)["verdict"], "PASS")
            failing = self.run_gate(directory, "prefs", "1", "12")
            self.assertEqual(failing.returncode, 1)
            self.assertEqual(json.loads(failing.stdout)["verdict"], "FAIL")

    def test_lint_findings_and_safe_cases(self):
        cases = [
            ("multiline_disabled", ".tsx", "<button\n  disabled\n>Save</button>", [("disabled-without-reason", 1)]),
            ("ignored_multiline", ".tsx", "<button // ui-flow-ignore: explained\n  disabled\n>Save</button>", []),
            ("disabled_false", ".tsx", "<button disabled={false}>Save</button>", []),
            ("disabled_true", ".tsx", "<button disabled={true}>Save</button>", [("disabled-without-reason", 1)]),
            ("aria_disabled", ".tsx", '<button aria-disabled="true">Save</button>', []),
            ("html_disabled", ".html", '<button disabled>Save</button>', [("disabled-without-reason", 1)]),
            ("native_select", ".tsx", "<select><option>A</option></select>", [("native-select", 1)]),
            ("numeric_width", ".tsx", "<div style={{ width: 320 }} />", [("fixed-px-size", 1)]),
            ("numeric_multiple", ".tsx", "<div style={{ padding: 16, minHeight: 48 }} />", [("fixed-px-size", 1)]),
            ("numeric_unitless", ".tsx", "<div style={{ lineHeight: 1.5, flex: 1, opacity: 0.5, zIndex: 10, fontWeight: 600 }} />", []),
            ("numeric_small", ".tsx", "<div style={{ width: 2, margin: 0 }} />", []),
            ("numeric_expression", ".tsx", "<div style={{ width: size, margin: 16 * factor }} />", []),
            ("numeric_other_object", ".ts", "const dimensions = { width: 320 };", []),
            ("styled", ".tsx", "const Box = styled.div`\n  width: 320px;\n`;", [("fixed-px-size", 2)]),
            ("css_tag", ".ts", "const box = css`\n  min-height: 48px;\n`;", [("fixed-px-size", 2)]),
            ("css_function", ".js", "const box = css`width: 320px;`;", [("fixed-px-size", 1)]),
            ("css_module", ".jsx", "const box = styled.div`width: 320px;`;", [("fixed-px-size", 1)]),
            ("not_css_template", ".ts", "const box = `width: 320px;`;", []),
            ("border_hairline", ".css", ".a { border: 1px solid; border-width: 2px; outline: 2px; }", []),
            ("css_media", ".css", "@media (min-width: 800px) {\n.a { width: 10rem; }\n}", []),
            ("css_container", ".css", "@container (min-width: 600px) {\n.a { height: 10rem; }\n}", []),
            ("styled_media", ".tsx", "const Box = styled.div`\n  @media (min-width: 800px) {\n    width: 10rem;\n  }\n`;", []),
            ("css_size", ".css", ".a { width: 320px; }", [("fixed-px-size", 1)]),
            ("inline_px", ".tsx", '<div style={{ width: "320px" }} />', [("fixed-px-size", 1)]),
            ("tailwind", ".tsx", '<div className="w-[320px]" />', [("fixed-px-size", 1)]),
            ("ignored_px", ".css", ".a { width: 320px; } /* ui-flow-ignore: design */", []),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for name, ext, source, expected in cases:
                with self.subTest(name=name):
                    path = Path(directory) / (name + ext)
                    path.write_text(source)
                    result = self.run_gate(directory, "lint", str(path))
                    self.assertEqual(result.returncode, 1 if expected else 0, result.stderr)
                    findings = json.loads(result.stdout)["findings"]
                    self.assertEqual([(f["rule"], f["line"]) for f in findings], expected)


if __name__ == "__main__":
    unittest.main()
