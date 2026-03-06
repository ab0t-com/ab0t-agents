#!/usr/bin/env python3
"""
Watchdog - monitor session files for real-time activity.
Called by: agents watch [--interval N]
Env vars: ACTION (watch/status), INTERVAL (seconds, default 5), PROJECT (path)
"""

import os
import sys
import json
import time
import signal
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   human_size)

# Clear line ANSI
CLEAR_LINE = "\033[2K\r"

action = os.environ.get("ACTION", "watch")
interval = int(os.environ.get("INTERVAL", "5"))
project_filter = os.environ.get("PROJECT", "")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]

# Graceful exit
running = True


def handle_signal(sig, frame):
    global running
    running = False
    print(f"\n{DIM}Stopped watching.{R}")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def time_ago(ts):
    s = int(time.time() - ts)
    if s < 5:
        return f"{GREEN}just now{R}"
    if s < 60:
        return f"{GREEN}{s}s ago{R}"
    if s < 300:
        return f"{YELLOW}{s // 60}m {s % 60}s ago{R}"
    if s < 3600:
        return f"{GRAY}{s // 60}m ago{R}"
    if s < 86400:
        return f"{GRAY}{s // 3600}h ago{R}"
    return f"{GRAY}{s // 86400}d ago{R}"


def get_session_size(fpath):
    try:
        return human_size(os.path.getsize(fpath))
    except OSError:
        return "?"


def get_last_record_type(fpath):
    """Read the last line of a session file to determine activity."""
    try:
        with open(fpath, "rb") as f:
            # Seek to end, find last newline
            f.seek(0, 2)
            pos = f.tell()
            if pos == 0:
                return "empty"
            # Read backwards to find last complete line
            pos -= 1
            while pos > 0:
                f.seek(pos)
                if f.read(1) == b'\n':
                    break
                pos -= 1
            last_line = f.readline().decode("utf-8", errors="replace").strip()
            if last_line:
                try:
                    d = json.loads(last_line)
                    return d.get("type", "unknown")
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return "unknown"


def discover_active_sessions():
    """Find sessions that have been modified recently."""
    now = time.time()
    active = []

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            if project_filter and not display_path.startswith(project_filter):
                continue

            age = now - mtime
            # Only show sessions active in last 24h
            if age > 86400:
                continue

            sid = os.path.basename(fpath).replace(".jsonl", "")
            active.append({
                "session_id": sid,
                "agent": adapter.name,
                "project": display_path,
                "fpath": fpath,
                "mtime": mtime,
                "age": age,
            })

    active.sort(key=lambda s: -s["mtime"])
    return active


def cmd_watch():
    """Watch session files for real-time changes."""
    print(f"{BOLD}{CYAN}Watching Sessions{R} {DIM}(Ctrl+C to stop, interval: {interval}s){R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    # Track previous state
    prev_state = {}  # fpath -> (mtime, size)
    iteration = 0

    while running:
        now = time.time()
        active = discover_active_sessions()

        if not active:
            if iteration == 0:
                print(f"  {GRAY}No active sessions in the last 24h.{R}")
                print(f"  {DIM}Start a session with claude or codex to see activity.{R}")
            time.sleep(interval)
            iteration += 1
            continue

        # Detect changes
        changes = []
        for s in active:
            fpath = s["fpath"]
            try:
                current_mtime = os.path.getmtime(fpath)
                current_size = os.path.getsize(fpath)
            except OSError:
                continue

            prev = prev_state.get(fpath)
            if prev:
                prev_mtime, prev_size = prev
                if current_mtime > prev_mtime:
                    size_delta = current_size - prev_size
                    last_type = get_last_record_type(fpath)
                    changes.append({
                        **s,
                        "size_delta": size_delta,
                        "last_type": last_type,
                    })

            prev_state[fpath] = (current_mtime, current_size)

        # Print changes as they happen
        if changes:
            ts_str = datetime.now().strftime("%H:%M:%S")
            for c in changes:
                a_color = CYAN if c["agent"] == "claude" else GREEN
                sid = c["session_id"][:8]
                delta_str = f"+{c['size_delta']:,}" if c["size_delta"] >= 0 else f"{c['size_delta']:,}"
                rec_type = c["last_type"]

                # Color by record type
                if rec_type == "assistant":
                    type_color = MAGENTA
                    type_label = "response"
                elif rec_type == "user":
                    type_color = WHITE
                    type_label = "message"
                elif rec_type == "tool_result":
                    type_color = YELLOW
                    type_label = "tool result"
                elif "system" in rec_type:
                    type_color = GRAY
                    type_label = "system"
                else:
                    type_color = GRAY
                    type_label = rec_type

                short_project = os.path.basename(c["project"]) if c["project"] else "?"

                print(f"  {DIM}{ts_str}{R}  {a_color}[{c['agent']}]{R} "
                      f"{WHITE}{sid}{R}  "
                      f"{type_color}{type_label}{R}  "
                      f"{DIM}{delta_str} bytes{R}  "
                      f"{BLUE}{short_project}{R}")

        # On first run or every 12th iteration, show status summary
        if iteration == 0 or (iteration % 12 == 0 and not changes):
            if iteration > 0:
                print()
            ts_str = datetime.now().strftime("%H:%M:%S")
            print(f"  {DIM}{ts_str}  Watching {len(active)} session{'s' if len(active) != 1 else ''}...{R}")
            for s in active[:5]:
                a_color = CYAN if s["agent"] == "claude" else GREEN
                age_str = time_ago(s["mtime"])
                size_str = get_session_size(s["fpath"])
                state = f"{GREEN}active{R}" if s["age"] < 300 else (
                    f"{YELLOW}idle{R}" if s["age"] < 3600 else f"{GRAY}quiet{R}"
                )
                print(f"    {a_color}[{s['agent']}]{R} {WHITE}{s['session_id'][:8]}{R}  "
                      f"{state}  {age_str}  {DIM}{size_str}{R}")
            if len(active) > 5:
                print(f"    {DIM}... and {len(active) - 5} more{R}")
            print()

        time.sleep(interval)
        iteration += 1


def cmd_status():
    """Show current session activity snapshot (non-blocking)."""
    now = time.time()
    active = discover_active_sessions()

    print(f"{BOLD}{CYAN}Session Activity{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    if not active:
        print(f"  {GRAY}No active sessions in the last 24h.{R}")
        return

    # Group by status
    live = [s for s in active if s["age"] < 300]      # < 5 min
    idle = [s for s in active if 300 <= s["age"] < 3600]  # 5min - 1h
    quiet = [s for s in active if s["age"] >= 3600]    # > 1h

    if live:
        print(f"  {GREEN}{BOLD}Active ({len(live)}):{R}")
        for s in live:
            a_color = CYAN if s["agent"] == "claude" else GREEN
            age_str = time_ago(s["mtime"])
            size_str = get_session_size(s["fpath"])
            short_proj = os.path.basename(s["project"]) if s["project"] else "?"
            print(f"    {a_color}[{s['agent']}]{R} {WHITE}{s['session_id'][:8]}{R}  "
                  f"{age_str}  {DIM}{size_str}{R}  {BLUE}{short_proj}{R}")
        print()

    if idle:
        print(f"  {YELLOW}{BOLD}Idle ({len(idle)}):{R}")
        for s in idle[:5]:
            a_color = CYAN if s["agent"] == "claude" else GREEN
            age_str = time_ago(s["mtime"])
            short_proj = os.path.basename(s["project"]) if s["project"] else "?"
            print(f"    {a_color}[{s['agent']}]{R} {WHITE}{s['session_id'][:8]}{R}  "
                  f"{age_str}  {BLUE}{short_proj}{R}")
        if len(idle) > 5:
            print(f"    {DIM}... and {len(idle) - 5} more{R}")
        print()

    if quiet:
        print(f"  {GRAY}{BOLD}Quiet ({len(quiet)}):{R}")
        for s in quiet[:3]:
            a_color = CYAN if s["agent"] == "claude" else GREEN
            age_str = time_ago(s["mtime"])
            short_proj = os.path.basename(s["project"]) if s["project"] else "?"
            print(f"    {a_color}[{s['agent']}]{R} {WHITE}{s['session_id'][:8]}{R}  "
                  f"{age_str}  {BLUE}{short_proj}{R}")
        if len(quiet) > 3:
            print(f"    {DIM}... and {len(quiet) - 3} more{R}")
        print()

    print(f"{DIM}Live watch: agents watch{R}")


if __name__ == "__main__":
    actions = {
        "watch": cmd_watch,
        "status": cmd_status,
    }

    handler = actions.get(action)
    if handler:
        handler()
    else:
        print(f"{RED}Unknown action: {action}{R}")
        raise SystemExit(1)
