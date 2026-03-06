#!/usr/bin/env python3
"""
Smart continue - find the best session to resume based on current context.
Called by: agents continue [--dry-run]
Env vars: CWD, GIT_BRANCH, DRY_RUN (true/false)
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   agent_color, time_ago, get_first_message)

cwd = os.environ.get("CWD", os.getcwd())
git_branch = os.environ.get("GIT_BRANCH", "")
dry_run = os.environ.get("DRY_RUN", "false") == "true"

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
available = [a for a in ALL_ADAPTERS if a.is_available()]


def get_session_branch(fpath):
    """Extract git branch from first few lines of a session file."""
    try:
        with open(fpath) as f:
            for i, line in enumerate(f):
                if i > 20:
                    break
                try:
                    d = json.loads(line)
                    branch = d.get("gitBranch", "")
                    if branch:
                        return branch
                except (json.JSONDecodeError, KeyError):
                    pass
    except OSError:
        pass
    return ""


def cmd_continue():
    candidates = []

    for adapter in available:
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue

            score = 0
            reasons = []

            if display_path == cwd or cwd.startswith(display_path) or display_path.startswith(cwd):
                score += 100
                reasons.append("directory match")
            elif os.path.basename(display_path) == os.path.basename(cwd):
                score += 30
                reasons.append("basename match")
            else:
                continue

            age = time.time() - mtime
            if age < 3600:
                score += 50
                reasons.append("< 1h ago")
            elif age < 86400:
                score += 30
                reasons.append("today")
            elif age < 604800:
                score += 10
                reasons.append("this week")

            if git_branch:
                session_branch = get_session_branch(fpath)
                if session_branch == git_branch:
                    score += 40
                    reasons.append(f"branch: {git_branch}")

            try:
                fsize = os.path.getsize(fpath)
                if fsize > 1_000_000:
                    score += 10
                    reasons.append("large session")
            except OSError:
                fsize = 0

            session_id = os.path.basename(fpath).replace(".jsonl", "")
            candidates.append({
                "score": score,
                "reasons": reasons,
                "adapter": adapter.name,
                "path": display_path,
                "fpath": fpath,
                "session_id": session_id,
                "mtime": mtime,
                "size": fsize,
            })

    candidates.sort(key=lambda c: -c["score"])

    if not candidates:
        print(f"{GRAY}No sessions found for {cwd}{R}")
        print(f"{DIM}Start a new session with: claude  or  codex{R}")
        raise SystemExit(1)

    best = candidates[0]
    a_color = agent_color(best["adapter"])
    badge = f"{a_color}[{best['adapter']}]{R}"
    age = time_ago(best["mtime"])
    preview = get_first_message(best["fpath"], best["adapter"])

    print(f"{BOLD}{CYAN}Best match:{R}")
    print(f"  {badge} {WHITE}{best['session_id'][:8]}{R} {DIM}({age}){R}")
    print(f"  {BLUE}{best['path']}{R}")
    if preview:
        print(f"  {GRAY}\"{preview}\"{R}")
    print(f"  {DIM}Score: {best['score']} ({', '.join(best['reasons'])}){R}")
    print()

    if len(candidates) > 1:
        print(f"{DIM}Other candidates:{R}")
        for c in candidates[1:4]:
            cb = f"{agent_color(c['adapter'])}[{c['adapter']}]{R}"
            print(f"  {cb} {c['session_id'][:8]} {DIM}({time_ago(c['mtime'])}, score: {c['score']}){R}")
        print()

    if dry_run:
        print(f"{DIM}Dry run - not launching.{R}")
        if best["adapter"] == "codex":
            print(f"{DIM}Would run: cd \"{best['path']}\" && codex resume \"{best['session_id']}\"{R}")
        else:
            print(f"{DIM}Would run: cd \"{best['path']}\" && claude -r \"{best['session_id']}\"{R}")
    else:
        try:
            os.chdir(best["path"])
        except OSError:
            print(f"{RED}Could not cd to {best['path']}{R}")
            raise SystemExit(1)
        if best["adapter"] == "codex":
            os.execvp("codex", ["codex", "resume", best["session_id"]])
        else:
            os.execvp("claude", ["claude", "-r", best["session_id"]])


if __name__ == "__main__":
    cmd_continue()
