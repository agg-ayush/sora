#!/usr/bin/env python3
"""Deterministic, local-only refresher for the ti-hiring Google Doc tracker.

Reads Kanban card statuses and GitHub PR/issue states, then updates only the
existing bracketed status markers in the "Live subtasks" tab. Never touches
any other tab, never restores removed sections, never posts to GitHub.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

# Google Doc id comes from TI_HIRING_TRACKER_DOC_ID in ~/.hermes/.env (never committed); see load_secret_env().
DOC_ID = os.environ.get("TI_HIRING_TRACKER_DOC_ID", "")
TAB_ID = "t.uvst00rz6jvj"
TAB_TITLE = "Live subtasks"
ACCOUNT = "ayushaggarwal018@gmail.com"
BOARD = "ti-hiring"
REPO = "<org>/ti-hiring"
PR_IDS = (390, 395, 403)
ISSUE_IDS = (404,)
ENV_FILE = os.path.join(os.path.expanduser("~"), ".hermes", ".env")

CARD_RE = re.compile(r"\[(CARD|PR|ISSUE):([^:\]]+):([A-Za-z_]+)\]")
CHECKED_RE = re.compile(r"\[CHECKED:([^\]]+)\]")
# Matches a previously-appended change-log line so we can find each marker's
# most recently logged status, not just whether any snippet ever appeared.
APPENDED_RE = re.compile(
    r"\[APPENDED [^\]]+\] \[(CARD|PR|ISSUE):([^:\]]+):[A-Za-z_]+\] -> "
    r"\[(?:CARD|PR|ISSUE):(?:[^:\]]+):([A-Za-z_]+)\]"
)


def _safe(s: str) -> str:
    """Strip newlines/carriage returns so appended lines can never break the
    single-line change-log format (defense in depth; regex vocab already
    excludes brackets/colons/newlines in practice)."""
    return s.replace("\r", "").replace("\n", " ")


LOG_MARKER = "[APPENDED "


def split_body_and_log(text: str):
    """Split into (static body, change-log tail) at the first appended
    change-log line. Replace mode must only ever read/target markers in the
    static body: if comments later disappear and mode reverts to replace
    while an old change-log tail is still present in the tab, bracket
    markers echoed inside that ledger (e.g. "[CARD:t_x:OLD] -> [CARD:t_x:NEW]")
    must never be mistaken for live body markers or counted toward
    uniqueness."""
    idx = text.find(LOG_MARKER)
    if idx == -1:
        return text, ""
    return text[:idx], text[idx:]

FORBIDDEN_ARG_SUBSTRINGS = (
    "--replace",
    "docs clear",
    "docs delete",
)


class RefreshError(Exception):
    """Carries a fixed, redacted error class string; never raw provider text."""

    def __init__(self, error_class: str):
        super().__init__(error_class)
        self.error_class = error_class


def load_secret_env(env_path: str = ENV_FILE) -> None:
    """Load only GOG_KEYRING_PASSWORD from the .env file into os.environ."""
    try:
        from dotenv import dotenv_values
    except ImportError as exc:  # pragma: no cover - dependency is expected to exist
        raise RefreshError("dotenv_unavailable") from exc
    values = dotenv_values(env_path)
    password = values.get("GOG_KEYRING_PASSWORD")
    if not password:
        raise RefreshError("env_missing_secret")
    os.environ["GOG_KEYRING_PASSWORD"] = password
    global DOC_ID
    DOC_ID = DOC_ID or values.get("TI_HIRING_TRACKER_DOC_ID") or ""
    if not DOC_ID:
        raise RefreshError("env_missing_doc_id")


def run_cmd(cmd: list) -> str:
    """Run a command and return stdout, raising RefreshError with no raw output
    leaked on failure. Refuses to run any command containing a forbidden
    mutating verb, as a defense-in-depth guard independent of call sites."""
    joined = " ".join(cmd)
    for forbidden in FORBIDDEN_ARG_SUBSTRINGS:
        if forbidden in joined:
            raise RefreshError("forbidden_command_blocked")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RefreshError("command_execution_failed") from exc
    if proc.returncode != 0:
        raise RefreshError("command_nonzero_exit")
    return proc.stdout


def run_json(cmd: list) -> dict:
    out = run_cmd(cmd)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise RefreshError("command_output_not_json") from exc


@dataclass
class Deps:
    """All external side effects, isolated for deterministic mocked testing."""

    list_tabs: Callable[[], dict]
    cat_tab: Callable[[], str]
    list_comments: Callable[[], dict]
    kanban_list: Callable[[], dict]
    kanban_show: Callable[[str], dict]
    gh_pr_view: Callable[[int], dict]
    gh_issue_view: Callable[[int], dict]
    find_replace: Callable[[str, str], dict]
    append_text: Callable[[str], dict]
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))


def real_deps() -> Deps:
    def list_tabs():
        return run_json(["gog", "docs", "list-tabs", DOC_ID, "-j", "-a", ACCOUNT])

    def cat_tab():
        return run_cmd(["gog", "docs", "cat", DOC_ID, "--tab", TAB_ID, "-a", ACCOUNT])

    def list_comments():
        return run_json(
            [
                "gog", "docs", "comments", "list", DOC_ID,
                "--tab", TAB_ID, "--all", "--include-resolved", "--locate",
                "-j", "-a", ACCOUNT,
            ]
        )

    def kanban_list():
        return run_json(["hermes", "kanban", "--board", BOARD, "list", "--json"])

    def kanban_show(task_id: str):
        return run_json(["hermes", "kanban", "--board", BOARD, "show", task_id, "--json"])

    def gh_pr_view(pr_id: int):
        return run_json(
            ["gh", "pr", "view", str(pr_id), "--repo", REPO, "--json", "state,isDraft"]
        )

    def gh_issue_view(issue_id: int):
        return run_json(
            ["gh", "issue", "view", str(issue_id), "--repo", REPO, "--json", "state"]
        )

    def find_replace(old: str, new: str):
        return run_json(
            [
                "gog", "docs", "find-replace", DOC_ID, old, new,
                "--tab", TAB_ID, "--match-case", "-j", "-a", ACCOUNT,
            ]
        )

    def append_text(text: str):
        return run_json(
            [
                "gog", "docs", "write", DOC_ID, "--tab", TAB_ID,
                "--append", "--text", text, "-j", "-a", ACCOUNT,
            ]
        )

    return Deps(
        list_tabs=list_tabs,
        cat_tab=cat_tab,
        list_comments=list_comments,
        kanban_list=kanban_list,
        kanban_show=kanban_show,
        gh_pr_view=gh_pr_view,
        gh_issue_view=gh_issue_view,
        find_replace=find_replace,
        append_text=append_text,
    )


def iso_now(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def preflight_tab(deps: Deps) -> str:
    tabs = deps.list_tabs()
    match = None
    for t in tabs.get("tabs", []):
        if t.get("id") == TAB_ID:
            match = t
            break
    if match is None or match.get("title") != TAB_TITLE:
        raise RefreshError("tab_preflight_failed")
    text = deps.cat_tab()
    if not text or TAB_TITLE not in text.splitlines()[0]:
        raise RefreshError("tab_preflight_failed")
    return text


def comments_exist(deps: Deps) -> bool:
    data = deps.list_comments()
    if not isinstance(data, dict) or "comments" not in data:
        # Ambiguous/malformed response: fail safe, assume comments present.
        return True
    comments = data.get("comments")
    if comments is None:
        return False
    if not isinstance(comments, list):
        # Anchor/location could not be determined -> fail safe.
        return True
    return len(comments) > 0  # Any comment present at all (open or resolved) blocks replace mode.


def kanban_statuses(deps: Deps, card_ids) -> dict:
    result = {}
    try:
        listing = deps.kanban_list()
    except RefreshError:
        raise RefreshError("kanban_lookup_failed")
    tasks = listing.get("tasks", listing) if isinstance(listing, dict) else listing
    by_id = {}
    if isinstance(tasks, list):
        for t in tasks:
            if isinstance(t, dict) and "id" in t:
                by_id[t["id"]] = t
    for card_id in card_ids:
        task = by_id.get(card_id)
        if task is not None:
            status = task.get("status")
            if not status:
                raise RefreshError("kanban_lookup_failed")
            result[card_id] = status.upper()
            continue
        try:
            shown = deps.kanban_show(card_id)
        except RefreshError:
            raise RefreshError("kanban_lookup_failed")
        task = shown.get("task", shown)
        status = task.get("status") if isinstance(task, dict) else None
        if not status:
            raise RefreshError("kanban_lookup_failed")
        result[card_id] = status.upper()
    return result


def pr_statuses(deps: Deps, pr_ids) -> dict:
    result = {}
    for pr_id in pr_ids:
        try:
            data = deps.gh_pr_view(pr_id)
        except RefreshError:
            raise RefreshError("github_lookup_failed")
        state = data.get("state")
        is_draft = bool(data.get("isDraft"))
        if not state:
            raise RefreshError("github_lookup_failed")
        if state == "OPEN":
            result[str(pr_id)] = "DRAFT" if is_draft else "OPEN"
        else:
            result[str(pr_id)] = state.upper()
    return result


def issue_statuses(deps: Deps, issue_ids) -> dict:
    result = {}
    for issue_id in issue_ids:
        try:
            data = deps.gh_issue_view(issue_id)
        except RefreshError:
            raise RefreshError("github_lookup_failed")
        state = data.get("state")
        if not state:
            raise RefreshError("github_lookup_failed")
        result[str(issue_id)] = state.upper()
    return result


def _mismatch(kind, ident, old_status, new_status, text):
    old_marker = f"[{kind}:{_safe(ident)}:{old_status}]"
    new_marker = f"[{kind}:{_safe(ident)}:{new_status}]"
    return {
        "kind": kind,
        "ident": ident,
        "old_status": old_status,
        "new_status": new_status,
        "old_marker": old_marker,
        "new_marker": new_marker,
        "occurrences": text.count(old_marker),
    }


def compute_replace_mismatches(text: str, statuses_by_kind: dict):
    """Body marker is the sole source of truth in replace mode: mismatch iff
    the literal bracket status differs from the freshly-read status. Scoped
    to the static body only (before any change-log tail) so a leftover
    append-mode ledger is never parsed as if it were live body markers."""
    body_text, _ = split_body_and_log(text)
    mismatches = []
    for kind, ident, old_status in CARD_RE.findall(body_text):
        new_status = statuses_by_kind.get(kind, {}).get(ident)
        if new_status is None or new_status == old_status:
            continue
        mismatches.append(_mismatch(kind, ident, old_status, new_status, body_text))
    return mismatches


def latest_logged_status(text: str) -> dict:
    """Last-appended status per (kind, ident), in the order lines appear
    (later append calls land later in the text, so the final regex match per
    key is the most recent one logged)."""
    latest = {}
    for kind, ident, logged_new_status in APPENDED_RE.findall(text):
        latest[(kind, ident)] = logged_new_status
    return latest


def compute_append_mismatches(text: str, statuses_by_kind: dict):
    """The body marker never changes in append mode, so the source of truth
    for "what we last recorded" is the latest change-log entry for that
    marker, not the (permanently stale) bracket text. Mismatch iff the
    latest logged status (or the body status, if never logged) differs from
    the freshly-read status; this correctly re-fires on a later transition
    back to an earlier status (e.g. BLOCKED -> RUNNING -> BLOCKED)."""
    body_text, _ = split_body_and_log(text)
    body_status = {}
    for kind, ident, old_status in CARD_RE.findall(body_text):
        body_status.setdefault((kind, ident), old_status)
    logged = latest_logged_status(text)
    mismatches = []
    for (kind, ident), fallback_status in body_status.items():
        new_status = statuses_by_kind.get(kind, {}).get(ident)
        if new_status is None:
            continue
        effective_status = logged.get((kind, ident), fallback_status)
        if new_status == effective_status:
            continue  # latest known state already matches the source; no-op
        mismatches.append(_mismatch(kind, ident, effective_status, new_status, text))
    return mismatches


def _count_exact_lines(text: str, line: str) -> int:
    """Count exact line matches (split on newline), not substring occurrences.
    A historical ledger line can be byte-identical to a line this run is
    about to (re)write -- e.g. the same status transition logged again at
    the same second, or a repeated "Checked at <iso>" line. Substring
    membership can't tell "already there from history" apart from "this
    run's write actually landed"; an exact per-line count, compared against
    a pre-write snapshot, can."""
    return sum(1 for candidate in text.splitlines() if candidate == line)


def extract_checked_marker(text: str):
    matches = CHECKED_RE.findall(text)
    if len(matches) != 1:
        raise RefreshError("checked_marker_invalid")
    old_iso = matches[0]
    old_marker = f"[CHECKED:{old_iso}]"
    if text.count(old_marker) != 1:
        raise RefreshError("checked_marker_invalid")
    return old_marker, old_iso


def extract_body_card_ids(text: str):
    """Card ids present in the static body only. A card id that only ever
    appears inside an [APPENDED ...] change-log line (never in the live
    body) must never be looked up or tracked -- it is history, not a live
    marker to source or act on."""
    body_text, _ = split_body_and_log(text)
    return sorted(set(m.group(2) for m in CARD_RE.finditer(body_text) if m.group(1) == "CARD"))


def build_plan(deps: Deps):
    text = preflight_tab(deps)
    has_comments = comments_exist(deps)

    card_ids = extract_body_card_ids(text)
    statuses_by_kind = {
        "CARD": kanban_statuses(deps, card_ids),
        "PR": pr_statuses(deps, PR_IDS),
        "ISSUE": issue_statuses(deps, ISSUE_IDS),
    }
    old_checked_marker, _ = extract_checked_marker(text)
    mode = "append" if has_comments else "replace"
    if mode == "replace":
        mismatches = compute_replace_mismatches(text, statuses_by_kind)
    else:
        mismatches = compute_append_mismatches(text, statuses_by_kind)
    return text, mismatches, mode, old_checked_marker


def run_refresh(deps: Deps, dry_run: bool) -> dict:
    text, mismatches, mode, old_checked_marker = build_plan(deps)
    now = deps.now()
    new_iso = iso_now(now)
    changed_labels = [
        f"{m['kind']}:{m['ident']}:{m['old_status']}->{m['new_status']}" for m in mismatches
    ]

    if dry_run:
        return {"checked_utc": new_iso, "changed": changed_labels, "mode": mode, "dry_run": True}

    applied = []
    if mode == "replace":
        # "occurrences" (from compute_replace_mismatches) is body-scoped and
        # only tells us whether the marker is unambiguous within the live
        # body. But gog find-replace operates over the WHOLE tab text,
        # including any leftover append-mode change-log tail. If the old
        # marker's literal text is also echoed inside that ledger (e.g. a
        # historical "[CARD:x:RUNNING] -> [CARD:x:BLOCKED]" line), a
        # body-unique marker can still be globally ambiguous, and a find
        # -replace call would silently rewrite the ledger too, corrupting
        # history. Require BOTH body-uniqueness and whole-tab uniqueness
        # before ever issuing the real find-replace call; fail safe (no
        # write attempted at all) otherwise.
        applicable = []
        failures = []
        for m in mismatches:
            if m["occurrences"] != 1 or text.count(m["old_marker"]) != 1:
                failures.append(m)
            else:
                applicable.append(m)
        for m in applicable:
            resp = deps.find_replace(m["old_marker"], m["new_marker"])
            if resp.get("replacements") != 1:
                failures.append(m)
            else:
                applied.append(m)

        if failures:
            raise RefreshError("replacement_mismatch")

        old_checked_full = old_checked_marker
        new_checked_marker = f"[CHECKED:{new_iso}]"
        resp = deps.find_replace(old_checked_full, new_checked_marker)
        if resp.get("replacements") != 1:
            raise RefreshError("checked_refresh_failed")

        reread = deps.cat_tab()
        for m in applied:
            if m["new_marker"] not in reread:
                raise RefreshError("readback_mismatch")
        if new_checked_marker not in reread:
            raise RefreshError("readback_mismatch")

    else:  # append mode
        # compute_append_mismatches already excludes markers whose latest
        # logged (or body) status matches the source; every entry here is
        # a real transition that must be recorded.
        status_lines = []
        for m in mismatches:
            snippet = f"{m['old_marker']} -> {m['new_marker']}"
            status_lines.append(f"[APPENDED {_safe(new_iso)}] {snippet}")
            applied.append(m)

        # Bounded append-only fix: a historical ledger can already contain a
        # line byte-identical to the one this run needs to write (e.g. the
        # same transition re-occurring at the same second, or the same
        # "Checked at <iso>" text from a prior run at that timestamp). A
        # plain substring check against the reread text can't distinguish
        # "already there from history" from "this run's write landed", so a
        # silently no-op'd append_text call would falsely read back as a
        # success. Instead, snapshot the EXACT per-line count before writing
        # and require it to have strictly increased afterward -- a
        # duplicate that pre-existed cannot manufacture that increase.
        pre_write_text = text
        if status_lines:
            pre_counts = [_count_exact_lines(pre_write_text, ln) for ln in status_lines]
            deps.append_text("\n".join(status_lines))
            post_status_text = deps.cat_tab()
            for ln, pre_count in zip(status_lines, pre_counts):
                if _count_exact_lines(post_status_text, ln) <= pre_count:
                    raise RefreshError("readback_mismatch")
        else:
            post_status_text = pre_write_text

        # Only after every status transition is confirmed as a demonstrably
        # new line do we advance the "Checked at" marker, using the same
        # exact-line-count discipline against a snapshot taken right before
        # this write.
        checked_line = f"Checked at {new_iso}"
        pre_checked_count = _count_exact_lines(post_status_text, checked_line)
        deps.append_text(checked_line)
        reread = deps.cat_tab()
        if _count_exact_lines(reread, checked_line) <= pre_checked_count:
            raise RefreshError("readback_mismatch")

    applied_labels = [
        f"{m['kind']}:{m['ident']}:{m['old_status']}->{m['new_status']}" for m in applied
    ]
    return {"checked_utc": new_iso, "changed": applied_labels, "mode": mode, "dry_run": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Read-only plan, no writes")
    parser.add_argument("--once", action="store_true", help="Perform one update (default)")
    args = parser.parse_args(argv)

    try:
        load_secret_env()
        deps = real_deps()
        result = run_refresh(deps, dry_run=args.dry_run)
    except RefreshError as exc:
        print(json.dumps({"error": exc.error_class}))
        return 1
    except Exception:  # pragma: no cover - last-resort guard, never leak details
        print(json.dumps({"error": "unexpected_error"}))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
