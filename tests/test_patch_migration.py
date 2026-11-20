"""One-time migration from the removed provider patch to the neutral replacements."""

import hashlib
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "devbox" / "setup-hermes.sh"
LEGACY_REL = "patches/seatbelt-claude-teams.patch"

BASE_FILES = {
    "agent/anthropic_credentials.py": '''\
    return not text or base_url_hostname(text) == "api.anthropic.com"


def anthropic_route_is_oauth(base_url: Any, credential: Any, *, provider: Optional[str] = None) -> bool:
    """Claude Code OAuth identity for one Anthropic Messages route (#114967).

    materialized once for the shape test (``CommandTokenSource`` caches, so this never double-mints)
    and a mint failure classifies as non-OAuth — the wire client surfaces the real error.
    """
    if not (is_native_anthropic_host(base_url) or (provider or "").strip().lower() == "anthropic"):
        return False
    if callable(credential) and not isinstance(credential, str):
        try:
            credential = credential()
        except Exception:
            return False
    return isinstance(credential, str) and _is_oauth_token(credential)


class CredentialPersistError(RuntimeError):
''',
    "agent/anthropic_endpoints.py": '''\
    """Any non-anthropic.com endpoint (own x-api-key keys; skip OAuth detection). No base_url =
    direct Anthropic API."""
    normalized = _normalized_lower(base_url)
    return bool(normalized) and "anthropic.com" not in normalized


def _is_kimi_coding_endpoint(base_url: str | None) -> bool:
''',
    "agent/anthropic_message_convert.py": '''\
imports the adapter (no cycle)."""

import copy
import json
import logging
import re


def _sanitize_tool_id(tool_id: str) -> str:
    """Anthropic requires ids matching [a-zA-Z0-9_-]; replace the rest, never empty."""
    return (re.sub(r"[^a-zA-Z0-9_-]", "_", tool_id) if tool_id else "") or "tool_0"


def _tool_use_block(tool_id: Any, name: Any, tool_input: Any) -> dict[str, Any]:
''',
    "agent/auxiliary_client.py": '''\
    return hostname == "api.anthropic.com" or bool(hostname == "api.kimi.com" and "/coding" in normalized)


def _maybe_wrap_anthropic(
    client_obj: Any, model: str, api_key: str, base_url: str, api_mode: Optional[str] = None
) -> Any:
    """Rewrap a plain OpenAI client in ``AnthropicAuxiliaryClient`` when the endpoint speaks Anthropic Messages.

    Single transport-correction chokepoint at the end of every ``resolve_provider_client`` branch; returns
        "(model=%s, base_url=%s, api_mode=%s)",
        model, base_url[:60] if base_url else "", api_mode or "auto-detected",
    )
    return AnthropicAuxiliaryClient(real_client, model, api_key, base_url, is_oauth=False)


def _read_nous_auth() -> Optional[dict]:
        if merged:
            extra["default_headers"] = merged
        client = _create_openai_client(api_key=api_key, base_url=base_url, **extra)
        return _tag_backend(_maybe_wrap_anthropic(client, model, api_key, raw_base_url), provider_id), model
    return None, None


    # A profile that declares the Messages wire (commandcode-anthropic) is on it whatever the URL
    # looks like; the same declaration gates ``_reasoning_config`` in _build_call_kwargs.
    api_mode = req.api_mode or _profile_declared_messages_wire(req.provider)
    return _maybe_wrap_anthropic(client_obj, final_model_str, api_key_str, base_url_str, api_mode)


def _profile_declared_messages_wire(provider: str) -> Optional[str]:
            return _route_client(req, _named_custom_openai_wire_client(custom_base, custom_key, entry_headers), final_model)
        return _route_client(
            req, AnthropicAuxiliaryClient(real_client, final_model, custom_key, custom_base,
                                          is_oauth=anthropic_route_is_oauth(custom_base, custom_key)), final_model)
    client = _named_custom_openai_wire_client(custom_base, custom_key, entry_headers)
    # codex_responses, or auto-detect via _wrap_transport (which reads the task-level api_mode).
    if entry_api_mode == "codex_responses":
''',
    "tests/agent/test_anthropic_route_oauth_identity.py": '''\
    assert anthropic_route_is_oauth("", OAUTH) is True  # empty = native default route
    # provider=anthropic behind a proxy keeps today's behaviour (identity travels with the provider).
    assert anthropic_route_is_oauth("https://proxy.example.com", OAUTH, provider="anthropic") is True
    # Third-party hosts and Console keys never qualify; a callable that cannot mint is non-OAuth.
    assert anthropic_route_is_oauth("https://api.minimax.io/anthropic", key_cmd) is False
    assert anthropic_route_is_oauth("https://api.anthropic.com", CONSOLE) is False
    # Neither do user-scoped sk-ant-usr* API keys: they pay per token, not via a Claude
    monkeypatch.setattr(aux, "_resolve_custom_runtime", lambda: ("https://api.minimax.io/anthropic", key_cmd, "anthropic_messages"))
    third_party_aux, _model = aux._try_custom_endpoint()
    assert isinstance(third_party_aux, AnthropicAuxiliaryClient) and third_party_aux.chat.completions._is_oauth is False
''',
}


def _legacy_patch() -> str:
    deleting = subprocess.run(
        ["git", "-C", str(ROOT), "log", "--diff-filter=D", "-1", "--format=%H", "--", LEGACY_REL],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    revision = f"{deleting}^:{LEGACY_REL}" if deleting else f"HEAD:{LEGACY_REL}"
    return subprocess.run(["git", "-C", str(ROOT), "show", revision], capture_output=True, text=True, check=True).stdout


class ProviderPatchMigrationTest(unittest.TestCase):
    def test_tool_id_patch_preserves_sanitization_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "agent"
            source = agent / "agent/anthropic_message_convert.py"
            source.parent.mkdir(parents=True)
            source.write_text(BASE_FILES["agent/anthropic_message_convert.py"])
            subprocess.run(["git", "init", "-q"], cwd=agent, check=True)
            subprocess.run(
                ["git", "-C", str(agent), "apply", str(ROOT / "patches/truefoundry-tool-id.patch")],
                check=True,
            )
            text = source.read_text()
            start = text.index("def _sanitize_tool_id")
            end = text.index("\ndef _tool_use_block", start)
            namespace = {"hashlib": hashlib, "re": re}
            exec(text[start:end], namespace)
            clean = namespace["_sanitize_tool_id"]

            self.assertEqual(clean("abc__thought__c2ln"), "abc")
            self.assertEqual(clean("abc__thought__"), "abc")
            self.assertEqual(clean("__thought__c2ln"), "tool_0")
            self.assertEqual(clean(""), "tool_0")
            self.assertEqual(clean("x" * 64), "x" * 64)
            first = clean("x" * 65)
            second = clean("y" * 65)
            self.assertEqual((len(first), len(second)), (64, 64))
            self.assertNotEqual(first, second)

    def test_legacy_patch_is_reversed_before_required_neutral_patches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = root / "agent"
            home = root / "home"
            home.mkdir()
            for rel, content in BASE_FILES.items():
                path = agent / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            subprocess.run(["git", "init", "-q"], cwd=agent, check=True)
            legacy = root / "legacy.patch"
            legacy.write_text(_legacy_patch())
            subprocess.run(["git", "-C", str(agent), "apply", str(legacy)], check=True)

            functions = root / "functions.sh"
            text = SETUP.read_text()
            names = ("_removed_provider_patch", "_reverse_removed_provider_patch", "apply_hermes_patches")
            chunks = []
            for name in names:
                start = text.index(f"{name}() {{")
                end = text.index("\n}\n", start) + 2
                chunks.append(text[start:end])
            functions.write_text("\n\n".join(chunks))
            env = {
                **os.environ,
                "REPO_DIR": str(ROOT),
                "HERMES_AGENT_DIR": str(agent),
                "HERMES_HOME": str(home),
                "HERMES_SKIP_PATCHES": "false",
            }
            command = f'PROVIDER_PATCH_MIGRATION="{home}/migration.done"; log() {{ printf "%s\\n" "$*"; }}; . "{functions}"; apply_hermes_patches'
            first = subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("reversed superseded provider patch", first.stdout)
            self.assertTrue((home / "migration.done").exists())
            credentials = (agent / "agent/anthropic_credentials.py").read_text()
            endpoints = (agent / "agent/anthropic_endpoints.py").read_text()
            auxiliary = (agent / "agent/auxiliary_client.py").read_text()
            convert = (agent / "agent/anthropic_message_convert.py").read_text()
            self.assertIn("_CLAUDE_TEAMS_PROVIDERS", credentials)
            self.assertIn('host == "promptlens.trilogy.com"', credentials)
            self.assertIn("is_native_anthropic_host(base_url)", credentials)
            self.assertNotIn("seatbelt", endpoints)
            self.assertIn(
                'base_url_hostname(base_url or "") not in {"api.anthropic.com", "promptlens.trilogy.com"}',
                endpoints,
            )
            self.assertIn("provider=provider", auxiliary)
            self.assertIn("__thought__", convert)
            for patch in ("anthropic-oauth-identity.patch", "truefoundry-tool-id.patch"):
                subprocess.run(
                    ["git", "-C", str(agent), "apply", "--reverse", "--check", str(ROOT / "patches" / patch)],
                    capture_output=True, check=True,
                )

            second = subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertNotIn("reversed superseded provider patch", second.stdout)


if __name__ == "__main__":
    unittest.main()
