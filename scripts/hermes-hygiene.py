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

  * Leaked ``remotion-webpack-bundle-*`` dirs in the scratch dir are removed after 2 hours
    (not 7 days) when no process holds them open; see ``prune_remotion_bundles``.

Designed for a ``no_agent`` cron: prints ONLY when something was reclaimed or
doctor found an actionable issue; silent otherwise.

Thresholds are deliberately conservative — this deletes derived artifacts
(checkpoints, index pages), never session history.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
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
            [exe, *args], capture_output=True, text=True, timeout=timeout,
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
    r = subprocess.run(["sqlite3", str(STATE_DB), sql], capture_output=True, text=True, timeout=180)
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
            capture_output=True, text=True, timeout=1800,
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
        capture_output=True, text=True, timeout=120,
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
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
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
        ) if ln
    ]
    if lines:
        print(f"[hermes-hygiene {time.strftime('%Y-%m-%d %H:%M')}]")
        for ln in lines:
            print(f"  - {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
