#!/usr/bin/env python3
"""
Chronological activity log across all coding agents.
Called by: agents log
Env vars: PERIOD (today/week/month/all), LIMIT (int)
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, BLUE, GRAY, BOLD, DIM, R)

period = os.environ.get("PERIOD", "today")
limit = int(os.environ.get("LIMIT", "30"))

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
now = time.time()

# Period filter
cutoff = {
    "today": now - 86400,
    "week": now - 604800,
    "month": now - 2592000,
    "all": 0,
}.get(period, now - 86400)


def get_first_msg(fpath, agent_name):
    """Get first user message from session file."""
    try:
        with open(fpath) as f:
            for i, line in enumerate(f):
                if i > 50:
                    break
                try:
                    d = json.loads(line)
                    if agent_name == "claude" and d.get("type") == "user":
                        content = d.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            return " ".join(content.split())[:60]
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    return " ".join(item.get("text", "").split())[:60]
                    elif agent_name == "codex" and d.get("type") == "response_item":
                        p = d.get("payload", {})
                        if p.get("role") == "user":
                            for item in p.get("content", []):
                                if isinstance(item, dict):
                                    text = item.get("text", "")
                                    if text and not text.startswith("#") and not text.startswith("<"):
                                        return " ".join(text.split())[:60]
                except (json.JSONDecodeError, KeyError):
                    pass
    except OSError:
        pass
    return ""


def get_session_duration(fpath):
    """Estimate active session duration from timestamps (exclude gaps > 1h)."""
    prev_ts = None
    active = 0
    first_ts = None
    last_ts = None
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    ts_str = d.get("timestamp")
                    if ts_str and isinstance(ts_str, str):
                        ts = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        ).timestamp()
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                        if prev_ts is not None:
                            gap = ts - prev_ts
                            if 0 < gap <= 3600:
                                active += gap
                        prev_ts = ts
                except (json.JSONDecodeError, ValueError, KeyError):
                    pass
    except OSError:
        pass
    return active, first_ts, last_ts


def fmt_duration(s):
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h, m = divmod(s, 3600)
    m = m // 60
    return f"{h}h {m}m" if m else f"{h}h"


def cmd_log():
    # Collect sessions
    entries = []  # (mtime, display_path, fpath, agent_name, session_id)

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            if mtime < cutoff:
                continue

            sid = os.path.basename(fpath).replace(".jsonl", "")
            if adapter.name == "codex":
                try:
                    with open(fpath) as f:
                        first = json.loads(f.readline())
                        if first.get("type") == "session_meta":
                            sid = first.get("payload", {}).get("id", sid)
                except (OSError, json.JSONDecodeError):
                    pass
            entries.append((mtime, display_path, fpath, adapter.name, sid))

    entries.sort(key=lambda x: -x[0])

    if not entries:
        print(f"{GRAY}No sessions found for period: {period}{R}")
        raise SystemExit(0)

    # Group by date
    days = {}
    day_order = []
    for mtime, display_path, fpath, aname, sid in entries[:limit]:
        day = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        if day not in days:
            days[day] = []
            day_order.append(day)
        days[day].append((mtime, display_path, fpath, aname, sid))

    period_label = {
        "today": "Today",
        "week": "This Week",
        "month": "This Month",
        "all": "All Time",
    }.get(period, period)

    print(f"{BOLD}{CYAN}Activity Log{R} {DIM}({period_label}){R}")
    print(f"{DIM}{'─' * 52}{R}")

    total_active = 0
    total_sessions = 0

    for day in day_order:
        day_entries = days[day]
        # Day header
        day_dt = datetime.strptime(day, "%Y-%m-%d")
        weekday = day_dt.strftime("%A")
        is_today = day == datetime.now().strftime("%Y-%m-%d")
        day_label = "Today" if is_today else f"{weekday} {day}"
        print(f"\n{BOLD}{WHITE}{day_label}{R} {DIM}({len(day_entries)} sessions){R}")

        for mtime, display_path, fpath, aname, sid in day_entries:
            total_sessions += 1
            a_color = CYAN if aname == "claude" else GREEN
            time_str = datetime.fromtimestamp(mtime).strftime("%H:%M")

            msg = get_first_msg(fpath, aname)
            if len(msg) > 45:
                msg = msg[:42] + "..."

            # Shorten path
            path_display = display_path
            if len(path_display) > 30:
                path_display = "..." + path_display[-27:]

            active, _, _ = get_session_duration(fpath)
            total_active += active
            dur_str = fmt_duration(active) if active > 0 else ""

            print(f"  {DIM}{time_str}{R}  {a_color}[{aname}]{R} {BLUE}{path_display}{R}", end="")
            if dur_str:
                print(f"  {DIM}{dur_str}{R}", end="")
            print()
            if msg:
                print(f"         {GRAY}\"{msg}\"{R}")

    print()
    print(f"{DIM}{'─' * 52}{R}")
    print(f"{BOLD}{total_sessions}{R} sessions", end="")
    if total_active > 0:
        print(f", {CYAN}{fmt_duration(total_active)}{R} active time")
    else:
        print()


if __name__ == "__main__":
    cmd_log()
