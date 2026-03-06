#!/usr/bin/env python3
"""
Generate Claude Code usage statistics dashboard.
Called by: agents stats
Env vars: PROJECTS_DIR, TOTAL_SIZE, TOTAL_STARTUPS

Uses adapter system to aggregate stats from multiple coding agents.
Caches per-session stats in ~/.ab0t/.agents/stats_cache.json.
"""

import os
import sys
import json
import time
from datetime import datetime
from collections import defaultdict

# Add parent scripts dir to path for adapter imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

total_size = os.environ.get("TOTAL_SIZE", "?")
total_startups = os.environ.get("TOTAL_STARTUPS", "0")

# ANSI colors
WHITE = "\033[1;37m"
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
MAGENTA = "\033[0;35m"
BLUE = "\033[0;34m"
GRAY = "\033[0;90m"
RED = "\033[0;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
R = "\033[0m"

CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")
CACHE_FILE = os.path.join(CACHE_DIR, "stats_cache.json")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]


# --- Cache ---

def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except OSError:
        pass


# --- Helpers ---

def decode_path(encoded):
    """Simple decode for Claude project dir names."""
    if encoded.startswith("/"):
        return encoded
    if encoded.startswith("-"):
        return "/" + encoded[1:].replace("-", "/")
    return "/" + encoded.replace("-", "/")


def get_first_msg(fpath):
    """Get first user message from a Claude session file."""
    try:
        with open(fpath) as f:
            for i, line in enumerate(f):
                if i > 50:
                    break
                try:
                    d = json.loads(line)
                    if d.get("type") == "user":
                        content = d.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            return " ".join(content.split())[:60]
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    return " ".join(item.get("text", "").split())[:60]
                    # Codex format
                    elif d.get("type") == "response_item":
                        p = d.get("payload", {})
                        if p.get("role") == "user":
                            for item in p.get("content", []):
                                if isinstance(item, dict):
                                    text = item.get("text", "")
                                    if text and not text.startswith("#"):
                                        return " ".join(text.split())[:60]
                except (json.JSONDecodeError, KeyError):
                    pass
    except OSError:
        pass
    return ""


def fmt_tokens(n):
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_duration(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    parts = []
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    mins, s = divmod(s, 60)
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")
    return " ".join(parts) if parts else "0m"


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


# --- Main scan ---

now = time.time()
day_ago = now - 86400
week_ago = now - 604800
month_ago = now - 2592000

cache = load_cache()
new_cache = {}

total_sessions = 0
total_agents = 0
sessions_today = 0
sessions_week = 0
sessions_month = 0
total_input = 0
total_output = 0
total_cache_read = 0
total_cache_create = 0
total_session_duration = 0
total_turn_duration = 0
earliest_ts = None
models = defaultdict(int)
project_stats = {}  # display_path -> (session_count, latest_mtime, agent_name)
recent = []  # (mtime, display_path, fpath, agent_name)

# Per-agent counts
agent_counts = {}  # adapter.name -> {"sessions": n, "subagents": n}

available_adapters = [a for a in ALL_ADAPTERS if a.is_available()]

if not available_adapters:
    print("No coding agent data found.")
    raise SystemExit(1)

for adapter in available_adapters:
    a_sessions = 0
    a_subagents = 0

    for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
        if is_agent:
            total_agents += 1
            a_subagents += 1
            continue

        total_sessions += 1
        a_sessions += 1

        if mtime > day_ago:
            sessions_today += 1
        if mtime > week_ago:
            sessions_week += 1
        if mtime > month_ago:
            sessions_month += 1

        recent.append((mtime, display_path, fpath, adapter.name))

        # Per-project aggregation
        proj_key = f"{adapter.name}:{display_path}"
        if proj_key in project_stats:
            count, latest, aname = project_stats[proj_key]
            project_stats[proj_key] = (count + 1, max(latest, mtime), aname)
        else:
            project_stats[proj_key] = (1, mtime, adapter.name)

        # Check cache: use cached stats if mtime matches
        cache_key = fpath
        cached = cache.get(cache_key)
        if cached and cached.get("mtime") == mtime:
            stats = cached
        else:
            stats = adapter.parse_session_stats(fpath)
            stats["mtime"] = mtime
        new_cache[cache_key] = stats

        # Aggregate
        total_input += stats.get("input", 0)
        total_output += stats.get("output", 0)
        total_cache_read += stats.get("cache_read", 0)
        total_cache_create += stats.get("cache_create", 0)
        total_turn_duration += stats.get("turn_duration_ms", 0)
        total_session_duration += stats.get("session_active_s", 0)
        for model, count in stats.get("models", {}).items():
            models[model] += count
        e = stats.get("earliest")
        if e is not None and (earliest_ts is None or e < earliest_ts):
            earliest_ts = e

    agent_counts[adapter.name] = {"sessions": a_sessions, "subagents": a_subagents}

save_cache(new_cache)

# Count unique project paths across all adapters
unique_projects = set()
for key in project_stats:
    # key is "adapter:path", extract path
    path = key.split(":", 1)[1] if ":" in key else key
    unique_projects.add(path)
total_projects = len(unique_projects)


# --- Render ---

sep = f"{DIM}{'─' * 52}{R}"

print(f"{BOLD}{CYAN}Coding Agent Statistics{R}")
print(sep)

# Agents detected
agent_labels = []
for adapter in available_adapters:
    ac = agent_counts.get(adapter.name, {})
    s = ac.get("sessions", 0)
    agent_labels.append(f"{adapter.color}{adapter.name}{R}({s})")
print(f"\n  {DIM}Agents:{R} {', '.join(agent_labels)}")

# Overview
print(f"\n{BOLD} Overview{R}")
print(f"  {WHITE}Projects:{R}   {total_projects:<10} {WHITE}Sessions:{R}  {total_sessions}")
print(f"  {WHITE}Subagents:{R} {total_agents:<10} {WHITE}Size:{R}      {total_size}")
if total_startups != "0":
    print(f"  {WHITE}Startups:{R}  {total_startups}")
if earliest_ts is not None:
    since_str = datetime.fromtimestamp(earliest_ts).strftime("%Y-%m-%d")
    print(f"  {DIM}(since {since_str}){R}")

# Activity
print(f"\n{BOLD} Activity{R}")
print(
    f"  {GREEN}Today:{R}     {sessions_today:<10} "
    f"{YELLOW}This week:{R} {sessions_week:<10} "
    f"{GRAY}This month:{R} {sessions_month}"
)

# Time
if total_session_duration > 0 or total_turn_duration > 0:
    print(f"\n{BOLD} Time{R}")
    print(
        f"  {WHITE}Session time:{R} {CYAN}{fmt_duration(total_session_duration):<12}{R} "
        f"{DIM}(excludes gaps > 1h){R}"
    )
    if total_turn_duration > 0:
        turn_secs = total_turn_duration / 1000
        print(
            f"  {WHITE}Active time:{R}  {CYAN}{fmt_duration(turn_secs):<12}{R} "
            f"{DIM}(time agents spent responding){R}"
        )
    if total_sessions > 0:
        avg = total_session_duration / total_sessions
        print(f"  {WHITE}Avg session:{R} {CYAN}{fmt_duration(avg)}{R}")

# Token usage
total_input_all = total_input + total_cache_read + total_cache_create
if total_input_all > 0 or total_output > 0:
    total_tokens = total_input_all + total_output
    print(f"\n{BOLD} Token Usage{R}")
    print(
        f"  {WHITE}Input:{R}     {fmt_tokens(total_input_all):<10} "
        f"{WHITE}Output:{R}    {fmt_tokens(total_output):<10} "
        f"{WHITE}Total:{R} {fmt_tokens(total_tokens)}"
    )
    if total_input_all > 0:
        cache_rate = total_cache_read / total_input_all * 100
        color = GREEN if cache_rate > 50 else (YELLOW if cache_rate > 20 else RED)
        print(
            f"  {WHITE}Cache hit:{R} {color}{cache_rate:.0f}%{R}       "
            f"{DIM}({fmt_tokens(total_cache_read)} read, {fmt_tokens(total_cache_create)} created, {fmt_tokens(total_input)} uncached){R}"
        )
        print(
            f"  {WHITE}Cache:{R}     {fmt_tokens(total_cache_read):<10} "
            f"{WHITE}Created:{R}  {fmt_tokens(total_cache_create):<10} "
            f"{WHITE}Uncached:{R} {fmt_tokens(total_input)}"
        )

# Models
if models:
    print(f"\n{BOLD} Models{R}")
    total_calls = sum(models.values())
    for model, count in sorted(models.items(), key=lambda x: -x[1])[:6]:
        pct = count / total_calls * 100
        bar_len = int(pct / 5)
        bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
        short = model.replace("claude-", "").replace("-20251101", "").replace("-20250929", "").replace("-20251001", "")
        print(f"  {MAGENTA}{short:20s}{R} {DIM}{bar}{R} {WHITE}{count:>5}{R} {DIM}({pct:.0f}%){R}")

# Top projects
if project_stats:
    print(f"\n{BOLD} Top Projects{R}")
    top = sorted(project_stats.items(), key=lambda x: -x[1][0])[:5]
    for proj_key, (count, latest, aname) in top:
        display = proj_key.split(":", 1)[1] if ":" in proj_key else proj_key
        if len(display) > 30:
            display = "..." + display[-27:]
        age_str = time_ago(latest)
        age_color = GREEN if (now - latest) < 86400 else (YELLOW if (now - latest) < 604800 else GRAY)
        plural = "s" if count != 1 else " "
        # Find adapter for color
        a_color = GRAY
        for a in available_adapters:
            if a.name == aname:
                a_color = a.color
                break
        badge = f"{a_color}[{aname}]{R}"
        print(f"  {badge} {YELLOW}{display:33s}{R} {WHITE}{count:>3}{R} session{plural} {age_color}{age_str}{R}")

# Recent sessions
recent.sort(key=lambda x: -x[0])
if recent:
    print(f"\n{BOLD} Recent Sessions{R}")
    shown = 0
    for mtime, display_path, fpath, aname in recent:
        if shown >= 5:
            break
        display = display_path
        if len(display) > 22:
            display = "..." + display[-19:]
        age_str = time_ago(mtime)
        age_color = GREEN if (now - mtime) < 3600 else (YELLOW if (now - mtime) < 86400 else GRAY)
        # Agent badge
        a_color = GRAY
        for a in available_adapters:
            if a.name == aname:
                a_color = a.color
                break
        badge = f"{a_color}[{aname}]{R}"
        msg = get_first_msg(fpath)
        if len(msg) > 35:
            msg = msg[:32] + "..."
        if msg:
            print(f"  {age_color}{age_str:>8}{R} {badge} {BLUE}{display:22s}{R}  {GRAY}\"{msg}\"{R}")
        else:
            print(f"  {age_color}{age_str:>8}{R} {badge} {BLUE}{display:22s}{R}")
        shown += 1

print()
