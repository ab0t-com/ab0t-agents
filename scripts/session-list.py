#!/usr/bin/env python3
"""
List all projects across all coding agents, sorted by recency.
Called by: agents list
Env vars: SHOW_ALL (true/false), LIMIT (int)

Writes projects_cache.json for use by show/resume.
Maintains stable letter IDs in project_letters.json so projects
keep the same ID even when recency order changes.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

show_all = os.environ.get("SHOW_ALL", "false") == "true"
limit = int(os.environ.get("LIMIT", "10"))

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
LETTERS_FILE = os.path.join(CACHE_DIR, "project_letters.json")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]
available = [a for a in ALL_ADAPTERS if a.is_available()]

if not available:
    print("No coding agent data found.")
    raise SystemExit(1)

# Collect all projects: (path, count, latest_mtime, agent_name)
projects = []
for adapter in available:
    for path, count, latest in adapter.list_projects():
        projects.append((path, count, latest, adapter.name))

# Merge projects at the same path across agents
merged = {}  # path -> {count, latest, agents: [name,...]}
for path, count, latest, aname in projects:
    if path in merged:
        m = merged[path]
        m["count"] += count
        m["latest"] = max(m["latest"], latest)
        if aname not in m["agents"]:
            m["agents"].append(aname)
    else:
        merged[path] = {"count": count, "latest": latest, "agents": [aname]}

# Sort by recency
sorted_projects = sorted(merged.items(), key=lambda x: -x[1]["latest"])


def time_ago(ts):
    s = int(time.time() - ts)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    if s < 604800:
        return f"{s // 86400}d ago"
    return f"{s // 604800}w ago"


# --- Stable letter IDs ---
# Load existing path->letter mapping
def load_letters():
    try:
        with open(LETTERS_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_letters(mapping):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(LETTERS_FILE, "w") as f:
        json.dump(mapping, f)


def next_letter(used):
    """Generate next available letter: a-z, then aa-az, ba-bz, etc."""
    for i in range(702):  # a-z (26) + aa-zz (676)
        if i < 26:
            letter = chr(ord("a") + i)
        else:
            j = i - 26
            letter = chr(ord("a") + j // 26) + chr(ord("a") + j % 26)
        if letter not in used:
            return letter
    return "?"


letters = load_letters()  # path -> letter
used_letters = set(letters.values())

# Assign letters to any new projects
for path, info in sorted_projects:
    if path not in letters:
        letter = next_letter(used_letters)
        letters[path] = letter
        used_letters.add(letter)

save_letters(letters)


AGENT_COLORS = {}
for a in ALL_ADAPTERS:
    AGENT_COLORS[a.name] = a.color

print(f"{BOLD}{CYAN}Coding Agent Projects{R}")
print(f"{DIM}{'─' * 52}{R}")
print()

# For cache: list of {path, agents, letter} in display order
cache_list = []

idx = 0
for path, info in sorted_projects:
    idx += 1
    if not show_all and idx > limit:
        break

    count = info["count"]
    latest = info["latest"]
    agents = info["agents"]
    letter = letters.get(path, "?")

    cache_list.append({"path": path, "agents": agents, "letter": letter})

    age_str = time_ago(latest)
    age = time.time() - latest
    time_color = GRAY
    if age < 3600:
        time_color = GREEN
    elif age < 86400:
        time_color = YELLOW

    # Agent badges
    badges = " ".join(f"{AGENT_COLORS.get(a, GRAY)}[{a}]{R}" for a in agents)

    print(f"{BOLD}{WHITE}[{letter:>2s}]{R} {YELLOW}{path}{R}")
    print(f"     {time_color}{age_str:<10}{R} {DIM}sessions: {count}{R}  {badges}")

print()
print(f"{DIM}Usage: agents show <letter>  or  agents show <path>{R}")
print(f"{DIM}       agents go <letter> [agent]  # resume last session (default: claude){R}")
print(f"{DIM}       agents show <num> also works (by position){R}")
print(f"{DIM}       agents list -a     (show all projects){R}")

# Save cache
os.makedirs(CACHE_DIR, exist_ok=True)
with open(os.path.join(CACHE_DIR, "projects_cache.json"), "w") as f:
    json.dump(cache_list, f)
