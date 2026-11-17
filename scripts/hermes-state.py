#!/usr/bin/env python3
"""Audit, compare, export and restore Hermes host state against config/state-manifest.yaml.

Exit codes: 0 ok, 1 problems found or refused, 2 manifest, dependency or internal error.
Run with the Hermes venv interpreter, which carries PyYAML.
"""

import argparse
import datetime
import errno
import fcntl
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tarfile
import time
import urllib.parse
from pathlib import Path

CLASSES = ("repo-managed", "personal-state", "secret", "history", "host-local", "platform-specific")
ROOTS = ("hermes", "claude", "smem")
PLATFORMS = ("mac", "linux", "wsl", "sora", "gateway")
_RULE_KEYS = {"root", "match", "class", "platform", "carry", "note"}

try:
    import yaml
except ImportError:
    yaml = None


class ManifestError(Exception):
    pass


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def root_paths() -> dict:
    return {"hermes": hermes_home(), "claude": Path.home() / ".claude", "smem": Path.home() / ".smem"}


def default_manifest_paths():
    here = Path(__file__).resolve().parent
    return [here / "state-manifest.yaml", here.parent / "config" / "state-manifest.yaml"]


def _fail(path, msg):
    raise ManifestError(f"{path}: {msg}")


def _check_rule(path, i, rule):
    if not isinstance(rule, dict):
        _fail(path, f"rules[{i}] is not a mapping")
    extra = set(rule) - _RULE_KEYS
    if extra:
        _fail(path, f"rules[{i}] has unknown keys {sorted(extra)}")
    if rule.get("root") not in ROOTS:
        _fail(path, f"rules[{i}] root must be one of {ROOTS}")
    if not isinstance(rule.get("match"), str) or not rule["match"]:
        _fail(path, f"rules[{i}] needs a non-empty match")
    if rule.get("class") not in CLASSES:
        _fail(path, f"rules[{i}] class must be one of {CLASSES}")
    if rule["class"] == "platform-specific":
        if rule.get("platform") not in PLATFORMS:
            _fail(path, f"rules[{i}] platform must be one of {PLATFORMS}")
    elif "platform" in rule or "carry" in rule:
        _fail(path, f"rules[{i}] platform and carry are only for platform-specific rules")
    if "carry" in rule and not isinstance(rule["carry"], bool):
        _fail(path, f"rules[{i}] carry must be a boolean")


def _check_str_list(path, data, key):
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        _fail(path, f"{key} must be a list of non-empty strings")
    return value


def _check_tags(path, tag):
    tags = tag if isinstance(tag, list) else [tag]
    if not tags or not all(t in PLATFORMS for t in tags):
        _fail(path, f"fingerprint_platform tags must be from {PLATFORMS}")


def load_manifest(path) -> dict:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except OSError as e:
        raise ManifestError(f"{path}: cannot read ({type(e).__name__})") from None
    except yaml.YAMLError:
        raise ManifestError(f"{path}: invalid YAML") from None
    if not isinstance(data, dict):
        _fail(path, "top level must be a mapping")
    if type(data.get("version")) is not int or data["version"] != 1:
        _fail(path, "version must be 1")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        _fail(path, "rules must be a non-empty list")
    for i, rule in enumerate(rules):
        _check_rule(path, i, rule)
    skips = data.get("restore_skip", [])
    if not isinstance(skips, list):
        _fail(path, "restore_skip must be a list")
    for i, skip in enumerate(skips):
        if not (isinstance(skip, dict) and set(skip) == {"root", "match"} and skip["root"] in ROOTS
                and isinstance(skip["match"], str) and skip["match"]):
            _fail(path, f"restore_skip[{i}] needs exactly a root from {ROOTS} and a match")
    fp = data.get("fingerprint_platform", {})
    if not isinstance(fp, dict) or not all(isinstance(v, dict) for v in fp.values()):
        _fail(path, "fingerprint_platform must map set names to item mappings")
    for items in fp.values():
        for tag in items.values():
            _check_tags(path, tag)
    return {
        "version": 1,
        "rules": rules,
        "never_carry": _check_str_list(path, data, "never_carry"),
        "secret_globs": _check_str_list(path, data, "secret_globs"),
        "restore_skip": skips,
        "fingerprint_platform": fp,
    }


def classify(manifest, root, name):
    """First matching rule for a top-level name, or None."""
    for rule in manifest["rules"]:
        if rule["root"] == root and fnmatch.fnmatchcase(name, rule["match"]):
            return rule
    return None


class StateReadError(Exception):
    """A state directory exists but cannot be listed."""


def _read_error(path, e) -> str:
    return f"cannot read directory {path} ({errno.errorcode.get(e.errno, e.errno)})"


def top_level_names(path: Path):
    try:
        with os.scandir(path) as it:
            return sorted(e.name for e in it)
    except (FileNotFoundError, NotADirectoryError):
        return []
    except OSError as e:
        raise StateReadError(_read_error(path, e)) from None


def find_unclassified(manifest, warnings=None):
    found = []
    for root, path in root_paths().items():
        try:
            names = top_level_names(path)
        except StateReadError as e:
            if warnings is None:
                raise
            warnings.append(str(e))
            continue
        for name in names:
            if classify(manifest, root, name) is None:
                found.append({"root": root, "name": name})
    return found


_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def parse_env(text: str) -> dict:
    """Map each key in .env text to whether its value is non-empty; values are never kept."""
    keys = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] == "#":
            continue
        if re.match(r"export\s", line):
            line = line[6:].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _ENV_KEY.match(key):
            continue
        if value.lstrip()[:1] in ("'", '"'):
            value = value.lstrip()
            end = value.find(value[0], 1)
            value = value[1:] if end < 0 else value[1:end]
        else:
            value = re.split(r"\s#", value, maxsplit=1)[0].strip()
        keys[key] = len(value) > 0
    return keys


def host_profile() -> str:
    if os.environ.get("HERMES_HOST_PROFILE"):
        return os.environ["HERMES_HOST_PROFILE"]
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("linux") and _is_wsl():
        return "wsl"
    return "sora"


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    for name in (
        os.environ.get("HERMES_PROC_OSRELEASE") or "/proc/sys/kernel/osrelease",
        os.environ.get("HERMES_PROC_VERSION") or "/proc/version",
    ):
        try:
            text = Path(name).read_text(errors="replace")
        except OSError:
            continue
        if "microsoft" in text.lower() or "WSL" in text:
            return True
    return False


def _gateway_installed() -> bool:
    home = Path.home()
    return any(
        os.path.lexists(p)
        for p in (
            home / "Library/LaunchAgents/ai.hermes.gateway.plist",
            home / ".config/systemd/user/hermes-gateway.service",
            Path("/etc/systemd/system/hermes-gateway.service"),
        )
    )


def _telegram_enabled(config) -> bool:
    try:
        env = parse_env((hermes_home() / ".env").read_text(errors="replace"))
    except OSError:
        env = {}
    if env.get("TELEGRAM_BOT_TOKEN"):
        return True
    try:
        return config["platforms"]["telegram"]["enabled"] is True
    except (KeyError, TypeError):
        return False


def detect_platforms(config) -> list:
    profile = host_profile()
    found = {"mac": {"mac"}, "wsl": {"linux", "wsl"}, "sora": {"linux", "sora", "gateway"}}.get(profile, set())
    if profile != "sora" and _gateway_installed() and _telegram_enabled(config):
        found = found | {"gateway"}
    return sorted(found)


def _read_structured(path: Path, loader, warnings):
    """Parsed top-level mapping, or None (with a warning) when missing, unreadable or not a mapping."""
    try:
        data = loader(path.read_text())
        if isinstance(data, dict):
            return data
        warnings.append(f"{path.name}: invalid")
    except FileNotFoundError:
        warnings.append(f"{path.name}: not found")
    except OSError as e:
        warnings.append(f"{path.name}: unreadable ({type(e).__name__})")
    except (ValueError, yaml.YAMLError):
        warnings.append(f"{path.name}: invalid")
    return None


def _keys(value):
    return sorted(str(k) for k in value) if isinstance(value, dict) else []


def _names(value):
    return sorted(str(v) for v in value) if isinstance(value, list) else []


def _dig(data, *path):
    for part in path:
        data = data.get(part) if isinstance(data, dict) else None
    return data


def _enabled_plugins(*docs):
    merged = {}
    for doc in docs:
        plugins = _dig(doc, "enabledPlugins")
        if isinstance(plugins, dict):
            merged.update(plugins)
    return sorted(str(k) for k, v in merged.items() if v is True)


def find_skills(skills_dir: Path, warnings):
    """Skill directory names, or None (with a warning) when any part of the tree cannot be listed."""
    names, seen = [], set()
    try:
        st = os.stat(skills_dir)
    except (FileNotFoundError, NotADirectoryError):
        return names
    except OSError as e:
        warnings.append(f"skills: unreadable ({type(e).__name__})")
        return None
    seen.add((st.st_dev, st.st_ino))
    failed = []
    for dirpath, dirnames, filenames in os.walk(skills_dir, followlinks=True, onerror=failed.append):
        keep = []
        for d in sorted(dirnames):
            try:
                st = os.stat(os.path.join(dirpath, d))
            except OSError:
                continue
            if (st.st_dev, st.st_ino) not in seen:
                seen.add((st.st_dev, st.st_ino))
                keep.append(d)
        dirnames[:] = keep
        rel = os.path.relpath(dirpath, skills_dir)
        if "SKILL.md" in filenames and rel != ".":
            names.append(rel)
    if failed:
        warnings.append(f"skills: unreadable ({os.path.relpath(failed[0].filename or str(skills_dir), skills_dir)})")
        return None
    return sorted(names)


def _installed_plugins(plugins_dir: Path, warnings):
    try:
        with os.scandir(plugins_dir) as it:
            return sorted(
                e.name
                for e in it
                if (e.is_symlink() or e.is_dir(follow_symlinks=False)) and not fnmatch.fnmatchcase(e.name, "*.bak-*")
            )
    except (FileNotFoundError, NotADirectoryError):
        return []
    except OSError as e:
        warnings.append(f"plugins: unreadable ({type(e).__name__})")
        return None


def _version(binary: str, warnings):
    exe = shutil.which(binary)
    if exe is None:
        warnings.append(f"{binary}: not found")
        return None
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        warnings.append(f"{binary}: version failed ({type(e).__name__})")
        return None
    first = proc.stdout.strip().splitlines()
    if proc.returncode != 0 or not first:
        warnings.append(f"{binary}: version failed (exit {proc.returncode})")
        return None
    return first[0].strip()


def build_fingerprint(manifest) -> dict:
    warnings = []
    home, hh = Path.home(), hermes_home()
    config = _read_structured(hh / "config.yaml", yaml.safe_load, warnings)
    jobs = _read_structured(hh / "cron" / "jobs.json", json.loads, warnings)
    if jobs is not None and not isinstance(jobs.get("jobs"), list):
        warnings.append("jobs.json: invalid")
        jobs = None
    claude_cfg = _read_structured(home / ".claude" / "settings.json", json.loads, warnings)
    claude_local = _read_structured(home / ".claude" / "settings.local.json", json.loads, [])
    seatbelt = _read_structured(hh / "claude-seatbelt-config" / "settings.json", json.loads, warnings)
    claude_json = _read_structured(home / ".claude.json", json.loads, warnings)
    provider = _dig(config, "memory", "provider")

    def from_config(fn, *path):
        return fn(_dig(config, *path)) if config is not None else None

    skills = find_skills(hh / "skills", warnings)
    return {
        "schema": 1,
        "host": socket.gethostname(),
        "home": str(home),
        "platforms": detect_platforms(config),
        "unclassified": find_unclassified(manifest, warnings),
        "skills": {"count": None if skills is None else len(skills), "names": skills},
        "hermes_plugins": {
            "enabled": from_config(_names, "plugins", "enabled"),
            "disabled": from_config(_names, "plugins", "disabled"),
            "installed": _installed_plugins(hh / "plugins", warnings),
        },
        "claude_plugins": _enabled_plugins(claude_cfg, claude_local) if claude_cfg is not None else None,
        "claude_plugins_seatbelt": _enabled_plugins(seatbelt) if seatbelt is not None else None,
        "claude_mcp_servers": _keys(_dig(claude_json, "mcpServers")) if claude_json is not None else None,
        "mcp_servers": from_config(_keys, "mcp_servers"),
        "model_aliases": from_config(_keys, "model", "aliases"),
        "cron_jobs": (
            sorted(str(j["name"]) for j in _dig(jobs, "jobs") or [] if isinstance(j, dict) and "name" in j)
            if jobs is not None
            else None
        ),
        "memory_provider": provider if isinstance(provider, str) else None,
        "versions": {"hermes": _version("hermes", warnings), "claude": _version("claude", warnings)},
        "warnings": warnings,
    }


def _resolve_manifest(arg):
    if arg:
        return Path(arg)
    for candidate in default_manifest_paths():
        if candidate.is_file():
            return candidate
    raise ManifestError("no state-manifest.yaml next to the script or under config/")


def _fmt(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, list):
        return ", ".join(value) if value else "-"
    return str(value)


def print_fingerprint(fp: dict) -> None:
    skills, plugins, versions = fp["skills"], fp["hermes_plugins"], fp["versions"]
    rows = [
        ("host", fp["host"]),
        ("platforms", fp["platforms"]),
        (f"skills ({_fmt(skills['count'])})", skills["names"]),
        ("hermes plugins enabled", plugins["enabled"]),
        ("hermes plugins disabled", plugins["disabled"]),
        ("hermes plugins installed", plugins["installed"]),
        ("claude plugins", fp["claude_plugins"]),
        ("claude plugins (seatbelt)", fp["claude_plugins_seatbelt"]),
        ("claude mcp servers", fp["claude_mcp_servers"]),
        ("mcp servers", fp["mcp_servers"]),
        ("model aliases", fp["model_aliases"]),
        ("cron jobs", fp["cron_jobs"]),
        ("memory provider", fp["memory_provider"]),
        ("hermes version", versions["hermes"]),
        ("claude version", versions["claude"]),
    ]
    print("fingerprint:")
    for label, value in rows:
        print(f"  {label}: {_fmt(value)}")
    for warning in fp["warnings"]:
        print(f"  warning: {warning}")


def cmd_audit(args) -> int:
    manifest = load_manifest(_resolve_manifest(args.manifest))
    fingerprint = build_fingerprint(manifest)
    unclassified = fingerprint["unclassified"]
    if args.json:
        print(json.dumps(fingerprint, indent=2, sort_keys=True))
    else:
        if unclassified:
            print(f"{len(unclassified)} unclassified:")
            for item in unclassified:
                print(f"  {item['root']}/{item['name']}")
        else:
            print("audit clean")
        print_fingerprint(fingerprint)
    return 1 if unclassified else 0


DIFFED_SETS = (
    "skills.names",
    "hermes_plugins.enabled",
    "hermes_plugins.disabled",
    "hermes_plugins.installed",
    "claude_plugins",
    "claude_plugins_seatbelt",
    "claude_mcp_servers",
    "mcp_servers",
    "model_aliases",
    "cron_jobs",
    "memory_provider",
)
_INFORMATIONAL = ("versions", "skills.count", "home", "host", "warnings", "platforms", "unclassified")


class CompareInputError(Exception):
    pass


def _load_fingerprint(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except OSError as e:
        raise CompareInputError(f"{path}: cannot read ({type(e).__name__})") from None
    except ValueError:
        raise CompareInputError(f"{path}: not valid JSON") from None
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
        raise CompareInputError(f"{path}: not a schema 1 fingerprint")
    for name in DIFFED_SETS:
        value = _get_set(data, name)
        scalar = name == "memory_provider"
        if value is not None and not (isinstance(value, str) if scalar else _is_str_list(value)):
            raise CompareInputError(f"{path}: {name} has the wrong shape")
    return data


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _get_set(fp, name):
    value = fp
    for part in name.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _as_items(value):
    return {value} if isinstance(value, str) else set(value)


def _platform_expected(tags, lacking_platforms):
    tags = tags if isinstance(tags, list) else [tags]
    return not set(tags) & set(lacking_platforms)


def compare_fingerprints(a, b, manifest):
    """Per set: (only_a, only_b, expected, unknown); expected holds (side, item) pairs."""
    tags = manifest["fingerprint_platform"]
    plat = {"A": a.get("platforms") or [], "B": b.get("platforms") or []}
    result = {}
    for name in DIFFED_SETS:
        va, vb = _get_set(a, name), _get_set(b, name)
        if va is None or vb is None:
            result[name] = ([], [], [], True)
            continue
        ia, ib = _as_items(va), _as_items(vb)
        only = {"A": sorted(ia - ib), "B": sorted(ib - ia)}
        expected = []
        for side, lacking in (("A", "B"), ("B", "A")):
            keep = []
            for item in only[side]:
                tag = tags.get(name, {}).get(item)
                if tag is not None and _platform_expected(tag, plat[lacking]):
                    expected.append((side, item))
                else:
                    keep.append(item)
            only[side] = keep
        result[name] = (only["A"], only["B"], expected, False)
    return result


def _info_value(fp, name):
    value = _get_set(fp, name)
    if name == "unclassified" and isinstance(value, list):
        value = [f"{u.get('root')}/{u.get('name')}" for u in value if isinstance(u, dict)]
    if isinstance(value, dict):
        value = ", ".join(f"{k}={v}" for k, v in sorted(value.items()))
    return _fmt(value) if not isinstance(value, (int, str)) else str(value)


def cmd_compare(args) -> int:
    manifest = load_manifest(_resolve_manifest(args.manifest))
    try:
        a, b = _load_fingerprint(args.a), _load_fingerprint(args.b)
    except CompareInputError as e:
        print(f"hermes-state: bad input: {e}", file=sys.stderr)
        return 2
    result = compare_fingerprints(a, b, manifest)
    differs = False
    print("differences:")
    for name, (only_a, only_b, _, unknown) in result.items():
        if unknown:
            print(f"  {name}: unknown on at least one side")
        elif only_a or only_b:
            differs = True
            print(f"  {name}: only A: {_fmt(only_a)}; only B: {_fmt(only_b)}")
    if not differs:
        print("  none")
    print("platform-expected:")
    shown = False
    for name, (_, _, expected, _) in result.items():
        for side, item in expected:
            shown = True
            print(f"  {name}: only {side}: {item}")
    if not shown:
        print("  none")
    print("informational:")
    for name in _INFORMATIONAL:
        print(f"  {name}: A={_info_value(a, name)}; B={_info_value(b, name)}")
    return 1 if differs else 0


GPG_MISSING = "hermes-state: gpg not found; install gnupg (sudo apt-get install gnupg)"
UNENCRYPTED_WARNING = (
    "WARNING: unencrypted bundle may contain secrets and history; do not upload it; "
    "delete it and its .sha256 after transfer"
)
GZIP_MAGIC = b"\x1f\x8b"
SQLITE_MAGIC = b"SQLite format 3\x00"
STAGING_MAX_AGE = 86400
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class ExportRefused(Exception):
    """A refusal that exits 1."""


def _before_open(path):
    """Test seam: runs after the walk and before each file open."""


def _after_fstat(path):
    """Test seam: runs after the size is frozen and before the first read."""


def _matches(name, globs):
    return any(fnmatch.fnmatchcase(name, g) for g in globs)


def _is_sqlite(path: Path) -> bool:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        return os.read(fd, 16) == SQLITE_MAGIC
    finally:
        os.close(fd)


def _carries(rule, include_secrets):
    cls = rule["class"]
    if cls in ("personal-state", "history"):
        return True
    if cls == "platform-specific":
        return bool(rule.get("carry"))
    return cls == "secret" and include_secrets


def _entry(root, rel, rule, st, link_target=None):
    entry = {"root": root, "path": f"{root}/{rel}", "class": rule["class"]}
    if "platform" in rule:
        entry["platform"] = rule["platform"]
    entry["mode"] = stat.S_IMODE(st.st_mode)
    return entry


def _walk_entries(manifest, root, base: Path, include_secrets):
    """Entries (without seq) for one root, parents before children."""
    never, secret = manifest["never_carry"], manifest["secret_globs"]
    out = []

    def visit(path: Path, rel: str, rule, top: bool):
        name = path.name
        if _matches(name, never) or (not top and not include_secrets and _matches(name, secret)):
            return
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return
        mode = st.st_mode
        if stat.S_ISLNK(mode):
            entry = _entry(root, rel, rule, st)
            entry.update(type="link", link_target=os.readlink(path))
            out.append(entry)
        elif stat.S_ISDIR(mode):
            entry = _entry(root, rel, rule, st)
            entry["type"] = "dir"
            out.append(entry)
            try:
                names = sorted(os.listdir(path))
            except (FileNotFoundError, NotADirectoryError):
                return
            except OSError as e:
                raise ExportRefused(f"cannot read directory {path} ({errno.errorcode.get(e.errno, e.errno)})") from None
            for child in names:
                visit(path / child, f"{rel}/{child}", rule, False)
        elif stat.S_ISREG(mode):
            if name.endswith(_SIDECAR_SUFFIXES) and _is_sqlite(path.with_name(name.rsplit("-", 1)[0])):
                return
            entry = _entry(root, rel, rule, st)
            entry["type"] = "sqlite" if st.st_size and _is_sqlite(path) else "file"
            out.append(entry)

    for name in top_level_names(base):
        rule = classify(manifest, root, name)
        if rule is not None and _carries(rule, include_secrets):
            visit(base / name, name, rule, True)
    return out


def collect_entries(manifest, include_secrets):
    entries = []
    for root, base in root_paths().items():
        entries.extend(_walk_entries(manifest, root, base, include_secrets))
    for seq, entry in enumerate(entries):
        entry["seq"] = seq
    return entries


class FrozenReader:
    """Reads at most the size seen at open; pads a shrunk file with NULs and hashes the bytes really read."""

    def __init__(self, fd, size):
        self.fd, self.size = fd, size
        self.sent = 0
        self.valid = 0
        self.eof = False
        self.sha = hashlib.sha256()

    def read(self, n=-1):
        remaining = self.size - self.sent
        if n is None or n < 0 or n > remaining:
            n = remaining
        parts = []
        need = n
        while need and not self.eof:
            chunk = os.read(self.fd, need)
            if not chunk:
                self.eof = True
                break
            self.sha.update(chunk)
            self.valid += len(chunk)
            parts.append(chunk)
            need -= len(chunk)
        if need:
            parts.append(b"\0" * need)
        self.sent += n
        return b"".join(parts)


def _open_frozen(path):
    """(reader, close) for a live file, or None when it vanished."""
    _before_open(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    size = os.fstat(fd).st_size
    _after_fstat(path)
    return FrozenReader(fd, size)


def snapshot_sqlite(src: Path, dst: Path):
    source = sqlite3.connect(f"file:{urllib.parse.quote(str(src))}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _add_bytes(tar, name, data: bytes, mode=0o600):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(data))


def _add_file(tar, entry, live_path: Path):
    """Data member then digest member; a vanished file gets a digest alone."""
    digest = {"seq": entry["seq"], "path": entry["path"]}
    reader = _open_frozen(live_path)
    if reader is None:
        digest.update(size=0, valid=0, sha256=None, missing=True)
    else:
        try:
            info = tarfile.TarInfo(entry["path"])
            info.size = reader.size
            info.mode = entry["mode"]
            info.mtime = int(time.time())
            tar.addfile(info, reader)
        finally:
            os.close(reader.fd)
        digest.update(size=reader.size, valid=reader.valid, sha256=reader.sha.hexdigest())
    _add_bytes(tar, f"digests/{entry['seq']}.json", json.dumps(digest).encode())


def sweep_staging(staging_root: Path):
    try:
        names = os.listdir(staging_root)
    except OSError:
        return
    cutoff = time.time() - STAGING_MAX_AGE
    for name in names:
        path = staging_root / name
        try:
            if os.lstat(path).st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def _gateway_alive() -> bool:
    try:
        raw = (hermes_home() / "gateway.pid").read_text().strip()
    except OSError:
        return False
    try:
        data = json.loads(raw)
        pid = data["pid"] if isinstance(data, dict) else data
    except (ValueError, KeyError):
        return False
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _lsof_holders(paths):
    """Pids holding any path open, or None when lsof is unavailable or fails."""
    exe = shutil.which("lsof")
    if exe is None or not paths:
        return None
    try:
        proc = subprocess.run([exe, "-w", "-t", "--", *map(str, paths)], capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {int(t) for t in proc.stdout.split() if t.isdigit()} - {os.getpid()}


def _live_writers(entries):
    sqlite_paths = [root_paths()[e["root"]] / e["path"].split("/", 1)[1] for e in entries if e["type"] == "sqlite"]
    pids = _lsof_holders(sqlite_paths) or set()
    return len(pids) + (1 if _gateway_alive() else 0)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _check_out_path(out: Path):
    resolved = os.path.join(os.path.realpath(out.parent), out.name)
    for base in root_paths().values():
        if base.exists() and _under(resolved, os.path.realpath(base)):
            raise ExportRefused(f"refusing --out under {base}: {out}")


def _lock_out(out: Path):
    lock = f"{out}.lock"
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise ExportRefused(f"refusing link at {lock}") from None
        if e.errno == errno.ENOENT:
            raise ExportRefused(f"--out parent does not exist: {out.parent}") from None
        raise ExportRefused(_cannot_lock(lock, e)) from None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        os.close(fd)
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            raise ExportRefused(f"export to {out} already running") from None
        raise ExportRefused(_cannot_lock(lock, e)) from None
    return fd


def _cannot_lock(lock, e):
    name = errno.errorcode.get(e.errno, str(e.errno))
    return f"cannot lock {lock} ({name}); choose an --out on a local filesystem"


def _gpg_env():
    env = dict(os.environ)
    if not env.get("GPG_TTY"):
        for fd in (0, 1, 2):
            try:
                env["GPG_TTY"] = os.ttyname(fd)
                break
            except OSError:
                continue
    return env


def _source_platforms():
    try:
        config = yaml.safe_load((hermes_home() / "config.yaml").read_text())
    except (OSError, yaml.YAMLError):
        config = None
    return detect_platforms(config if isinstance(config, dict) else None)


def _bundle_meta(manifest, entries, include_secrets):
    return {
        "schema": 1,
        "created": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "source_home": str(Path.home()),
        "source_platforms": _source_platforms(),
        "include_secrets": include_secrets,
        "roots_present": [r for r, p in root_paths().items() if p.is_dir()],
        "source_fingerprint": build_fingerprint(manifest),
        "entries": entries,
    }


def _stream_bundle(tar, meta, staged):
    _add_bytes(tar, "bundle.json", json.dumps(meta, sort_keys=True).encode())
    for entry in meta["entries"]:
        if entry["type"] in ("file", "sqlite"):
            live = staged.get(entry["seq"]) or root_paths()[entry["root"]] / entry["path"].split("/", 1)[1]
            _add_file(tar, entry, live)


def _write_sha256(src: Path, out: Path):
    """Checksum of src written for out; call before renaming src to out so no bundle ever lacks one."""
    digest = hashlib.sha256()
    with open(src, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    Path(f"{out}.sha256").write_text(f"{digest.hexdigest()}  {out.name}\n")


def _open_partial(partial: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        return os.open(partial, flags, 0o600)
    except OSError as e:
        name = errno.errorcode.get(e.errno, str(e.errno))
        raise ExportRefused(f"cannot create {partial} ({name}); remove it and retry") from None


def _write_plain(fd: int, meta, staged):
    try:
        f = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        raise
    try:
        os.fchmod(f.fileno(), 0o600)
        with tarfile.open(fileobj=f, mode="w|gz") as tar:
            _stream_bundle(tar, meta, staged)
    finally:
        f.close()


def cmd_export(args) -> int:
    gpg = None
    if args.unencrypted:
        print(UNENCRYPTED_WARNING)
    else:
        gpg = shutil.which("gpg")
        if gpg is None:
            print(GPG_MISSING, file=sys.stderr)
            return 2
    manifest = load_manifest(_resolve_manifest(args.manifest))
    unclassified = find_unclassified(manifest)
    out = Path(args.out)
    try:
        if unclassified:
            names = ", ".join(f"{u['root']}/{u['name']}" for u in unclassified)
            raise ExportRefused(f"refusing export: {len(unclassified)} unclassified entries: {names}")
        _check_out_path(out)
        lock_fd = _lock_out(out)
    except ExportRefused as e:
        print(f"hermes-state: {e}", file=sys.stderr)
        return 1
    try:
        return _export_locked(args, gpg, manifest, out)
    except ExportRefused as e:
        print(f"hermes-state: {e}", file=sys.stderr)
        return 1
    finally:
        os.close(lock_fd)


def _export_locked(args, gpg, manifest, out: Path) -> int:
    if os.path.lexists(out):
        raise ExportRefused(f"refusing to overwrite existing {out}")
    partial = Path(f"{out}.partial")
    if os.path.lexists(partial):
        os.unlink(partial)
        print(f"note: removed stale {partial}")
    staging_root = hermes_home() / "state-staging"
    sweep_staging(staging_root)
    entries = collect_entries(manifest, args.include_secrets)
    writers = _live_writers(entries)
    if writers:
        print(f"note: {writers} live writers; history is copied as of each file's open")
    staging = None
    staged = {}
    proc = None
    ours = not args.unencrypted
    try:
        if any(e["type"] == "sqlite" for e in entries):
            staging_root.mkdir(mode=0o700, exist_ok=True)
            staging = staging_root / f"{os.getpid()}-{int(time.time())}"
            staging.mkdir(mode=0o700)
            for entry in entries:
                if entry["type"] == "sqlite":
                    live = root_paths()[entry["root"]] / entry["path"].split("/", 1)[1]
                    staged[entry["seq"]] = staging / f"{entry['seq']}.db"
                    snapshot_sqlite(live, staged[entry["seq"]])
        meta = _bundle_meta(manifest, entries, args.include_secrets)
        if args.unencrypted:
            fd = _open_partial(partial)
            ours = True
            _write_plain(fd, meta, staged)
        else:
            cmd = [gpg, "--symmetric", "--cipher-algo", "AES256", "--output", str(partial)]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, close_fds=True, env=_gpg_env())
            try:
                with tarfile.open(fileobj=proc.stdin, mode="w|") as tar:
                    _stream_bundle(tar, meta, staged)
                proc.stdin.close()
            except BrokenPipeError:
                pass
            rc = proc.wait()
            if rc != 0:
                print(f"hermes-state: gpg failed (exit {rc})", file=sys.stderr)
                _discard(partial)
                return 2
        try:
            _write_sha256(partial, out)
            os.rename(partial, out)
        except BaseException:
            _discard_after_error(Path(f"{out}.sha256"))
            raise
        print(f"exported {len(entries)} entries to {out}")
        return 0
    except BaseException:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        if ours:
            _discard_after_error(partial)
        raise
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _discard(partial: Path):
    try:
        os.unlink(partial)
    except FileNotFoundError:
        pass


def _discard_after_error(path: Path):
    """Discard path while an error propagates; a cleanup failure is reported, not raised."""
    try:
        _discard(path)
    except OSError as e:
        print(f"hermes-state: cleanup of {path} failed ({e})", file=sys.stderr)


_TEXT_SUFFIXES = (".yaml", ".yml", ".json", ".toml", ".ini", ".conf", ".sh", ".env")
_BACKUP_GLOBS = ("*.bak", "*.bak-*", "*.bak.*", "*.orig-*", "*.pre-migration-backup-*")
_POINT_IN_TIME = ("backups", ".curator_backups", "state-snapshots")
_SETUP_WIRED_PLUGINS = {"claude-orchestrate", "hermes-session-reset-policy", "synapse-mem"}
_ENTRY_TYPES = ("file", "dir", "link", "sqlite")
_KIND_NAMES = {
    stat.S_IFSOCK: "socket",
    stat.S_IFIFO: "fifo",
    stat.S_IFCHR: "character device",
    stat.S_IFBLK: "block device",
}


class RestoreRefused(Exception):
    """A refusal that exits 1."""


class ApplyError(Exception):
    """An apply failure that stops the run with exit 2."""


class EntryFailed(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _after_plan():
    """Test seam: runs between the plan pass and the apply pass."""


def match_segments(rule: str, path: str) -> bool:
    """Segment matcher: `**` spans zero or more whole segments, other segments are fnmatch within one."""

    def go(r, p):
        if not r:
            return not p
        if r[0] == "**":
            return any(go(r[1:], p[i:]) for i in range(len(p) + 1))
        return bool(p) and fnmatch.fnmatchcase(p[0], r[0]) and go(r[1:], p[1:])

    return go(rule.split("/"), path.split("/"))


def find_restore_skip(manifest, root, path):
    for rule in manifest["restore_skip"]:
        if rule["root"] == root and match_segments(rule["match"], path):
            return rule
    return None


def rewrite_home(text: str, old: str, new: str) -> str:
    if not old or old == new:
        return text
    pattern = (
        r"(?:(?<![A-Za-z0-9._/-])|(?<=[Ff][Ii][Ll][Ee]://))" + re.escape(old) + r"(?![A-Za-z0-9._-])"
    )
    return re.sub(pattern, lambda _m: new, text)


def _rewrite_bytes(data: bytes, old: str, new: str) -> bytes:
    text = data.decode("utf-8", errors="surrogateescape")
    return rewrite_home(text, old, new).encode("utf-8", errors="surrogateescape")


def _rewrite_eligible(entry, rel: str) -> bool:
    if entry["type"] != "file" or entry["class"] not in ("personal-state", "secret", "platform-specific"):
        return False
    parts = rel.split("/")
    name = parts[-1]
    if entry["root"] == "hermes" and parts[0] in _POINT_IN_TIME:
        return False
    if _matches(name, _BACKUP_GLOBS):
        return False
    return name.endswith(_TEXT_SUFFIXES) or name.startswith(".env")


def _kind_of(mode) -> str:
    return _KIND_NAMES.get(stat.S_IFMT(mode), "unknown")


def _is_special(mode) -> bool:
    return not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode))


def _display(entry) -> str:
    rel = entry["path"].split("/", 1)[1]
    return rel if entry["root"] == "hermes" else entry["path"]


def _validate_entries(meta):
    entries = meta.get("entries")
    if not isinstance(entries, list):
        raise RestoreRefused("bundle.json has no entries list")
    for e in entries:
        path = e.get("path") if isinstance(e, dict) else None
        if not isinstance(path, str) or not path or path.startswith("/"):
            raise RestoreRefused(f"bad entry path: {path!r}")
        parts = path.split("/")
        if len(parts) < 2 or ".." in parts or "" in parts or parts[0] not in ROOTS or e.get("root") != parts[0]:
            raise RestoreRefused(f"bad entry path: {path}")
        if e.get("type") not in _ENTRY_TYPES or type(e.get("mode")) is not int or type(e.get("seq")) is not int:
            raise RestoreRefused(f"bad entry: {path}")
        if not isinstance(e.get("class"), str) or ("platform" in e and not isinstance(e["platform"], str)):
            raise RestoreRefused(f"bad entry: {path}")
        if e["type"] == "link" and not isinstance(e.get("link_target"), str):
            raise RestoreRefused(f"bad link entry: {path}")
    return entries


def _verify_checksum(bundle: Path):
    sha_file = Path(f"{bundle}.sha256")
    try:
        want = sha_file.read_text().split()[0]
    except (OSError, IndexError):
        raise RestoreRefused(f"missing or unreadable checksum {sha_file}") from None
    digest = hashlib.sha256()
    try:
        with open(bundle, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                digest.update(block)
    except OSError as e:
        raise RestoreRefused(f"cannot read {bundle} ({type(e).__name__})") from None
    if digest.hexdigest() != want:
        raise RestoreRefused(f"checksum mismatch for {bundle}")


def _verify_checksum_fd(bundle: Path, fd: int, open_error):
    sha_file = Path(f"{bundle}.sha256")
    try:
        want = sha_file.read_text().split()[0]
    except (OSError, IndexError):
        raise RestoreRefused(f"missing or unreadable checksum {sha_file}") from None
    digest = hashlib.sha256()
    try:
        if open_error is not None:
            raise open_error
        os.lseek(fd, 0, os.SEEK_SET)
        for block in iter(lambda: os.read(fd, 1 << 20), b""):
            digest.update(block)
    except OSError as e:
        raise RestoreRefused(f"cannot read {bundle} ({type(e).__name__})") from None
    if digest.hexdigest() != want:
        raise RestoreRefused(f"checksum mismatch for {bundle}")


def _read_plain_meta(fd: int):
    os.lseek(fd, 0, os.SEEK_SET)
    meta = None
    with open(fd, "rb", closefd=False) as stream:
        try:
            with tarfile.open(fileobj=stream, mode="r|gz") as tar:
                info = tar.next()
                if info is not None and info.name == "bundle.json":
                    meta = json.loads(tar.extractfile(info).read())
        except (tarfile.TarError, ValueError, OSError):
            meta = None
    if not isinstance(meta, dict):
        raise ApplyError("cannot read bundle.json from bundle")
    return meta


def _open_gpg(gpg, bundle: Path, stderr):
    return subprocess.Popen(
        [gpg, "--decrypt", str(bundle)], stdout=subprocess.PIPE, stderr=stderr, close_fds=True, env=_gpg_env()
    )


def _read_plan_meta(gpg, bundle: Path):
    proc = _open_gpg(gpg, bundle, subprocess.PIPE)
    meta = None
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            info = tar.next()
            if info is not None and info.name == "bundle.json":
                meta = json.loads(tar.extractfile(info).read())
    except (tarfile.TarError, ValueError, OSError):
        meta = None
    if not isinstance(meta, dict):
        proc.kill()
        detail = proc.stderr.read().decode(errors="replace").strip()
        proc.wait()
        raise ApplyError(f"cannot read bundle.json from gpg output{': ' + detail if detail else ''}")
    proc.stdout.close()
    proc.terminate()
    proc.wait()
    proc.stderr.close()
    return meta


def _dest_platforms():
    return set(_source_platforms())


class Plan:
    def __init__(self, entry, rel):
        self.entry = entry
        self.rel = rel
        self.skip = None
        self.unsupported = None
        self.clashes = []
        self.target = "absent"
        self.link_identical = False


def _classify_target(realroot: str, plan: Plan, link_target):
    entry, parts = plan.entry, plan.rel.split("/")
    cur = Path(realroot)
    for i, part in enumerate(parts):
        cur = cur / part
        last = i == len(parts) - 1
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            return
        mode = st.st_mode
        rel = "/".join(parts[: i + 1])
        if _is_special(mode):
            plan.unsupported = _kind_of(mode)
            return
        if not last:
            if stat.S_ISDIR(mode):
                continue
            plan.clashes.append((rel, "link" if stat.S_ISLNK(mode) else "file"))
            return
        bundle_type = entry["type"]
        if stat.S_ISLNK(mode):
            if bundle_type == "link" and os.readlink(cur) == link_target:
                plan.link_identical = True
                plan.target = "link"
            else:
                plan.clashes.append((rel, "link"))
        elif stat.S_ISDIR(mode):
            if bundle_type == "dir":
                plan.target = "dir"
            else:
                plan.clashes.append((rel, "dir"))
        else:
            if bundle_type in ("file", "sqlite"):
                plan.target = "file"
            else:
                plan.clashes.append((rel, "file"))


def _link_target_for(entry, meta, home):
    return rewrite_home(entry["link_target"], meta["source_home"], home) if entry["type"] == "link" else None


def build_plan(manifest, meta, entries, dest_platforms, home):
    roots = root_paths()
    plans = []
    for entry in entries:
        rel = entry["path"].split("/", 1)[1]
        plan = Plan(entry, rel)
        platform = entry.get("platform")
        if platform and platform not in dest_platforms:
            plan.skip = f"platform {platform}"
        elif find_restore_skip(manifest, entry["root"], rel):
            plan.skip = "host-profile managed"
        else:
            base = roots[entry["root"]]
            realroot = os.path.realpath(base)
            _classify_target(realroot, plan, _link_target_for(entry, meta, home))
        plans.append(plan)
    return plans


class Restorer:
    def __init__(self, manifest, meta, plans, dry_run, home):
        self.manifest, self.meta, self.plans = manifest, meta, plans
        self.dry_run, self.home = dry_run, home
        self.roots = {r: os.path.realpath(p) for r, p in root_paths().items()}
        self.backup_dir = None
        self.resolved = set()
        self.applied = []
        self.failed = 0
        self.overwrote_config = False
        self.restored_plugins = []
        self.pending_modes = []

    def emit(self, text):
        print(text)

    def fail_line(self, plan, reason):
        self.failed += 1
        verb = "would fail" if self.dry_run else "failed"
        self.emit(f"{verb} ({reason}) {_display(plan.entry)}")

    def dest(self, plan) -> str:
        return os.path.join(self.roots[plan.entry["root"]], plan.rel)

    def backup_target(self, root, rel) -> Path:
        if self.backup_dir is None:
            base = hermes_home() / "state-restore-backups"
            stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            path, n = base / stamp, 0
            while path.exists():
                n += 1
                path = base / f"{stamp}-{n}"
            path.mkdir(parents=True, mode=0o700)
            self.backup_dir = path
        dst = self.backup_dir / root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        return dst

    def displace(self, root, rel, src):
        """Move a destination entry (a link itself, never its target) to the backup dir."""
        dst = self.backup_target(root, rel)
        try:
            os.rename(src, dst)
            return
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise ApplyError(f"{rel}: cannot move to backup ({errno.errorcode.get(e.errno, e.errno)})") from None
        self._copy_then_remove(root, rel, src, dst)

    def _copy_then_remove(self, root, rel, src, dst):
        st = os.lstat(src)
        if stat.S_ISDIR(st.st_mode):
            for dirpath, dirnames, filenames in os.walk(src):
                for name in dirnames + filenames:
                    sub = os.path.join(dirpath, name)
                    mode = os.lstat(sub).st_mode
                    if _is_special(mode):
                        raise EntryFailed(f"unsupported type {_kind_of(mode)} at {os.path.relpath(sub, src)}")
        try:
            if stat.S_ISDIR(st.st_mode):
                shutil.copytree(src, dst, symlinks=True)
            elif stat.S_ISLNK(st.st_mode):
                os.symlink(os.readlink(src), dst)
            else:
                shutil.copy2(src, dst)
        except OSError as e:
            shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) and not os.path.islink(dst) else None
            raise ApplyError(f"{rel}: backup copy failed ({errno.errorcode.get(e.errno, e.errno)})") from None
        try:
            if stat.S_ISDIR(st.st_mode):
                shutil.rmtree(src)
            else:
                os.unlink(src)
        except OSError as e:
            name = errno.errorcode.get(e.errno, str(e.errno))
            raise ApplyError(f"{rel}: cannot remove original ({name}); complete backup kept at {dst}") from None

    def resolve_clashes(self, plan, scope="all"):
        for rel, _kind in plan.clashes:
            own = rel == plan.rel
            if (scope == "parents" and own) or (scope == "own" and not own):
                continue
            key = (plan.entry["root"], rel)
            if key in self.resolved:
                continue
            src = os.path.join(self.roots[plan.entry["root"]], rel)
            if os.path.lexists(src):
                self.displace(plan.entry["root"], rel, src)
            self.resolved.add(key)

    def check_outside_root(self, plan):
        root = self.roots[plan.entry["root"]]
        parent = os.path.dirname(self.dest(plan))
        if self.dry_run:
            parts = plan.rel.split("/")[:-1]
            if plan.clashes:
                first = min(len(c[0].split("/")) for c in plan.clashes)
                parts = parts[: first - 1]
            parent = os.path.join(root, *parts)
            while not os.path.lexists(parent) and parent != root:
                parent = os.path.dirname(parent)
        if not _under(os.path.realpath(parent), root):
            raise EntryFailed("outside root")

    def ensure_parents(self, plan):
        root = self.roots[plan.entry["root"]]
        os.makedirs(root, mode=0o700, exist_ok=True)
        cur = root
        for part in plan.rel.split("/")[:-1]:
            cur = os.path.join(cur, part)
            if not os.path.lexists(cur):
                os.mkdir(cur, 0o700)

    def cleanup_temp(self, path):
        if path:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def done(self, plan, line):
        self.emit(line)
        self.applied.append(_display(plan.entry))
        e = plan.entry
        parts = plan.rel.split("/")
        if e["root"] == "hermes" and len(parts) == 2 and parts[0] == "plugins" and e["type"] in ("dir", "link"):
            self.restored_plugins.append(parts[1])
        if e["root"] == "hermes" and plan.rel in (".env", "config.yaml"):
            self.restored_files.add(plan.rel)

    restored_files = None

    def consume(self, tar, plan):
        """Read and discard the members of an entry that is not applied."""
        if plan.entry["type"] not in ("file", "sqlite"):
            return
        names = (plan.entry["path"], f"digests/{plan.entry['seq']}.json")
        info = tar.next()
        if info is not None and info.name == names[0]:
            info = tar.next()
        if info is None or info.name != names[1]:
            raise UnexpectedMember("<missing>" if info is None else info.name)

    def apply(self, plan, tar):
        e = plan.entry
        if plan.skip:
            self.emit(f"skipped ({plan.skip}) {_display(e)}")
            self.consume(tar, plan)
            return
        if plan.unsupported:
            self.fail_line(plan, f"unsupported type {plan.unsupported}")
            self.consume(tar, plan)
            return
        try:
            if e["type"] == "dir":
                self.apply_dir(plan)
            elif e["type"] == "link":
                self.apply_link(plan)
            else:
                self.apply_file(plan, tar)
        except EntryFailed as ex:
            self.fail_line(plan, ex.reason)

    def prepare(self, plan, defer_own=False):
        """Displace planned clashes, then verify and create parents; defer_own leaves the entry's own target alone."""
        if not self.dry_run:
            self.resolve_clashes(plan, "parents" if defer_own else "all")
        self.check_outside_root(plan)
        if not self.dry_run:
            self.ensure_parents(plan)

    def own_clash(self, plan):
        for rel, kind in plan.clashes:
            if rel == plan.rel:
                return kind
        return None

    def current_kind(self, plan):
        """lstat of the target now: 'absent', 'file', 'dir', 'link', or raises for special files."""
        try:
            st = os.lstat(self.dest(plan))
        except FileNotFoundError:
            return "absent"
        except OSError as e:
            raise ApplyError(f"{_display(plan.entry)}: {errno.errorcode.get(e.errno, e.errno)}") from None
        if _is_special(st.st_mode):
            raise EntryFailed(f"unsupported type {_kind_of(st.st_mode)}")
        return "link" if stat.S_ISLNK(st.st_mode) else "dir" if stat.S_ISDIR(st.st_mode) else "file"

    def apply_dir(self, plan):
        e = plan.entry
        self.prepare(plan)
        clash = self.own_clash(plan)
        if self.dry_run and clash:
            self.done(plan, f"would replace {clash} {_display(e)}")
            return
        now = "absent" if self.dry_run and plan.target == "absent" else self.current_kind(plan)
        if self.dry_run and plan.clashes:
            now = "absent"
        if now == "absent":
            if self.dry_run:
                self.done(plan, f"would create dir {_display(e)}")
                return
            os.mkdir(self.dest(plan), 0o700)
            os.chmod(self.dest(plan), 0o700)
            self.pending_modes.append((self.dest(plan), e["mode"]))
            self.done(plan, f"created dir {_display(e)}")
        elif now == "dir":
            if not self.dry_run:
                self.defer_mode(self.dest(plan), e["mode"])
            self.done(plan, f"identical {_display(e)}")
        else:
            raise EntryFailed("changed during restore")

    def defer_mode(self, path, mode):
        """Make an existing dir owner-writable for its children; the recorded mode is applied after them."""
        cur = stat.S_IMODE(os.lstat(path).st_mode)
        if cur & 0o700 != 0o700:
            os.chmod(path, cur | 0o700)
        if cur != mode:
            self.pending_modes.append((path, mode))
        elif cur & 0o700 != 0o700:
            self.pending_modes.append((path, cur))

    def apply_dir_modes(self):
        for path, mode in reversed(self.pending_modes):
            try:
                os.chmod(path, mode)
            except OSError as e:
                self.failed += 1
                print(f"hermes-state: cannot set mode on {path} ({errno.errorcode.get(e.errno, e.errno)})", file=sys.stderr)
        self.pending_modes = []

    def apply_link(self, plan):
        e = plan.entry
        target = rewrite_home(e["link_target"], self.meta["source_home"], self.home)
        self.prepare(plan)
        clash = self.own_clash(plan)
        if self.dry_run and clash:
            self.done(plan, f"would replace {clash} {_display(e)}")
            return
        now = "absent" if self.dry_run and plan.clashes else self.current_kind(plan)
        if now == "link":
            if os.readlink(self.dest(plan)) == target:
                self.done(plan, f"identical {_display(e)}")
                return
            raise EntryFailed("changed during restore")
        if now != "absent":
            raise EntryFailed("changed during restore")
        if self.dry_run:
            self.done(plan, f"would create link {_display(e)}")
            return
        tmp = f"{self.dest(plan)}.restore-{os.getpid()}-{time.monotonic_ns()}"
        os.symlink(target, tmp)
        try:
            os.replace(tmp, self.dest(plan))
        except OSError:
            self.cleanup_temp(tmp)
            raise
        self.done(plan, f"created link {_display(e)}")

    def apply_file(self, plan, tar):
        e = plan.entry
        digest_name = f"digests/{e['seq']}.json"
        try:
            self.prepare(plan, defer_own=True)
        except EntryFailed:
            self.consume(tar, plan)
            raise
        info = tar.next()
        if info is None or info.name not in (e["path"], digest_name):
            raise UnexpectedMember("<missing>" if info is None else info.name)
        eligible = _rewrite_eligible(e, plan.rel) and self.meta["source_home"] != self.home
        in_memory = eligible or self.dry_run
        spool = tmp_path = None
        data_buf = bytearray()
        sha = hashlib.sha256()
        hasher = _PrefixHasher()
        size = 0
        got_data = False
        try:
            if info.name == e["path"]:
                got_data = True
                src = tar.extractfile(info)
                if not in_memory:
                    spool, tmp_path = self._open_spool(plan)
                for block in iter(lambda: src.read(1 << 20), b""):
                    if eligible:
                        data_buf += block
                    elif spool is not None:
                        _write_all(spool, block)
                    hasher.update(block)
                size = hasher.size
                info = tar.next()
            if info is None or info.name != digest_name:
                raise UnexpectedMember("<missing>" if info is None else info.name)
            digest = json.loads(tar.extractfile(info).read())
            if digest.get("missing"):
                self.emit(f"skipped (vanished during export) {_display(e)}")
                return
            valid = digest.get("valid", size)
            if not got_data or type(valid) is not int or not 0 <= valid <= size:
                raise EntryFailed("digest mismatch")
            sha = hasher.prefix(valid)
            if sha is None or sha.hexdigest() != digest.get("sha256"):
                raise EntryFailed("digest mismatch")
            if eligible:
                data = _rewrite_bytes(bytes(data_buf[:valid]), self.meta["source_home"], self.home)
                post, size = hashlib.sha256(data).hexdigest(), len(data)
                if not self.dry_run:
                    spool, tmp_path = self._open_spool(plan)
                    _write_all(spool, data)
            elif self.dry_run:
                post, size = sha.hexdigest(), valid
            else:
                os.ftruncate(spool, valid)
                post, size = sha.hexdigest(), valid
            if spool is not None:
                os.fsync(spool)
                if os.fstat(spool).st_size != size or self._sha_of_fd(spool, size).hexdigest() != post:
                    raise EntryFailed("write verification failed")
            self._place(plan, post, size, tmp_path)
        finally:
            if spool is not None:
                os.close(spool)
            if tmp_path and os.path.lexists(tmp_path):
                self.cleanup_temp(tmp_path)

    def _open_spool(self, plan):
        name = os.path.basename(self.dest(plan))
        tmp = os.path.join(os.path.dirname(self.dest(plan)), f".{name}.restore-{os.getpid()}-{time.monotonic_ns()}")
        fd = os.open(tmp, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, plan.entry["mode"])
        return fd, tmp

    @staticmethod
    def _sha_of_fd(fd, length):
        sha = hashlib.sha256()
        os.lseek(fd, 0, os.SEEK_SET)
        left = length
        while left:
            block = os.read(fd, min(1 << 20, left))
            if not block:
                break
            sha.update(block)
            left -= len(block)
        return sha

    def _compare_sha(self, plan, want_hex, want_size):
        dest = self.dest(plan)
        try:
            fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as e:
            try:
                st = os.lstat(dest)
            except FileNotFoundError:
                raise EntryFailed("changed during restore") from None
            except OSError as e2:
                raise ApplyError(f"{_display(plan.entry)}: {errno.errorcode.get(e2.errno, e2.errno)}") from None
            if _is_special(st.st_mode):
                raise EntryFailed(f"unsupported type {_kind_of(st.st_mode)}") from None
            if stat.S_ISLNK(st.st_mode) or stat.S_ISDIR(st.st_mode):
                raise EntryFailed("changed during restore") from None
            raise ApplyError(f"{_display(plan.entry)}: {errno.errorcode.get(e.errno, e.errno)}") from None
        try:
            st = os.fstat(fd)
            if stat.S_ISDIR(st.st_mode):
                raise EntryFailed("changed during restore")
            if not stat.S_ISREG(st.st_mode):
                raise EntryFailed(f"unsupported type {_kind_of(st.st_mode)}")
            if st.st_size != want_size:
                return False
            return self._sha_of_fd(fd, want_size).hexdigest() == want_hex
        finally:
            os.close(fd)

    def _place(self, plan, post, size, tmp_path):
        e = plan.entry
        clash = self.own_clash(plan)
        if self.dry_run and clash:
            self.done(plan, f"would replace {clash} {_display(e)}")
            return
        if clash:
            self.resolve_clashes(plan, "own")
        now = "absent" if self.dry_run and plan.clashes else self.current_kind(plan)
        if now in ("link", "dir"):
            raise EntryFailed("changed during restore")
        stale = e["type"] == "sqlite" and any(os.path.lexists(self.dest(plan) + sfx) for sfx in _SIDECAR_SUFFIXES)
        if now == "file" and not stale and self._compare_sha(plan, post, size):
            self.done(plan, f"identical {_display(e)}")
            return
        if self.dry_run:
            self.done(plan, f"would write {_display(e)}")
            return
        dest = self.dest(plan)
        replaced = now == "file"
        if replaced:
            self.displace(e["root"], plan.rel, dest)
        if e["type"] == "sqlite":
            for suffix in _SIDECAR_SUFFIXES:
                if os.path.lexists(dest + suffix):
                    self.displace(e["root"], plan.rel + suffix, dest + suffix)
        os.replace(tmp_path, dest)
        if replaced and e["root"] == "hermes" and plan.rel == "config.yaml":
            self.overwrote_config = True
        self.done(plan, f"wrote {_display(e)}")


class UnexpectedMember(Exception):
    pass


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


class _PrefixHasher:
    """Streaming sha256 that also yields the digest of a prefix whose tail is NUL padding."""

    def __init__(self):
        self.full = hashlib.sha256()
        self.size = 0
        self.lnz = hashlib.sha256()
        self.lnz_end = 0

    def update(self, block):
        keep = len(block.rstrip(b"\0"))
        if keep == len(block):
            self.full.update(block)
            self.lnz = self.full.copy()
        elif keep:
            self.lnz = self.full.copy()
            self.lnz.update(block[:keep])
            self.full.update(block)
        else:
            self.full.update(block)
        if keep:
            self.lnz_end = self.size + keep
        self.size += len(block)

    def prefix(self, valid):
        """sha256 of the first `valid` bytes, or None when non-NUL bytes lie beyond it."""
        if valid == self.size:
            return self.full
        if valid < self.lnz_end:
            return None
        digest = self.lnz.copy()
        left = valid - self.lnz_end
        zeros = bytes(min(left, 1 << 20))
        while left:
            n = min(left, len(zeros))
            digest.update(zeros[:n])
            left -= n
        return digest


def _lsof_check(paths):
    if not paths:
        return
    exe = shutil.which("lsof")
    if exe is None:
        raise RestoreRefused("lsof not found; install it (sudo apt-get install lsof)")
    for path in paths:
        try:
            proc = subprocess.run(
                [exe, "-w", "-t", "--", path], capture_output=True, text=True, check=False, timeout=60, stdin=subprocess.DEVNULL
            )
        except (OSError, subprocess.SubprocessError):
            raise RestoreRefused(f"cannot tell whether {path} is open (lsof failed)") from None
        if proc.stdout.strip():
            raise RestoreRefused(f"refusing restore: {path} is held open by another process")
        if proc.returncode not in (0, 1):
            raise RestoreRefused(f"cannot tell whether {path} is open (lsof failed)")


def _check_guards(restorer):
    if _gateway_alive():
        raise RestoreRefused("refusing restore: the gateway is running; stop it first")
    held = []
    for plan in restorer.plans:
        if plan.skip or plan.unsupported or plan.entry["type"] != "sqlite":
            continue
        dest = restorer.dest(plan)
        for path in (dest, dest + "-wal"):
            if os.path.lexists(path):
                held.append(path)
    _lsof_check(held)


def _plugins_txt_names(profile):
    repo = os.environ.get("REPO_DIR")
    if repo:
        base = Path(repo)
    else:
        here = Path(__file__).resolve().parent.parent
        base = here if (here / "hosts").is_dir() else Path.home() / "hermes-setup"
    path = base / "hosts" / profile / "plugins.txt"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    return {ln.split()[0] for ln in lines if ln.strip() and not ln.strip().startswith("#")}


def _plugin_note(restorer, profile):
    names = sorted(
        {
            n
            for n in restorer.restored_plugins
            if not n.startswith(".") and not fnmatch.fnmatchcase(n, "*.bak-*") and n not in _SETUP_WIRED_PLUGINS
        }
    )
    known = _plugins_txt_names(profile)
    missing = names if known is None else [n for n in names if n not in known]
    if not missing:
        return None
    where = f"hosts/{profile}/plugins.txt"
    head = f"restored plugins not in {where}" if known is not None else f"restored plugins ({where} not found)"
    return f"note: {head}: {', '.join(missing)}; run hermes plugins install for each"


def _telegram_warnings(restorer):
    warnings = []
    home = hermes_home()
    if ".env" in restorer.restored_files:
        try:
            env = parse_env((home / ".env").read_text(errors="replace"))
        except OSError:
            env = {}
        if env.get("TELEGRAM_BOT_TOKEN"):
            warnings.append(("restored .env", "TELEGRAM_BOT_TOKEN"))
    if "config.yaml" in restorer.restored_files:
        try:
            cfg = yaml.safe_load((home / "config.yaml").read_text())
        except (OSError, yaml.YAMLError):
            cfg = None
        if _dig(cfg, "platforms", "telegram", "enabled") is True:
            warnings.append(("restored config.yaml", "platforms.telegram.enabled"))
    return [
        f"WARNING: {what} enables Telegram ({key}) on a non-gateway host; only one host may poll the bot (docs/sora-host.md)"
        for what, key in warnings
    ]


def _report_stop(restorer, message):
    print(f"hermes-state: {message}", file=sys.stderr)
    if restorer.backup_dir:
        print(f"backup dir: {restorer.backup_dir}")
    print(f"applied: {', '.join(restorer.applied) if restorer.applied else '(none)'}")


def _head_is_gzip(read_head):
    """True/False when the first two bytes decide it; None when they cannot be read."""
    try:
        head = read_head()
    except OSError:
        return None
    return head == GZIP_MAGIC if len(head) == 2 else None


def _path_head(bundle: Path):
    with open(bundle, "rb") as f:
        return f.read(2)


def _fd_head(fd: int):
    os.lseek(fd, 0, os.SEEK_SET)
    return os.read(fd, 2)


def cmd_restore(args) -> int:
    bundle = Path(args.from_)
    if not args.unencrypted:
        if _head_is_gzip(lambda: _path_head(bundle)):
            print(f"hermes-state: {bundle} is an unencrypted bundle; add --unencrypted to restore it", file=sys.stderr)
            return 1
        gpg = shutil.which("gpg")
        if gpg is None:
            print(GPG_MISSING, file=sys.stderr)
            return 2
        return _restore_flow(args, bundle, gpg, -1, None)
    print(UNENCRYPTED_WARNING)
    fd, open_error = -1, None
    try:
        try:
            fd = os.open(bundle, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as e:
            open_error = e
        if fd >= 0 and _head_is_gzip(lambda: _fd_head(fd)) is False:
            print(f"hermes-state: {bundle} is not an unencrypted bundle; drop --unencrypted to restore it", file=sys.stderr)
            return 1
        return _restore_flow(args, bundle, None, fd, open_error)
    finally:
        if fd >= 0:
            os.close(fd)


def _apply_stream(args, restorer, plans, stream, mode, drain, abort):
    """Pass 2 over an open stream; returns an exit code on a stop, None when the stream applied cleanly."""
    try:
        with tarfile.open(fileobj=stream, mode=mode) as tar:
            tar.next()
            for plan in plans:
                restorer.apply(plan, tar)
            extra = tar.next()
            if extra is not None:
                raise UnexpectedMember(extra.name)
        drain()
    except UnexpectedMember as e:
        abort()
        if args.dry_run:
            print(f"would fail (unexpected member {e})")
            return 2
        _report_stop(restorer, f"unexpected member {e}")
        return 2
    except (ApplyError, EntryFailed) as e:
        abort()
        _report_stop(restorer, str(e))
        return 2
    except (tarfile.TarError, OSError) as e:
        abort()
        _report_stop(restorer, f"bundle stream failed ({type(e).__name__})")
        return 2
    except BaseException:
        abort()
        raise
    return None


def _restore_flow(args, bundle: Path, gpg, fd: int, open_error) -> int:
    plain = gpg is None
    manifest = load_manifest(_resolve_manifest(args.manifest))
    try:
        if plain:
            _verify_checksum_fd(bundle, fd, open_error)
        else:
            _verify_checksum(bundle)
        if not args.dry_run:
            sweep_staging(hermes_home() / "state-staging")
        try:
            meta = _read_plain_meta(fd) if plain else _read_plan_meta(gpg, bundle)
        except ApplyError as e:
            print(f"hermes-state: {e}", file=sys.stderr)
            return 2
        if type(meta.get("schema")) is not int or meta["schema"] != 1:
            raise RestoreRefused("unsupported bundle schema (expected 1)")
        entries = _validate_entries(meta)
        if not isinstance(meta.get("source_home"), str):
            raise RestoreRefused("bundle.json has no source_home")
        home = str(Path.home())
        dest_platforms = _dest_platforms()
        plans = build_plan(manifest, meta, entries, dest_platforms, home)
        restorer = Restorer(manifest, meta, plans, args.dry_run, home)
        restorer.restored_files = set()
        _check_guards(restorer)
    except RestoreRefused as e:
        print(f"hermes-state: {e}", file=sys.stderr)
        return 1
    _after_plan()
    try:
        if plain:
            os.lseek(fd, 0, os.SEEK_SET)
            with open(fd, "rb", closefd=False) as stream:
                stopped = _apply_stream(args, restorer, plans, stream, "r|gz", lambda: None, lambda: None)
        else:
            proc = _open_gpg(gpg, bundle, None)

            def abort():
                proc.kill()
                proc.wait()

            stopped = _apply_stream(args, restorer, plans, proc.stdout, "r|", lambda: proc.stdout.read(), abort)
        if stopped is not None:
            return stopped
        if not plain:
            rc = proc.wait()
            if rc != 0:
                if args.dry_run:
                    print(f"would fail (gpg exit {rc})")
                else:
                    _report_stop(restorer, f"gpg exited {rc}")
                return 2
        restorer.apply_dir_modes()
        if args.dry_run:
            return 2 if restorer.failed else 0
        if restorer.backup_dir:
            print(f"backup dir: {restorer.backup_dir}")
        if "gateway" not in dest_platforms:
            for line in _telegram_warnings(restorer):
                print(line)
        profile = host_profile()
        if restorer.overwrote_config and sorted(meta.get("source_platforms") or []) != sorted(dest_platforms):
            print(
                f"note: restored config.yaml came from another profile; review hosts/{profile}/config-overrides.yaml "
                "by hand (setup applies overrides only to a new config)"
            )
        note = _plugin_note(restorer, profile)
        if note:
            print(note)
        unclassified = find_unclassified(manifest)
        if unclassified:
            print(f"audit: {len(unclassified)} unclassified:")
            for item in unclassified:
                print(f"  {item['root']}/{item['name']}")
        else:
            print("audit clean")
        if restorer.failed:
            return 2
        return 3 if unclassified else 0
    finally:
        restorer.apply_dir_modes()


def build_parser():
    parser = argparse.ArgumentParser(prog="hermes-state")
    parser.add_argument("--manifest", help="manifest path (default: next to the script, then config/)")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="list unclassified entries and print the fingerprint")
    audit.add_argument("--json", action="store_true", help="machine-readable fingerprint")
    audit.set_defaults(func=cmd_audit)
    compare = sub.add_parser("compare", help="diff two audit --json fingerprints")
    compare.add_argument("a", metavar="A.json")
    compare.add_argument("b", metavar="B.json")
    compare.set_defaults(func=cmd_compare)
    export = sub.add_parser("export", help="write a bundle of host state, gpg-encrypted unless --unencrypted is given")
    export.add_argument("--out", required=True, help="bundle path to write")
    export.add_argument("--include-secrets", action="store_true", help="also carry secret entries")
    export.add_argument("--unencrypted", action="store_true", help="write a plaintext gzip bundle; no gpg involved")
    export.set_defaults(func=cmd_export)
    restore = sub.add_parser(
        "restore", help="restore host state from a bundle that is gpg-encrypted unless --unencrypted is given"
    )
    restore.add_argument("--from", dest="from_", required=True, metavar="F", help="bundle written by export")
    restore.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    restore.add_argument("--unencrypted", action="store_true", help="read a plaintext gzip bundle; no gpg involved")
    restore.set_defaults(func=cmd_restore)
    return parser


def main(argv=None) -> int:
    if yaml is None:
        print("hermes-state: PyYAML missing; run with ~/.hermes/hermes-agent/venv/bin/python", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ManifestError as e:
        print(f"hermes-state: manifest error: {e}", file=sys.stderr)
        return 2
    except StateReadError as e:
        print(f"hermes-state: {e}", file=sys.stderr)
        return 2
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:  # noqa: BLE001
        print(f"hermes-state: internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
