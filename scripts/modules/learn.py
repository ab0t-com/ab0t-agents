#!/usr/bin/env python3
"""
Self-learning: extract patterns, preferences, solutions, and workflows
from session history into a persistent knowledge base.
Called by: agents learn [--show] [--project PATH] [--apply]
Env vars: ACTION (scan/show/apply), PROJECT (path or "all")
"""

import os
import sys
import json
import re
import time
from datetime import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

WHITE = "\033[1;37m"
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
MAGENTA = "\033[0;35m"
GRAY = "\033[0;90m"
RED = "\033[0;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
R = "\033[0m"

KNOWLEDGE_DIR = os.path.expanduser("~/.ab0t/.agents/knowledge")
action = os.environ.get("ACTION", "scan")
project_filter = os.environ.get("PROJECT", "all")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
available = [a for a in ALL_ADAPTERS if a.is_available()]


def load_knowledge():
    kfile = os.path.join(KNOWLEDGE_DIR, "knowledge.json")
    try:
        with open(kfile) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "preferences": [],
            "patterns": [],
            "solutions": [],
            "tools_and_libs": Counter(),
            "anti_patterns": [],
            "scanned_sessions": [],
            "last_scan": None,
        }


def save_knowledge(k):
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    kfile = os.path.join(KNOWLEDGE_DIR, "knowledge.json")
    # Counter isn't JSON serializable
    kc = dict(k)
    if isinstance(kc.get("tools_and_libs"), Counter):
        kc["tools_and_libs"] = dict(kc["tools_and_libs"])
    with open(kfile, "w") as f:
        json.dump(kc, f, indent=2)


def extract_user_text_claude(data):
    content = data.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


def extract_assistant_tools_claude(data):
    """Extract tool usage from assistant messages."""
    tools = []
    content = data.get("message", {}).get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                tools.append({
                    "name": item.get("name", ""),
                    "input": item.get("input", {}),
                })
    return tools


# Patterns we look for in user messages
PREFERENCE_PATTERNS = [
    (r"\b(always|never|prefer|don't|dont|please|make sure)\b.*\b(use|using|with)\b\s+(\w+)",
     "explicit_preference"),
    (r"\b(use|switch to|install|setup)\b\s+(pytest|jest|vitest|mocha|bun|pnpm|npm|yarn|poetry|pip|cargo)\b",
     "tool_preference"),
    (r"\b(don't|dont|never|stop|no)\b.*\b(inline|hardcode|commit|push|delete|remove)\b",
     "anti_preference"),
]

# Patterns for solution extraction (from user describing a fix)
SOLUTION_PATTERNS = [
    (r"(fix|fixed|solved|solution|the issue was|the problem was|turns out)",
     "solution_mention"),
]

# Libraries and tools to track
TOOL_PATTERNS = re.compile(
    r"\b(pytest|jest|vitest|mocha|eslint|prettier|black|ruff|mypy|"
    r"docker|kubernetes|terraform|ansible|"
    r"react|vue|angular|svelte|next|nuxt|"
    r"fastapi|flask|django|express|"
    r"postgres|mysql|redis|mongodb|sqlite|"
    r"pnpm|npm|yarn|bun|pip|poetry|cargo|go)\b",
    re.IGNORECASE,
)


def scan_session(fpath, agent_name, project):
    """Scan a session and extract knowledge signals."""
    signals = {
        "preferences": [],
        "tools": Counter(),
        "solutions": [],
        "commands_used": Counter(),
    }

    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)

                    if agent_name == "claude":
                        if d.get("type") == "user":
                            text = extract_user_text_claude(d)
                            if not text:
                                continue

                            # Check preference patterns
                            for pattern, ptype in PREFERENCE_PATTERNS:
                                m = re.search(pattern, text, re.IGNORECASE)
                                if m:
                                    snippet = text[max(0, m.start()-20):m.end()+20].strip()
                                    signals["preferences"].append({
                                        "type": ptype,
                                        "text": " ".join(snippet.split())[:100],
                                        "project": project,
                                    })

                            # Check solution patterns
                            for pattern, stype in SOLUTION_PATTERNS:
                                m = re.search(pattern, text, re.IGNORECASE)
                                if m:
                                    snippet = text[max(0, m.start()-30):min(len(text), m.end()+100)].strip()
                                    signals["solutions"].append({
                                        "type": stype,
                                        "text": " ".join(snippet.split())[:150],
                                        "project": project,
                                    })

                            # Track tools mentioned
                            for m in TOOL_PATTERNS.finditer(text):
                                signals["tools"][m.group().lower()] += 1

                        elif d.get("type") == "assistant":
                            tools = extract_assistant_tools_claude(d)
                            for t in tools:
                                if t["name"] == "Bash":
                                    cmd = t["input"].get("command", "")
                                    # Extract the base command
                                    base = cmd.strip().split()[0] if cmd.strip() else ""
                                    if base:
                                        signals["commands_used"][base] += 1
                                    # Track tools from commands
                                    for m in TOOL_PATTERNS.finditer(cmd):
                                        signals["tools"][m.group().lower()] += 1

                    elif agent_name == "codex":
                        if d.get("type") == "response_item":
                            item = d.get("item", {})
                            if item.get("role") == "user":
                                content = item.get("content", [])
                                text = ""
                                if isinstance(content, list):
                                    text = " ".join(
                                        c.get("text", "") for c in content if isinstance(c, dict)
                                    )
                                if text:
                                    for m in TOOL_PATTERNS.finditer(text):
                                        signals["tools"][m.group().lower()] += 1

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    return signals


def cmd_scan():
    """Scan all sessions and extract knowledge."""
    knowledge = load_knowledge()
    scanned = set(knowledge.get("scanned_sessions", []))
    tools_counter = Counter(knowledge.get("tools_and_libs", {}))

    new_sessions = 0
    total_signals = 0

    print(f"{BOLD}{CYAN}Learning from sessions...{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    for adapter in available:
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            if fpath in scanned:
                continue
            if project_filter != "all" and not display_path.startswith(project_filter):
                continue

            signals = scan_session(fpath, adapter.name, display_path)
            scanned.add(fpath)
            new_sessions += 1

            # Merge signals
            knowledge["preferences"].extend(signals["preferences"])
            knowledge["solutions"].extend(signals["solutions"])
            tools_counter.update(signals["tools"])
            total_signals += len(signals["preferences"]) + len(signals["solutions"])

    knowledge["scanned_sessions"] = list(scanned)
    knowledge["tools_and_libs"] = tools_counter
    knowledge["last_scan"] = datetime.utcnow().isoformat() + "Z"
    save_knowledge(knowledge)

    print(f"  {WHITE}Sessions scanned:{R}  {new_sessions} new ({len(scanned)} total)")
    print(f"  {WHITE}Preferences:{R}       {len(knowledge['preferences'])}")
    print(f"  {WHITE}Solutions:{R}          {len(knowledge['solutions'])}")
    print(f"  {WHITE}Tools tracked:{R}      {len(tools_counter)}")
    print()

    # Show top tools
    if tools_counter:
        print(f"{BOLD}  Top Tools & Libraries:{R}")
        for tool, count in tools_counter.most_common(10):
            bar_len = min(20, count)
            bar = "█" * bar_len
            print(f"    {MAGENTA}{tool:20s}{R} {DIM}{bar}{R} {WHITE}{count}{R}")
        print()

    # Show recent preferences
    if knowledge["preferences"]:
        print(f"{BOLD}  Recent Preferences:{R}")
        for pref in knowledge["preferences"][-5:]:
            print(f"    {YELLOW}{pref['type']:20s}{R} {GRAY}\"{pref['text']}\"{R}")
        print()

    # Show recent solutions
    if knowledge["solutions"]:
        print(f"{BOLD}  Recent Solutions:{R}")
        for sol in knowledge["solutions"][-5:]:
            print(f"    {GREEN}{sol['type']:20s}{R} {GRAY}\"{sol['text']}\"{R}")


def cmd_show():
    """Display current knowledge base."""
    knowledge = load_knowledge()

    print(f"{BOLD}{CYAN}Knowledge Base{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    scanned = knowledge.get("scanned_sessions", [])
    last_scan = knowledge.get("last_scan", "never")
    print(f"  {WHITE}Sessions scanned:{R} {len(scanned)}")
    print(f"  {WHITE}Last scan:{R}        {last_scan}")
    print()

    prefs = knowledge.get("preferences", [])
    if prefs:
        print(f"{BOLD}  Preferences ({len(prefs)}):{R}")
        for p in prefs[-10:]:
            print(f"    {YELLOW}[{p['type']}]{R} {GRAY}{p['text']}{R}")
        if len(prefs) > 10:
            print(f"    {DIM}... and {len(prefs) - 10} more{R}")
        print()

    solutions = knowledge.get("solutions", [])
    if solutions:
        print(f"{BOLD}  Solutions ({len(solutions)}):{R}")
        for s in solutions[-10:]:
            print(f"    {GREEN}[{s['type']}]{R} {GRAY}{s['text']}{R}")
        if len(solutions) > 10:
            print(f"    {DIM}... and {len(solutions) - 10} more{R}")
        print()

    tools = knowledge.get("tools_and_libs", {})
    if tools:
        counter = Counter(tools)
        print(f"{BOLD}  Tools & Libraries ({len(counter)}):{R}")
        for tool, count in counter.most_common(15):
            print(f"    {MAGENTA}{tool:20s}{R} {DIM}×{count}{R}")
        print()

    if not prefs and not solutions and not tools:
        print(f"  {GRAY}Knowledge base is empty. Run 'agents learn' to scan sessions.{R}")


def cmd_apply():
    """Generate a CLAUDE.md snippet from learned knowledge."""
    knowledge = load_knowledge()
    tools = Counter(knowledge.get("tools_and_libs", {}))
    prefs = knowledge.get("preferences", [])

    lines = []
    lines.append("# Learned Preferences")
    lines.append("")
    lines.append("Auto-generated by `agents learn --apply`. Review before using.")
    lines.append("")

    if tools:
        lines.append("## Tools & Stack")
        for tool, count in tools.most_common(10):
            if count >= 3:
                lines.append(f"- Frequently uses: {tool}")
        lines.append("")

    if prefs:
        lines.append("## Preferences")
        seen = set()
        for p in prefs:
            key = p["text"][:50]
            if key not in seen:
                seen.add(key)
                lines.append(f"- {p['text']}")
        lines.append("")

    result = "\n".join(lines)
    print(result)
    print()
    print(f"{DIM}Paste the above into your CLAUDE.md or save with:{R}")
    print(f"{DIM}  agents learn --apply > learned-preferences.md{R}")


# Dispatch
if action == "show":
    cmd_show()
elif action == "apply":
    cmd_apply()
else:
    cmd_scan()
