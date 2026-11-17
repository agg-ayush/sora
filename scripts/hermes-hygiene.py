#!/usr/bin/env python3
"""hermes-hygiene — weekly storage + health maintenance for the tier system.

Runs the maintenance the tier system's growth patterns need and that nothing
else reclaims:

  * ``hermes checkpoints prune``  — worktree checkpoints outlive the tmux
    sessions the orphan-reaper kills, so they accumulate unbounded.
  * ``hermes sessions optimize-storage`` — VACUUM + FTS rebuild. Session
    auto-archive soft-hides rows but never shrinks the file.
  * ``hermes doctor --fix``       — surfaces WAL/disk/dependency problems and
    auto-fixes what it can (TCC anchor, WAL checkpoint, etc.).

  * ``hermes-state.py audit`` — reports unclassified host-state entries every run and
    a change in the fingerprint's diffed sets once; the first run records a silent baseline.
    ``<state dir>/hermes-state-audit.off`` skips the step.

  * Leaked ``remotion-webpack-bundle-*`` dirs in the scratch dir are removed after 2 hours
    (not 7 days) when no process holds them open; see ``prune_remotion_bundles``.

Designed for a ``no_agent`` cron: prints ONLY when something was reclaimed or
doctor found an actionable issue; silent otherwise.

Thresholds are deliberately conservative — this deletes derived artifacts
(checkpoints, index pages), never session history.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Only VACUUM when the DB has grown past this — the rebuild is expensive.
VACUUM_ABOVE_MB = 750
STATE_DB = Path.home() / ".hermes" / "state.db"
STATE_DB_WAL = Path.home() / ".hermes" / "state.db-wal"

# Doctor warnings we explicitly do NOT care about (not actionable for our setup).
IGNORED_DOCTOR_PATTERNS: list[str] = [
    # OAuth providers we never use
    "Nous Portal auth",
    "OpenAI Codex auth",
    "MiniMax OAuth",
    "xAI OAuth",
    # Optional tools we do not use
    "docker not found",
    # WhatsApp bridge was dropped
    "WhatsApp bridge deps",
    # Tool-availability warnings for tools we do not configure
    "a2a (system dependency not met)",
    "browser (system dependency not met)",
    "browser-cdp (system dependency not met)",
    "computer_use (system dependency not met)",
    "discord (missing DISCORD_BOT_TOKEN)",
    "discord_admin (missing DISCORD_BOT_TOKEN)",
    "feishu_doc (system dependency not met)",
    "feishu_drive (system dependency not met)",
    "hermes-yuanbao (system dependency not met)",
    "homeassistant (system dependency not met)",
    "image_gen (system dependency not met)",
    "video_gen (system dependency not met)",
    "x_search (missing XAI_API_KEY)",
    # API connectivity warnings we do not act on
    "OpenRouter API (not configured)",
    "AWS Bedrock",
]


def hermes(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    exe = shutil.which("hermes") or str(Path.home() / ".local" / "bin" / "hermes")
    try:
        return subprocess.run(
            [exe, *args], capture_output=True, text=True, check=False, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001 — a broken hermes must not crash the cron
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def db_size_mb() -> float:
    try:
        return STATE_DB.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def wal_size_mb() -> float:
    try:
        return STATE_DB_WAL.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def prune_checkpoints() -> str | None:
    """Drop orphaned/stale worktree checkpoints. Returns a line if it reclaimed."""
    r = hermes("checkpoints", "prune", "-f", timeout=300)
    if r.returncode != 0:
        return f"checkpoints prune failed: {(r.stderr or r.stdout).strip()[:120]}"
    m = re.search(r"Bytes reclaimed:\s*([\d.]+)\s*(\w+)", r.stdout)
    if not m:
        return None
    amount, unit = float(m.group(1)), m.group(2)
    if unit.upper().startswith("B") or amount == 0:
        return None
    return f"checkpoints: reclaimed {amount:.1f} {unit}"


def prune_archived_messages(keep_per_session: int = 400) -> str | None:
    """Delete old compaction-archived (active = 0) rows beyond the newest *keep_per_session*
    per session, never touching active = 1 or _compressed_summary = 1 rows (zero model impact)."""
    if not STATE_DB.is_file():
        return None
    sql = f"""
    PRAGMA busy_timeout = 10000;
    DELETE FROM messages WHERE id IN (
      SELECT id FROM (
        SELECT id, _compressed_summary,
               ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY id DESC) AS rn
        FROM messages WHERE active = 0
      ) WHERE rn > {int(keep_per_session)} AND _compressed_summary = 0
    );
    SELECT changes();
    """
    r = subprocess.run(["sqlite3", str(STATE_DB), sql], capture_output=True, text=True, check=False, timeout=180)
    if r.returncode != 0:
        return f"archived-message prune failed: {(r.stderr or r.stdout).strip()[:120]}"
    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip().isdigit()]
    deleted = int(lines[-1]) if lines else 0
    return f"messages: pruned {deleted} old compacted rows (> {keep_per_session}/session)" if deleted > 0 else None


def optimize_sessions() -> str | None:
    """VACUUM + FTS rebuild, but only once the DB is actually large."""
    before = db_size_mb()
    if before < VACUUM_ABOVE_MB:
        return None
    # The command prompts interactively; feed it a confirmation.
    exe = shutil.which("hermes") or str(Path.home() / ".local" / "bin" / "hermes")
    try:
        subprocess.run(
            [exe, "sessions", "optimize-storage"], input="y\n",
            capture_output=True, text=True, check=False, timeout=1800,
        )
    except Exception as exc:  # noqa: BLE001
        return f"sessions optimize-storage failed: {exc}"
    after = db_size_mb()
    if after >= before - 1:
        return None
    return f"state.db: {before:.0f} MB -> {after:.0f} MB (reclaimed {before - after:.0f} MB)"


def checkpoint_wal() -> str | None:
    """Truncate the WAL if it has grown past 32 MB."""
    before = wal_size_mb()
    if before < 32:
        return None
    r = subprocess.run(
        ["sqlite3", str(STATE_DB), "PRAGMA wal_checkpoint(TRUNCATE);"],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if r.returncode != 0:
        return f"WAL checkpoint failed: {(r.stderr or r.stdout).strip()[:120]}"
    after = wal_size_mb()
    if after >= before - 1:
        return None
    return f"state.db WAL: {before:.0f} MB -> {after:.1f} MB (checkpointed)"


STALE_DAYS = 7
HOME = Path.home()
# (directory, whether only entries owned by this user may be removed)
STALE_ROOTS: list[tuple[Path, bool]] = [
    (HOME / ".hermes" / "cache" / "scratch", False),
    (HOME / ".config" / "gogcli" / "drive-downloads", False),
    (HOME / ".npm" / "_npx", False),
    (Path("/tmp"), True),
]
# /tmp entries that belong to running services, never removed
TMP_KEEP_PREFIXES = ("tmux-", "systemd-", "snap-private", ".X", ".ICE", ".font-unix", "ssh-")


def _newest_mtime(path: Path) -> float:
    """Most recent mtime anywhere under path, symlinks not followed."""
    try:
        newest = path.lstat().st_mtime
    except OSError:
        return time.time()
    if path.is_dir() and not path.is_symlink():
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            for name in dirnames + filenames:
                try:
                    newest = max(newest, os.lstat(os.path.join(dirpath, name)).st_mtime)
                except OSError:
                    pass
    return newest


def _entry_size(path: Path) -> int:
    if path.is_symlink() or not path.is_dir():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    for dirpath, _dirs, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def prune_stale_files(roots: list[tuple[Path, bool]] | None = None, days: int = STALE_DAYS,
                      now: float | None = None, dry_run: bool = False) -> str | None:
    """Remove cache/temp entries with nothing inside modified in the last *days* days."""
    cutoff = (now or time.time()) - days * 86400
    uid = os.getuid()
    freed, removed = 0, 0
    for root, own_only in (STALE_ROOTS if roots is None else roots):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if root == Path("/tmp") and entry.name.startswith(TMP_KEEP_PREFIXES):
                continue
            try:
                if own_only and entry.lstat().st_uid != uid:
                    continue
            except OSError:
                continue
            if _newest_mtime(entry) >= cutoff:
                continue
            size = _entry_size(entry)
            if dry_run:
                print(f"would remove {size / (1024 * 1024):8.1f} MB  {entry}")
                freed += size
                removed += 1
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except OSError:
                continue
            freed += size
            removed += 1
    if not removed:
        return None
    return f"stale caches/tmp: removed {removed} entries older than {days} days ({freed / (1024 * 1024):.0f} MB)"


BUNDLE_PREFIX = "remotion-webpack-bundle-"
BUNDLE_MIN_AGE_HOURS = 2
SCRATCH_DIR = HOME / ".hermes" / "cache" / "scratch"


def _held_open(path: Path) -> bool:
    """True if any process has a file open under *path* (cwd, mmap or fd), or if that cannot be told.

    lsof exits 1 when nothing matches; any other failure counts as held (fail safe: keep the dir).
    """
    try:
        r = subprocess.run(
            ["lsof", "-w", "-t", "+D", str(path)],
            capture_output=True, text=True, check=False, timeout=60, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if r.returncode == 0:
        return bool(r.stdout.strip())
    return r.returncode != 1 or bool(r.stdout.strip())


def prune_remotion_bundles(scratch: Path | None = None, hours: float = BUNDLE_MIN_AGE_HOURS,
                           now: float | None = None, dry_run: bool = False,
                           held_open=_held_open) -> str | None:
    """Remove leaked ``remotion-webpack-bundle-*`` dirs (~64 MB each) older than *hours*.

    Remotion's bundler mkdtemp()s one per render under TMPDIR and never removes it when the render
    is SIGTERMed or the caller forgets; 250 of them filled a disk in under 3 hours. The 7-day stale
    rule is far too slow for that. Narrow on purpose: only real directories (not symlinks) directly
    under the Hermes scratch dir, only that name prefix, only when nothing inside was modified for
    *hours* and no process holds a file in it open.
    """
    root = SCRATCH_DIR if scratch is None else scratch
    if not root.is_dir():
        return None
    cutoff = (now or time.time()) - hours * 3600
    freed, removed = 0, 0
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith(BUNDLE_PREFIX):
            continue
        try:
            if entry.is_symlink() or not entry.is_dir():
                continue
        except OSError:
            continue
        if _newest_mtime(entry) >= cutoff or held_open(entry):
            continue
        size = _entry_size(entry)
        if dry_run:
            print(f"would remove {size / (1024 * 1024):8.1f} MB  {entry}")
        else:
            try:
                shutil.rmtree(entry)
            except OSError:
                continue
        freed += size
        removed += 1
    if not removed:
        return None
    return f"remotion bundles: removed {removed} dirs older than {hours:g}h ({freed / (1024 * 1024):.0f} MB)"


def doctor_issues() -> str | None:
    """Report doctor's failures/warnings, filtered to only actionable items."""
    r = hermes("doctor", "--fix", timeout=300)
    bad: list[str] = []
    for ln in (r.stdout or "").splitlines():
        stripped = ln.strip()
        if not stripped.startswith(("✗", "⚠")):
            continue
        # Skip anything matching our ignore list
        if any(pat in stripped for pat in IGNORED_DOCTOR_PATTERNS):
            continue
        bad.append(stripped)
    if not bad:
        return None
    return "doctor:\n" + "\n".join(f"    {ln}" for ln in bad[:8])


STATE_SCRIPT = Path(__file__).parent / "hermes-state.py"
STATE_AUDIT_TIMEOUT = 120
STATE_BASELINE_NAME = "hermes-state-fingerprint.json"
STATE_MARKER_NAME = "hermes-state-audit.off"
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
    "platforms",
)
_STATE_LIST_CAP = 10


def _is_schema_1(value) -> bool:
    return isinstance(value, dict) and type(value.get("schema")) is int and value["schema"] == 1


def _state_dir() -> Path:
    override = os.environ.get("WATCHER_STATE_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "watcher-state"


def _get_set(fp: dict, name: str):
    value = fp
    for part in name.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _put_set(fp: dict, name: str, value) -> None:
    parts = name.split(".")
    for part in parts[:-1]:
        if not isinstance(fp.get(part), dict):
            fp[part] = {}
        fp = fp[part]
    fp[parts[-1]] = value


def _set_shape_ok(name: str, value) -> bool:
    if value is None:
        return True
    if name == "memory_provider":
        return isinstance(value, str)
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _baseline_shape_ok(data: dict) -> bool:
    for top in ("skills", "hermes_plugins"):
        if data.get(top) is not None and not isinstance(data[top], dict):
            return False
    return all(_set_shape_ok(name, _get_set(data, name)) for name in DIFFED_SETS)


def _read_baseline(path: Path):
    """(status, data): status is 'none' for a first run, 'bad' when unusable, else 'ok'."""
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return "none", None
    except OSError:
        return "bad", None
    try:
        data = json.loads(raw.decode())
    except ValueError:
        return "bad", None
    if not _is_schema_1(data) or not _baseline_shape_ok(data):
        return "bad", None
    return "ok", data


def _write_baseline(state_dir: Path, data: dict) -> bool:
    tmp = None
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=state_dir, prefix=".hermes-state-fingerprint.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, state_dir / STATE_BASELINE_NAME)
        return True
    except OSError:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False


def _capped(sign: str, items: list) -> list[str]:
    out = [f"{sign}{item}" for item in items[:_STATE_LIST_CAP]]
    if len(items) > _STATE_LIST_CAP:
        out.append(f"+{len(items) - _STATE_LIST_CAP} more")
    return out


def _as_items(value) -> set:
    return {value} if isinstance(value, str) else set(value)


def _diff_segments(baseline: dict, current: dict) -> list[str]:
    segments = []
    for name in DIFFED_SETS:
        old, new = _get_set(baseline, name), _get_set(current, name)
        if old is None or new is None:
            continue
        old_items, new_items = _as_items(old), _as_items(new)
        added, removed = sorted(new_items - old_items), sorted(old_items - new_items)
        if added or removed:
            segments.append(" ".join([name, *_capped("+", added), *_capped("-", removed)]))
    return segments


def _merge_baseline(baseline: dict | None, current: dict) -> dict:
    merged = json.loads(json.dumps(current))
    if baseline is not None:
        for name in DIFFED_SETS:
            if _get_set(current, name) is None and _get_set(baseline, name) is not None:
                _put_set(merged, name, _get_set(baseline, name))
    return merged


def _unclassified_line(fp: dict) -> str | None:
    items = fp.get("unclassified") or []
    if not items:
        return None
    names = [f"{u['root']}/{u['name']}" for u in items]
    shown = ", ".join(names[:_STATE_LIST_CAP])
    more = f", +{len(names) - _STATE_LIST_CAP} more" if len(names) > _STATE_LIST_CAP else ""
    return f"state: {len(names)} unclassified: {shown}{more}"


def _run_state_audit():
    """(fingerprint, failure line); exactly one is None."""
    try:
        proc = subprocess.run(
            [sys.executable, str(STATE_SCRIPT), "audit", "--json"],
            capture_output=True, text=True, check=False, timeout=STATE_AUDIT_TIMEOUT, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "state audit failed (exit timeout)"
    fp = None
    if proc.returncode in (0, 1):
        try:
            parsed = json.loads(proc.stdout)
        except ValueError:
            parsed = None
        fp = parsed if _is_schema_1(parsed) else None
    if fp is None:
        return None, f"state audit failed (exit {proc.returncode})"
    return fp, None


def _state_audit_lines() -> list[str]:
    state_dir = _state_dir()
    try:
        os.stat(state_dir / STATE_MARKER_NAME)
        return []
    except (FileNotFoundError, NotADirectoryError):
        pass
    fp, failure = _run_state_audit()
    if failure:
        return [failure]
    lines = []
    unclassified = _unclassified_line(fp)
    if unclassified:
        lines.append(unclassified)
    status, baseline = _read_baseline(state_dir / STATE_BASELINE_NAME)
    if status == "ok":
        segments = _diff_segments(baseline, fp)
        if segments:
            lines.append("state fingerprint changed: " + "; ".join(segments))
    written = _write_baseline(state_dir, _merge_baseline(baseline, fp))
    if status == "bad":
        lines.append("state baseline unreadable; re-baselined" if written else "state baseline unreadable; write failed")
    elif not written:
        lines.append("state baseline write failed")
    return lines


def state_audit() -> str | None:
    """Report unclassified host-state entries and fingerprint changes; never raises."""
    try:
        lines = _state_audit_lines()
    except Exception as exc:  # noqa: BLE001 — a broken audit must not crash the cron
        return f"state audit failed (error {type(exc).__name__})"
    return "\n    ".join(lines) if lines else None


def main() -> int:
    if "--dry-run" in sys.argv[1:]:
        # Only the file-removal rules; the checkpoint/DB/doctor steps have no dry-run mode.
        for fn in (prune_stale_files, prune_remotion_bundles):
            print(f"{fn.__name__}: {fn(dry_run=True)}")
        return 0
    lines = [
        ln for ln in (
            prune_checkpoints(),
            prune_archived_messages(),
            optimize_sessions(),
            checkpoint_wal(),
            prune_stale_files(),
            prune_remotion_bundles(),
            doctor_issues(),
            state_audit(),
        ) if ln
    ]
    if lines:
        print(f"[hermes-hygiene {time.strftime('%Y-%m-%d %H:%M')}]")
        for ln in lines:
            print(f"  - {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
