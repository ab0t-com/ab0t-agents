#!/usr/bin/env python3
"""
Fork a session at a specific point, creating a new session.
Called by: agents fork <session-num|session-id> [--at N]
Env vars: SESSION_KEY, FORK_AT (message number, default: all)
"""

import os
import sys
import json
import uuid
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

WHITE = "\033[1;37m"
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
GRAY = "\033[0;90m"
RED = "\033[0;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
R = "\033[0m"

CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")
FORKS_DIR = os.path.join(CACHE_DIR, "forks")
session_key = os.environ.get("SESSION_KEY", "")
fork_at = os.environ.get("FORK_AT", "")


def resolve_session():
    cache_file = os.path.join(CACHE_DIR, "sessions_cache.json")
    if session_key.isdigit() and os.path.isfile(cache_file):
        try:
            with open(cache_file) as f:
                sessions = json.load(f)
            idx = int(session_key) - 1
            if 0 <= idx < len(sessions):
                s = sessions[idx]
                return s.get("file", ""), s.get("agent", "claude"), s.get("path", "")
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    for adapter in [ClaudeAdapter(), CodexAdapter()]:
        if not adapter.is_available():
            continue
        for display, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            basename = os.path.basename(fpath).replace(".jsonl", "")
            if basename.startswith(session_key) or session_key in basename:
                return fpath, adapter.name, display
    return "", "", ""


if not session_key:
    print(f"{RED}Usage: agents fork <session-num|session-id> [--at N]{R}")
    raise SystemExit(1)

fpath, agent_name, project = resolve_session()
if not fpath or not os.path.isfile(fpath):
    print(f"{RED}Could not find session: {session_key}{R}")
    raise SystemExit(1)

parent_id = os.path.basename(fpath).replace(".jsonl", "")

# Count messages and determine fork point
message_count = 0
lines = []
try:
    with open(fpath) as f:
        for line in f:
            lines.append(line)
            try:
                d = json.loads(line)
                if d.get("type") in ("user", "assistant") or \
                   (d.get("type") == "response_item" and d.get("item", {}).get("role") in ("user", "assistant")):
                    message_count += 1
            except (json.JSONDecodeError, KeyError):
                pass
except OSError:
    print(f"{RED}Could not read session file.{R}")
    raise SystemExit(1)

# Determine cutoff
if fork_at:
    cutoff_msg = int(fork_at)
else:
    cutoff_msg = message_count  # Fork with all messages (branch from current point)

# Copy lines up to the cutoff message
forked_lines = []
msg_seen = 0
for line in lines:
    try:
        d = json.loads(line)
        is_msg = d.get("type") in ("user", "assistant") or \
                 (d.get("type") == "response_item" and d.get("item", {}).get("role") in ("user", "assistant"))
        if is_msg:
            msg_seen += 1
            if msg_seen > cutoff_msg:
                break
        forked_lines.append(line)
    except (json.JSONDecodeError, KeyError):
        forked_lines.append(line)

# Generate new session ID and write fork
fork_id = str(uuid.uuid4())
os.makedirs(FORKS_DIR, exist_ok=True)

fork_file = os.path.join(FORKS_DIR, f"{fork_id}.jsonl")

# Write fork metadata as first line
fork_meta = json.dumps({
    "type": "fork_meta",
    "parent_session": parent_id,
    "parent_file": fpath,
    "parent_agent": agent_name,
    "fork_at_message": cutoff_msg,
    "fork_timestamp": datetime.utcnow().isoformat() + "Z",
    "project": project,
})

with open(fork_file, "w") as f:
    f.write(fork_meta + "\n")
    for line in forked_lines:
        f.write(line)

# Also save a forks index
forks_index = os.path.join(FORKS_DIR, "index.json")
try:
    with open(forks_index) as f:
        index = json.load(f)
except (OSError, json.JSONDecodeError):
    index = []

index.append({
    "fork_id": fork_id,
    "parent_id": parent_id,
    "parent_agent": agent_name,
    "fork_at": cutoff_msg,
    "total_messages": message_count,
    "project": project,
    "created": datetime.utcnow().isoformat() + "Z",
})

with open(forks_index, "w") as f:
    json.dump(index, f, indent=2)

print(f"{BOLD}{CYAN}Session Forked{R}")
print(f"{DIM}{'─' * 52}{R}")
print(f"  {WHITE}Parent:{R}  {parent_id[:8]} ({agent_name})")
print(f"  {WHITE}Fork:{R}    {fork_id[:8]}")
print(f"  {WHITE}At:{R}      message {cutoff_msg} of {message_count}")
print(f"  {WHITE}File:{R}    {fork_file}")
print()
print(f"{DIM}This fork is a snapshot. To resume it as a new session,{R}")
print(f"{DIM}you can inject it as context into a fresh session.{R}")
