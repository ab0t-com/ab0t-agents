#!/usr/bin/env python3
"""
Show sessions for a specific project across all coding agents.
Called by: agents show
Env vars: TARGET (path or "." for cwd)

Writes sessions_cache.json for use by resume.
"""

import os
import sys
import json
import time
import glob
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

target = os.environ.get("TARGET", ".")
if target == ".":
    target = os.getcwd()

WHITE = "\033[1;37m"
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
MAGENTA = "\033[0;35m"
BLUE = "\033[0;34m"
GRAY = "\033[0;90m"
BOLD = "\033[1m"
DIM = "\033[2m"
R = "\033[0m"

CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
now = time.time()


def time_ago(ts):
    s = int(now - ts)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    if s < 604800:
        return f"{s // 86400}d ago"
    return f"{s // 604800}w ago"


def get_first_msg(fpath, agent_name):
    """Get first user message from session file."""
    try:
        with open(fpath) as f:
            for i, line in enumerate(f):
                if i > 50:
                    break
                try:
                    d = json.loads(line)
                    # Claude format
                    if agent_name == "claude" and d.get("type") == "user":
                        content = d.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            return " ".join(content.split())[:55]
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    return " ".join(item.get("text", "").split())[:55]
                    # Codex format
                    elif agent_name == "codex" and d.get("type") == "response_item":
                        p = d.get("payload", {})
                        if p.get("role") == "user":
                            for item in p.get("content", []):
                                if isinstance(item, dict):
                                    text = item.get("text", "")
                                    if text and not text.startswith("#") and not text.startswith("<"):
                                        return " ".join(text.split())[:55]
                except (json.JSONDecodeError, KeyError):
                    pass
    except OSError:
        pass
    return ""


def get_codex_first_msg_from_history(session_id):
    """Fallback: get first user message from codex history.jsonl."""
    hfile = os.path.expanduser("~/.codex/history.jsonl")
    if not os.path.isfile(hfile):
        return ""
    try:
        with open(hfile) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if d.get("session_id") == session_id:
                        return " ".join(d.get("text", "").split())[:55]
                except (json.JSONDecodeError, KeyError):
                    pass
    except OSError:
        pass
    return ""


# Collect sessions from all adapters for the target path
# Each entry: (mtime, session_id, fpath, agent_name, size_bytes)
sessions = []

# --- Claude ---
claude = ClaudeAdapter()
if claude.is_available():
    # Encode target path to find the Claude project dir
    encoded = target.lstrip("/")
    encoded = "".join("-" if ch in "/_.@ " else ch for ch in encoded)
    encoded = "-" + encoded
    proj_dir = os.path.join(claude.projects_dir, encoded)

    if os.path.isdir(proj_dir):
        for fname in os.listdir(proj_dir):
            if not fname.endswith(".jsonl") or fname.startswith("agent-"):
                continue
            fpath = os.path.join(proj_dir, fname)
            session_id = fname.replace(".jsonl", "")
            try:
                mtime = os.path.getmtime(fpath)
                size = os.path.getsize(fpath)
            except OSError:
                mtime, size = 0, 0
            sessions.append((mtime, session_id, fpath, "claude", size))

# --- Codex ---
codex = CodexAdapter()
if codex.is_available():
    for sf in glob.glob(
        os.path.join(codex.sessions_dir, "**", "*.jsonl"), recursive=True
    ):
        try:
            with open(sf) as f:
                first = json.loads(f.readline())
                if first.get("type") == "session_meta":
                    cwd = first.get("payload", {}).get("cwd", "")
                    sid = first.get("payload", {}).get("id", "")
                    if cwd == target:
                        mtime = os.path.getmtime(sf)
                        size = os.path.getsize(sf)
                        sessions.append((mtime, sid, sf, "codex", size))
        except (OSError, json.JSONDecodeError):
            pass

if not sessions:
    print(f"{GRAY}No sessions found for: {target}{R}")
    raise SystemExit(1)

sessions.sort(key=lambda x: -x[0])

AGENT_COLORS = {a.name: a.color for a in ALL_ADAPTERS}

print(f"{BOLD}{CYAN}Sessions in {YELLOW}{target}{R}")
print(f"{DIM}{'─' * 52}{R}")
print()

# For cache: list of {session_id, path, agent}
cache_list = []

for idx, (mtime, session_id, fpath, aname, size) in enumerate(sessions[:15], 1):
    cache_list.append({"session_id": session_id, "path": target, "agent": aname})

    age = now - mtime
    age_str = time_ago(mtime)
    date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

    time_color = GRAY
    if age < 3600:
        time_color = GREEN
    elif age < 86400:
        time_color = YELLOW

    # Human-readable size
    if size > 1_000_000:
        size_str = f"{size / 1_000_000:.1f}M"
    elif size > 1_000:
        size_str = f"{size / 1_000:.0f}K"
    else:
        size_str = f"{size}B"

    a_color = AGENT_COLORS.get(aname, GRAY)
    badge = f"{a_color}[{aname}]{R}"

    preview = get_first_msg(fpath, aname)
    if not preview and aname == "codex":
        preview = get_codex_first_msg_from_history(session_id)
    if len(preview) > 50:
        preview = preview[:47] + "..."

    print(f"{BOLD}{WHITE}[{idx:2d}]{R} {badge} {MAGENTA}{session_id[:8]}{R}")
    print(f"     {time_color}{age_str:<10}{R} {DIM}{date_str}{R}  {DIM}({size_str}){R}")
    if preview:
        print(f"     {GRAY}\"{preview}\"{R}")

print(f"{DIM}{'─' * 52}{R}")
print(f"{BOLD}Resume:{R}")
print()

# Show resume hints for each agent type present
agent_types = set(s[3] for s in sessions)
if "claude" in agent_types:
    print(f"  {GREEN}cd {target} && claude -c{R}  {DIM}# continue last claude session{R}")
if "codex" in agent_types:
    print(f"  {GREEN}cd {target} && codex resume --last{R}  {DIM}# continue last codex session{R}")
print(f"  {GREEN}agents resume <num>{R}  {DIM}# resume specific session from above{R}")
print()

# Save cache
os.makedirs(CACHE_DIR, exist_ok=True)
with open(os.path.join(CACHE_DIR, "sessions_cache.json"), "w") as f:
    json.dump(cache_list, f)
with open(os.path.join(CACHE_DIR, "path_cache"), "w") as f:
    f.write(target)
