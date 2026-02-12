#!/usr/bin/env python3
"""
Blend context from multiple sessions into a synthesized context document.
Called by: agents blend <session1> <session2> [--mode full|summary|artifacts]
Env vars: SESSIONS (comma-separated keys), MODE (full/summary/artifacts)
"""

import os
import sys
import json
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
BLENDS_DIR = os.path.join(CACHE_DIR, "blends")

sessions_str = os.environ.get("SESSIONS", "")
mode = os.environ.get("MODE", "summary")

if not sessions_str:
    print(f"{RED}Usage: agents blend <session1> <session2> [--mode full|summary|artifacts]{R}")
    raise SystemExit(1)

session_keys = [s.strip() for s in sessions_str.split(",") if s.strip()]


def resolve_session(key):
    cache_file = os.path.join(CACHE_DIR, "sessions_cache.json")
    if key.isdigit() and os.path.isfile(cache_file):
        try:
            with open(cache_file) as f:
                sessions = json.load(f)
            idx = int(key) - 1
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
            if basename.startswith(key) or key in basename:
                return fpath, adapter.name, display
    return "", "", ""


def extract_session_context(fpath, agent_name):
    """Extract key context from a session: messages, file edits, decisions."""
    context = {
        "messages": [],
        "files_touched": set(),
        "commands": [],
        "first_message": "",
        "message_count": 0,
    }

    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)

                    if agent_name == "claude":
                        if d.get("type") == "user":
                            content = d.get("message", {}).get("content", "")
                            text = ""
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                text = " ".join(
                                    item.get("text", "")
                                    for item in content
                                    if isinstance(item, dict) and item.get("type") == "text"
                                )
                            if text:
                                context["messages"].append({"role": "user", "text": text})
                                context["message_count"] += 1
                                if not context["first_message"]:
                                    context["first_message"] = " ".join(text.split())[:80]

                        elif d.get("type") == "assistant":
                            msg = d.get("message", {})
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict):
                                        if item.get("type") == "text":
                                            context["messages"].append({
                                                "role": "assistant",
                                                "text": item.get("text", "")
                                            })
                                            context["message_count"] += 1
                                        elif item.get("type") == "tool_use":
                                            name = item.get("name", "")
                                            inp = item.get("input", {})
                                            if name in ("Write", "Edit"):
                                                context["files_touched"].add(inp.get("file_path", ""))
                                            elif name == "Bash":
                                                context["commands"].append(inp.get("command", ""))

                    elif agent_name == "codex":
                        if d.get("type") == "response_item":
                            item = d.get("item", {})
                            role = item.get("role", "")
                            content = item.get("content", [])
                            text = ""
                            if isinstance(content, list):
                                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                            if text and role in ("user", "assistant"):
                                context["messages"].append({"role": role, "text": text})
                                context["message_count"] += 1
                                if role == "user" and not context["first_message"]:
                                    context["first_message"] = " ".join(text.split())[:80]

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    context["files_touched"] = list(context["files_touched"])
    return context


# Resolve all sessions
resolved = []
for key in session_keys:
    fpath, agent_name, project = resolve_session(key)
    if not fpath:
        print(f"{RED}Could not find session: {key}{R}")
        continue
    resolved.append({
        "key": key,
        "fpath": fpath,
        "agent": agent_name,
        "project": project,
        "session_id": os.path.basename(fpath).replace(".jsonl", ""),
    })

if len(resolved) < 2:
    print(f"{RED}Need at least 2 valid sessions to blend.{R}")
    raise SystemExit(1)

print(f"{BOLD}{CYAN}Blending Sessions{R}")
print(f"{DIM}{'─' * 52}{R}")

# Extract context from each
contexts = []
for r in resolved:
    ctx = extract_session_context(r["fpath"], r["agent"])
    contexts.append(ctx)
    a_color = CYAN if r["agent"] == "claude" else GREEN
    badge = f"{a_color}[{r['agent']}]{R}"
    print(f"  {badge} {WHITE}{r['session_id'][:8]}{R}  {DIM}{ctx['message_count']} messages, {len(ctx['files_touched'])} files{R}")
    if ctx["first_message"]:
        print(f"    {GRAY}\"{ctx['first_message']}\"{R}")

print()

# Build blended document
blend_lines = []
blend_lines.append("# Blended Session Context")
blend_lines.append("")
blend_lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
blend_lines.append(f"Mode: {mode}")
blend_lines.append(f"Sources: {len(resolved)} sessions")
blend_lines.append("")

for i, (r, ctx) in enumerate(zip(resolved, contexts)):
    blend_lines.append(f"## Source {i+1}: {r['agent']} session {r['session_id'][:8]}")
    if r["project"]:
        blend_lines.append(f"Project: {r['project']}")
    blend_lines.append("")

    if mode == "artifacts":
        if ctx["files_touched"]:
            blend_lines.append("### Files Modified")
            for fp in ctx["files_touched"]:
                blend_lines.append(f"- {fp}")
            blend_lines.append("")
        if ctx["commands"]:
            blend_lines.append("### Commands Run")
            for cmd in ctx["commands"][:10]:
                blend_lines.append(f"- `{cmd[:80]}`")
            blend_lines.append("")

    elif mode == "summary":
        # Take first and last user messages as summary
        user_msgs = [m for m in ctx["messages"] if m["role"] == "user"]
        if user_msgs:
            blend_lines.append("### Initial Request")
            blend_lines.append(user_msgs[0]["text"][:500])
            blend_lines.append("")
        if len(user_msgs) > 1:
            blend_lines.append("### Latest Request")
            blend_lines.append(user_msgs[-1]["text"][:500])
            blend_lines.append("")
        if ctx["files_touched"]:
            blend_lines.append(f"### Files Touched ({len(ctx['files_touched'])})")
            for fp in ctx["files_touched"][:20]:
                blend_lines.append(f"- {fp}")
            blend_lines.append("")

    else:  # full
        for msg in ctx["messages"]:
            role = "User" if msg["role"] == "user" else "Assistant"
            blend_lines.append(f"**{role}:** {msg['text'][:1000]}")
            blend_lines.append("")

    blend_lines.append("---")
    blend_lines.append("")

# Save blend
os.makedirs(BLENDS_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
blend_file = os.path.join(BLENDS_DIR, f"blend-{timestamp}.md")

with open(blend_file, "w") as f:
    f.write("\n".join(blend_lines))

total_msgs = sum(c["message_count"] for c in contexts)
total_files = len(set(fp for c in contexts for fp in c["files_touched"]))

print(f"{GREEN}{BOLD}Blend complete.{R}")
print(f"  {WHITE}File:{R}     {blend_file}")
print(f"  {WHITE}Messages:{R} {total_msgs} across {len(resolved)} sessions")
print(f"  {WHITE}Files:{R}    {total_files} unique files touched")
print()
print(f"{DIM}Use this file as context when starting a new session:{R}")
print(f"{DIM}  claude \"Read {blend_file} for context, then...\"{R}")
