#!/usr/bin/env python3
"""
Session threading - shared communication channel between sessions.
Called by: agents thread <action> [args]
Env vars: ACTION (create/list/show/post/close), THREAD_NAME, MESSAGE
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, time_ago)

THREADS_DIR = os.path.join(CACHE_DIR, "threads")
ARCHIVE_DIR = os.path.join(THREADS_DIR, ".archive")

action = os.environ.get("ACTION", "list")
thread_name = os.environ.get("THREAD_NAME", "")
message = os.environ.get("MESSAGE", "")
sender = os.environ.get("SENDER", "user")


def thread_path(name):
    return os.path.join(THREADS_DIR, f"{name}.thread")


def read_thread(path):
    """Read all messages from a thread file."""
    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return messages


def cmd_create():
    if not thread_name:
        print(f"{RED}Usage: agents thread create <name>{R}")
        raise SystemExit(1)

    os.makedirs(THREADS_DIR, exist_ok=True)
    path = thread_path(thread_name)

    if os.path.exists(path):
        print(f"{YELLOW}Thread '{thread_name}' already exists.{R}")
        raise SystemExit(1)

    # Create with metadata header
    meta = {
        "type": "thread_meta",
        "name": thread_name,
        "created": datetime.utcnow().isoformat() + "Z",
        "created_by": sender,
    }
    with open(path, "w") as f:
        f.write(json.dumps(meta) + "\n")

    print(f"{GREEN}Thread created: {WHITE}{thread_name}{R}")
    print()
    print(f"  {DIM}File: {path}{R}")
    print()
    print(f"{BOLD}To use in a session:{R}")
    print(f"  Tell the agent:")
    print(f"  {CYAN}\"Watch the thread at {path}")
    print(f"  Check it for messages and post updates there.\"{R}")
    print()
    print(f"{BOLD}Or post from CLI:{R}")
    print(f"  {GREEN}agents thread post {thread_name} \"your message\"{R}")


def cmd_list():
    if not os.path.isdir(THREADS_DIR):
        print(f"{GRAY}No threads yet. Create one: agents thread create <name>{R}")
        return

    threads = []
    for f in os.listdir(THREADS_DIR):
        if f.endswith(".thread"):
            name = f.replace(".thread", "")
            path = os.path.join(THREADS_DIR, f)
            messages = read_thread(path)
            # Filter out meta
            msgs = [m for m in messages if m.get("type") != "thread_meta"]
            mtime = os.path.getmtime(path)
            threads.append((name, len(msgs), mtime, path))

    if not threads:
        print(f"{GRAY}No threads yet. Create one: agents thread create <name>{R}")
        return

    threads.sort(key=lambda x: -x[2])

    print(f"{BOLD}{CYAN}Active Threads{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    for name, msg_count, mtime, path in threads:
        age_str = time_ago(mtime)
        age_color = GREEN if (time.time() - mtime) < 3600 else (
            YELLOW if (time.time() - mtime) < 86400 else GRAY
        )
        print(f"  {WHITE}{name}{R}")
        print(f"    {age_color}{age_str}{R}  {DIM}{msg_count} messages{R}")

    print()
    print(f"{DIM}Usage: agents thread show <name>  |  agents thread post <name> \"msg\"{R}")


def cmd_show():
    if not thread_name:
        print(f"{RED}Usage: agents thread show <name>{R}")
        raise SystemExit(1)

    path = thread_path(thread_name)
    if not os.path.isfile(path):
        print(f"{RED}Thread not found: {thread_name}{R}")
        raise SystemExit(1)

    messages = read_thread(path)

    print(f"{BOLD}{CYAN}Thread: {WHITE}{thread_name}{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"{DIM}File: {path}{R}")
    print()

    msg_count = 0
    for m in messages:
        if m.get("type") == "thread_meta":
            created = m.get("created", "?")
            print(f"  {DIM}Created: {created} by {m.get('created_by', '?')}{R}")
            print()
            continue

        msg_count += 1
        ts = m.get("ts", "")
        sender_id = m.get("from", "unknown")
        text = m.get("msg", "")

        # Parse timestamp for display
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M")
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            time_str = "??:??"
            date_str = ""

        # Color sender by agent type
        if "claude" in sender_id:
            s_color = CYAN
        elif "codex" in sender_id:
            s_color = GREEN
        else:
            s_color = WHITE

        print(f"  {DIM}{time_str}{R}  {s_color}{sender_id}{R}")

        # Word-wrap message
        words = text.split()
        lines = []
        current = ""
        for w in words:
            if len(current) + len(w) + 1 > 60:
                lines.append(current)
                current = w
            else:
                current = f"{current} {w}" if current else w
        if current:
            lines.append(current)

        for line in lines:
            print(f"    {line}")
        print()

    if msg_count == 0:
        print(f"  {GRAY}No messages yet.{R}")
        print()

    print(f"{DIM}{'─' * 52}{R}")
    print(f"{DIM}Post: agents thread post {thread_name} \"message\"{R}")


def cmd_post():
    if not thread_name or not message:
        print(f"{RED}Usage: agents thread post <name> \"message\"{R}")
        raise SystemExit(1)

    path = thread_path(thread_name)
    if not os.path.isfile(path):
        print(f"{RED}Thread not found: {thread_name}{R}")
        print(f"{DIM}Create it first: agents thread create {thread_name}{R}")
        raise SystemExit(1)

    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "from": sender,
        "msg": message,
    }

    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"{GREEN}Posted to {WHITE}{thread_name}{R}")


def cmd_close():
    if not thread_name:
        print(f"{RED}Usage: agents thread close <name>{R}")
        raise SystemExit(1)

    path = thread_path(thread_name)
    if not os.path.isfile(path):
        print(f"{RED}Thread not found: {thread_name}{R}")
        raise SystemExit(1)

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = os.path.join(ARCHIVE_DIR, f"{thread_name}.thread")
    os.rename(path, archive_path)
    print(f"{GREEN}Thread '{thread_name}' archived.{R}")
    print(f"{DIM}Moved to: {archive_path}{R}")


if __name__ == "__main__":
    actions = {
        "create": cmd_create,
        "list": cmd_list,
        "show": cmd_show,
        "post": cmd_post,
        "close": cmd_close,
    }

    handler = actions.get(action)
    if handler:
        handler()
    else:
        print(f"{RED}Unknown action: {action}{R}")
        print(f"{DIM}Actions: create, list, show, post, close{R}")
        raise SystemExit(1)
