#!/usr/bin/env python3
"""
Show what files were changed during a session.
Called by: agents diff <session-num|session-id> [--project PATH]
Env vars: SESSION_KEY, PROJECT (path)
"""

import os
import sys
import json
import time
import re
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   resolve_session as _resolve_session)

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]

session_key = os.environ.get("SESSION_KEY", "")
project_path = os.environ.get("PROJECT", "")


def resolve_session():
    """Resolve session key to (filepath, agent_name)."""
    fpath, agent_name, _project, _sid = _resolve_session(session_key, ALL_ADAPTERS)
    return fpath, agent_name


def extract_changes_claude(fpath):
    """Extract file changes from a Claude session."""
    files_modified = {}
    files_created = set()
    commands_run = []
    git_commits = []
    session_start = None
    session_end = None

    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    ts_str = d.get("timestamp")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if session_start is None or ts < session_start:
                                session_start = ts
                            if session_end is None or ts > session_end:
                                session_end = ts
                        except ValueError:
                            pass

                    if d.get("type") == "assistant":
                        msg = d.get("message", {})
                        content = msg.get("content", [])
                        if not isinstance(content, list):
                            continue
                        for item in content:
                            if not isinstance(item, dict):
                                continue
                            if item.get("type") == "tool_use":
                                name = item.get("name", "")
                                inp = item.get("input", {})

                                if name in ("Write", "Edit"):
                                    fp = inp.get("file_path", "")
                                    if fp:
                                        if fp not in files_modified:
                                            files_modified[fp] = {"edits": 0, "writes": 0}
                                        if name == "Write":
                                            files_modified[fp]["writes"] += 1
                                        else:
                                            files_modified[fp]["edits"] += 1

                                elif name == "Bash":
                                    cmd = inp.get("command", "")
                                    if cmd:
                                        commands_run.append(cmd)
                                        # Detect git commits
                                        if "git commit" in cmd:
                                            git_commits.append(cmd)

                    elif d.get("type") == "tool_result":
                        pass  # Could extract exit codes here

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    return {
        "files": files_modified,
        "commands": commands_run,
        "git_commits": git_commits,
        "start": session_start,
        "end": session_end,
    }


def extract_changes_codex(fpath):
    """Extract file changes from a Codex session."""
    files_modified = {}
    commands_run = []
    git_commits = []
    session_start = None
    session_end = None

    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    rec_type = d.get("type")

                    if rec_type == "event_msg":
                        event = d.get("event", {})
                        etype = event.get("type", "")
                        if etype in ("file_write", "file_edit"):
                            fp = event.get("file_path", event.get("path", ""))
                            if fp:
                                if fp not in files_modified:
                                    files_modified[fp] = {"edits": 0, "writes": 0}
                                if etype == "file_write":
                                    files_modified[fp]["writes"] += 1
                                else:
                                    files_modified[fp]["edits"] += 1
                        elif etype == "command":
                            cmd = event.get("command", "")
                            if cmd:
                                commands_run.append(cmd)
                                if "git commit" in cmd:
                                    git_commits.append(cmd)

                    ts_str = d.get("ts", d.get("timestamp", ""))
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                            if session_start is None or ts < session_start:
                                session_start = ts
                            if session_end is None or ts > session_end:
                                session_end = ts
                        except (ValueError, TypeError):
                            pass

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    return {
        "files": files_modified,
        "commands": commands_run,
        "git_commits": git_commits,
        "start": session_start,
        "end": session_end,
    }


def cmd_diff():
    if not session_key:
        print(f"{RED}Usage: agents diff <session-num|session-id>{R}")
        print(f"{DIM}Run 'agents show' first, then 'agents diff 1'{R}")
        raise SystemExit(1)

    fpath, agent_name = resolve_session()
    if not fpath or not os.path.isfile(fpath):
        print(f"{RED}Could not find session: {session_key}{R}")
        print(f"{DIM}Run 'agents show' first to populate session cache.{R}")
        raise SystemExit(1)

    session_id = os.path.basename(fpath).replace(".jsonl", "")

    if agent_name == "codex":
        changes = extract_changes_codex(fpath)
    else:
        changes = extract_changes_claude(fpath)

    # Display
    duration = ""
    if changes["start"] and changes["end"]:
        delta = changes["end"] - changes["start"]
        secs = int(delta.total_seconds())
        if secs >= 3600:
            duration = f"{secs // 3600}h {(secs % 3600) // 60}m"
        elif secs >= 60:
            duration = f"{secs // 60}m"
        else:
            duration = f"{secs}s"

    a_color = CYAN if agent_name == "claude" else GREEN
    badge = f"{a_color}[{agent_name}]{R}"
    date_str = changes["start"].strftime("%Y-%m-%d %H:%M") if changes["start"] else "unknown"

    print(f"{BOLD}{CYAN}Session Diff{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"  {badge} {WHITE}{session_id[:8]}{R} {DIM}{date_str}{R}", end="")
    if duration:
        print(f" {DIM}({duration}){R}")
    else:
        print()
    print()

    if changes["files"]:
        print(f"{BOLD}  Modified Files:{R}")
        for fp, counts in sorted(changes["files"].items()):
            parts = []
            if counts["writes"]:
                parts.append(f"{counts['writes']} write{'s' if counts['writes'] > 1 else ''}")
            if counts["edits"]:
                parts.append(f"{counts['edits']} edit{'s' if counts['edits'] > 1 else ''}")
            detail = ", ".join(parts)
            print(f"    {GREEN}{fp}{R}  {DIM}({detail}){R}")
        print()
    else:
        print(f"  {GRAY}No file modifications detected.{R}")
        print()

    if changes["commands"]:
        seen = set()
        unique_cmds = []
        for cmd in changes["commands"]:
            short = cmd.strip()[:80]
            if short not in seen:
                seen.add(short)
                unique_cmds.append(short)

        print(f"{BOLD}  Commands Run:{R} {DIM}({len(changes['commands'])} total, {len(unique_cmds)} unique){R}")
        for cmd in unique_cmds[:15]:
            print(f"    {DIM}${R} {cmd}")
        if len(unique_cmds) > 15:
            print(f"    {DIM}... and {len(unique_cmds) - 15} more{R}")
        print()

    if changes["git_commits"]:
        print(f"{BOLD}  Git Commits:{R}")
        for cmd in changes["git_commits"]:
            m = re.search(r'-m\s+["\']([^"\']+)["\']', cmd)
            if m:
                print(f"    {YELLOW}{m.group(1)}{R}")
            else:
                print(f"    {DIM}{cmd[:70]}{R}")
        print()

    print(f"{DIM}{'─' * 52}{R}")
    print(f"  {WHITE}{len(changes['files'])}{R} files  {WHITE}{len(changes['commands'])}{R} commands  {WHITE}{len(changes['git_commits'])}{R} commits")


if __name__ == "__main__":
    cmd_diff()
