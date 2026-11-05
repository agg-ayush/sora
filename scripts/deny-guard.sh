#!/usr/bin/env python3
"""T3 PreToolUse command guard; exit 2 blocks a Bash tool call."""

import json
import os
import re
import shlex
import sys
from urllib.parse import urlsplit


REASONS = {
    "git": "git push — the merge gate is the broker; the T3 agent edits+commits, never pushes",
    "pr": "gh pr create/merge — the merge gate is the broker; the T3 agent edits+commits, never PRs",
    "shared": "gh release/repo create/delete — shared-infra, the broker owns it",
    "rm": "rm -rf / or ~ — catastrophic",
    "sudo": "sudo — not in a T3 session",
    "secret": "reading a secrets file — the T3 agent doesn't need to read credentials",
    "cloud": "cloud destructive command — the broker owns infra mutations",
    "network": "curl/wget to a non-allowlisted host — potential exfil",
}
ALLOWED_HOSTS = {
    "api.github.com", "github.com", "raw.githubusercontent.com",
    "<model-gateway>", "<model-gateway>",
    "<llm-gateway>.truefoundry.cloud", "api.fireworks.ai", "api.anthropic.com",
    "localhost", "127.0.0.1",
}
ROOT_TARGETS = {"/", "/*", "~", "~/", "$HOME", "${HOME}", "$HOME/"}
SECRETS = re.compile(r"(\.env|credentials|secrets?|\.pem|\.key|id_rsa|id_ed25519)\b")
ASSIGNMENT = re.compile(r"[a-zA-Z_][a-zA-Z_0-9]*=.*", re.DOTALL)
URLISH = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?::\d+)?(?:/|$)|localhost(?::\d+)?(?:/|$)|127\.0\.0\.1(?::\d+)?(?:/|$))")


def substitutions(command):
    """Yield executable substitution bodies, ignoring single-quoted literals."""
    i = 0
    quote = None
    while i < len(command):
        char = command[i]
        if char == "\\" and quote != "'":
            i += 2
            continue
        if char == "'" and quote != '"':
            quote = None if quote == "'" else "'"
        elif char == '"' and quote != "'":
            quote = None if quote == '"' else '"'
        elif quote != "'" and command.startswith("$(", i):
            start = i + 2
            depth = 1
            j = start
            inner_quote = None
            while j < len(command) and depth:
                c = command[j]
                if c == "\\" and inner_quote != "'":
                    j += 2
                    continue
                if c == "'" and inner_quote != '"':
                    inner_quote = None if inner_quote == "'" else "'"
                elif c == '"' and inner_quote != "'":
                    inner_quote = None if inner_quote == '"' else '"'
                elif inner_quote != "'":
                    if command.startswith("$(", j):
                        depth += 1
                        j += 2
                        continue
                    if c == ")":
                        depth -= 1
                j += 1
            if depth == 0:
                yield command[start:j - 1]
                i = j
                continue
        elif quote != "'" and char == "`":
            j = i + 1
            while j < len(command) and command[j] != "`":
                j += 2 if command[j] == "\\" else 1
            if j < len(command):
                yield command[i + 1:j]
                i = j + 1
                continue
        i += 1


def skip_options(args, valued, valueless=()):
    """Find a CLI subcommand past global options with or without values."""
    index = 0
    while index < len(args):
        token = args[index]
        if token in valued:
            index += 2
        elif any(token.startswith(option + "=") for option in valued if option.startswith("--")):
            index += 1
        elif any(token.startswith(option) and token != option for option in valued if option.startswith("-") and len(option) == 2):
            index += 1
        elif token in valueless or token.startswith("-"):
            index += 1
        else:
            break
    return args[index:]


def unwrap(tokens):
    tokens = list(tokens)
    while tokens:
        binary = os.path.basename(tokens[0])
        if ASSIGNMENT.fullmatch(tokens[0]):
            tokens.pop(0)
        elif binary == "env":
            tokens.pop(0)
            while tokens and tokens[0].startswith("-"):
                option = tokens.pop(0)
                if option in ("-u", "--unset", "-C", "--chdir") and tokens:
                    tokens.pop(0)
        elif binary in ("command", "nohup", "time", "xargs", "exec"):
            tokens.pop(0)
            while tokens and tokens[0].startswith("-"):
                option = tokens.pop(0)
                if binary == "xargs" and option in ("-n", "-P", "-s", "-I", "-L") and tokens:
                    tokens.pop(0)
        else:
            break
    return tokens


def check_segment(tokens, depth):
    tokens = unwrap(tokens)
    if not tokens:
        return None
    binary = os.path.basename(tokens[0])
    args = tokens[1:]

    if binary in ("bash", "sh", "zsh"):
        for index, arg in enumerate(args):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", arg) and index + 1 < len(args):
                return check_command(args[index + 1], depth + 1)

    if binary == "git":
        rest = skip_options(args, ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"), ("--no-pager", "-P", "--bare"))
        if rest and rest[0] == "push":
            return REASONS["git"]
    elif binary == "gh":
        rest = skip_options(args, ("-R", "--repo"))
        if rest and rest[0] in ("pr", "release", "repo"):
            group = rest[0]
            action = skip_options(rest[1:], ("-R", "--repo"))
            if action and group == "pr" and action[0] in ("create", "merge", "close", "reopen", "edit"):
                return REASONS["pr"]
            if action and group in ("release", "repo") and action[0] in ("create", "delete"):
                return REASONS["shared"]
    elif binary == "rm":
        recursive = any(arg in ("--recursive", "-r", "-R") or (arg.startswith("-") and not arg.startswith("--") and "r" in arg.lower()) for arg in args)
        force = any(arg == "--force" or (arg.startswith("-") and not arg.startswith("--") and "f" in arg) for arg in args)
        if recursive and force and any(arg in ROOT_TARGETS for arg in args):
            return REASONS["rm"]
    elif binary == "sudo":
        return REASONS["sudo"]
    elif binary in ("cat", "less", "head", "tail", "more"):
        if any(SECRETS.search(arg) for arg in args):
            return REASONS["secret"]
    elif binary in ("aws", "gcloud", "az"):
        if any(re.match(r"^(delete|remove|destroy|terminate)(?:$|[-_])", arg) for arg in args):
            return REASONS["cloud"]
    elif binary in ("curl", "wget"):
        urls = [arg for arg in args if URLISH.match(arg) and not arg.startswith("-")]
        if not urls or any(urlsplit(url if "://" in url else "//" + url).hostname not in ALLOWED_HOSTS for url in urls):
            return REASONS["network"]
    return None


def fallback(command):
    """Fail closed for push and PR mutations if shell tokenization fails."""
    git = r"(?<![\w./-])(?:[\w./-]*/)?git\b[^;&|\n]*\bpush\b"
    pr = r"(?<![\w./-])(?:[\w./-]*/)?gh\b[^;&|\n]*\bpr\b[^;&|\n]*\b(create|merge|close|reopen|edit)\b"
    if re.search(git, command):
        return REASONS["git"]
    if re.search(pr, command):
        return REASONS["pr"]
    return None


def check_command(command, depth=0):
    if depth > 20:
        return fallback(command)
    for inner in substitutions(command):
        result = check_command(inner, depth + 1)
        if result:
            return result
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return fallback(command)
    segment = []
    for token in tokens + [";"]:
        if token and all(char in ";&|()\n" for char in token):
            if segment:
                result = check_segment(segment, depth)
                if result:
                    return result
            segment = []
        else:
            segment.append(token)
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("tool_name", "Bash") != "Bash":
            return 0
        command = payload.get("tool_input", {}).get("command", "")
        if not isinstance(command, str):
            return 0
    except (ValueError, TypeError, AttributeError):
        return 0
    reason = check_command(command)
    if reason:
        print("BLOCKED by deny-guard: " + reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
