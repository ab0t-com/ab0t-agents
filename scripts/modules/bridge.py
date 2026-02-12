#!/usr/bin/env python3
"""
Cross-Agent Context Bridge - transfer context between different coding agents.
Called by: agents bridge <session> [--to codex|claude] [--format md|json]
Env vars: SESSION_KEY, TARGET_AGENT (claude/codex), FORMAT (md/json)
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
MAGENTA = "\033[0;35m"
BLUE = "\033[0;34m"
GRAY = "\033[0;90m"
RED = "\033[0;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
R = "\033[0m"

CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")
BRIDGE_DIR = os.path.join(CACHE_DIR, "bridges")

session_key = os.environ.get("SESSION_KEY", "")
target_agent = os.environ.get("TARGET_AGENT", "")
fmt = os.environ.get("FORMAT", "md")
output = os.environ.get("OUTPUT", "")


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


def extract_context(fpath, agent_name):
    """Extract a portable context snapshot from a session."""
    context = {
        "decisions": [],
        "files_modified": {},
        "current_task": "",
        "errors_resolved": [],
        "key_messages": [],
        "commands_run": [],
        "git_info": {"branch": "", "commits": []},
        "constraints": [],
    }

    messages = []
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    rec_type = d.get("type", "")

                    # Git branch
                    if d.get("gitBranch") and not context["git_info"]["branch"]:
                        context["git_info"]["branch"] = d["gitBranch"]

                    if agent_name == "claude":
                        if rec_type == "user":
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
                                messages.append({"role": "user", "text": text})
                                # First user message is usually the task
                                if not context["current_task"]:
                                    context["current_task"] = " ".join(text.split())[:200]

                        elif rec_type == "assistant":
                            content = d.get("message", {}).get("content", [])
                            if isinstance(content, list):
                                asst_text = []
                                for item in content:
                                    if isinstance(item, dict):
                                        if item.get("type") == "text":
                                            asst_text.append(item.get("text", ""))
                                        elif item.get("type") == "tool_use":
                                            name = item.get("name", "")
                                            inp = item.get("input", {})
                                            if name in ("Write", "Edit"):
                                                fp = inp.get("file_path", "")
                                                if fp:
                                                    if fp not in context["files_modified"]:
                                                        context["files_modified"][fp] = 0
                                                    context["files_modified"][fp] += 1
                                            elif name == "Bash":
                                                cmd = inp.get("command", "")
                                                if cmd:
                                                    context["commands_run"].append(cmd[:80])
                                                    if "git commit" in cmd:
                                                        context["git_info"]["commits"].append(cmd[:100])
                                if asst_text:
                                    messages.append({"role": "assistant", "text": " ".join(asst_text)})

                    elif agent_name == "codex":
                        if rec_type == "response_item":
                            p = d.get("payload", d.get("item", {}))
                            role = p.get("role", "")
                            content = p.get("content", [])
                            text = ""
                            if isinstance(content, list):
                                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                            if text and role in ("user", "assistant"):
                                messages.append({"role": role, "text": text})
                                if role == "user" and not context["current_task"]:
                                    context["current_task"] = " ".join(text.split())[:200]

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    # Extract decisions (look for decision-like patterns in assistant messages)
    import re
    for msg in messages:
        if msg["role"] == "assistant":
            text = msg["text"]
            # Look for decision patterns
            for pattern in [
                r"(?:I'll|I will|Let's|We should|Going to)\s+(.{10,80})",
                r"(?:Decision|Approach|Strategy):\s*(.{10,80})",
            ]:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    decision = m.group(1).strip()
                    if decision and len(context["decisions"]) < 10:
                        context["decisions"].append(" ".join(decision.split())[:100])

    # Extract errors resolved
    for i, msg in enumerate(messages):
        if msg["role"] == "user":
            text_lower = msg["text"].lower()
            if any(w in text_lower for w in ["error", "fix", "bug", "broken", "failed"]):
                # Check if next assistant message resolves it
                if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                    context["errors_resolved"].append({
                        "problem": " ".join(msg["text"].split())[:100],
                        "resolution": " ".join(messages[i + 1]["text"].split())[:100],
                    })

    # Keep last few user messages as key context
    user_msgs = [m for m in messages if m["role"] == "user"]
    context["key_messages"] = [
        " ".join(m["text"].split())[:150] for m in user_msgs[-5:]
    ]

    context["total_messages"] = len(messages)
    return context


def format_markdown(context, source_agent, project, session_id, target):
    """Format context as a markdown handoff document."""
    lines = []
    lines.append("# Context Handoff")
    lines.append("")
    lines.append(f"**From:** {source_agent} session `{session_id[:8]}`")
    if target:
        lines.append(f"**To:** {target}")
    lines.append(f"**Project:** {project}")
    lines.append(f"**Generated:** {datetime.utcnow().isoformat()}Z")
    lines.append("")

    if context["current_task"]:
        lines.append("## Current Task")
        lines.append(context["current_task"])
        lines.append("")

    if context["git_info"]["branch"]:
        lines.append(f"**Git branch:** `{context['git_info']['branch']}`")
        lines.append("")

    if context["decisions"]:
        lines.append("## Key Decisions")
        for d in context["decisions"][:7]:
            lines.append(f"- {d}")
        lines.append("")

    if context["files_modified"]:
        lines.append("## Files Modified")
        for fp, count in sorted(context["files_modified"].items()):
            lines.append(f"- `{fp}` ({count} edit{'s' if count > 1 else ''})")
        lines.append("")

    if context["errors_resolved"]:
        lines.append("## Errors Resolved")
        for err in context["errors_resolved"][:5]:
            lines.append(f"- **Problem:** {err['problem']}")
            lines.append(f"  **Fix:** {err['resolution']}")
        lines.append("")

    if context["constraints"]:
        lines.append("## Constraints")
        for c in context["constraints"]:
            lines.append(f"- {c}")
        lines.append("")

    if context["key_messages"]:
        lines.append("## Recent Context (last user messages)")
        for msg in context["key_messages"]:
            lines.append(f"- {msg}")
        lines.append("")

    if context["git_info"]["commits"]:
        lines.append("## Git Commits During Session")
        for c in context["git_info"]["commits"][:5]:
            lines.append(f"- `{c}`")
        lines.append("")

    lines.append("---")
    lines.append(f"*{context['total_messages']} messages in original session*")

    return "\n".join(lines)


def format_json(context, source_agent, project, session_id, target):
    """Format context as structured JSON."""
    return json.dumps({
        "handoff": {
            "from_agent": source_agent,
            "to_agent": target or "any",
            "session_id": session_id,
            "project": project,
            "generated": datetime.utcnow().isoformat() + "Z",
        },
        "context": context,
    }, indent=2)


# Main
if not session_key:
    print(f"{RED}Usage: agents bridge <session> [--to claude|codex] [--format md|json]{R}")
    raise SystemExit(1)

fpath, agent_name, project = resolve_session()
if not fpath or not os.path.isfile(fpath):
    print(f"{RED}Could not find session: {session_key}{R}")
    raise SystemExit(1)

session_id = os.path.basename(fpath).replace(".jsonl", "")

# Auto-detect target if not specified
if not target_agent:
    target_agent = "codex" if agent_name == "claude" else "claude"

print(f"{BOLD}{CYAN}Context Bridge{R}")
print(f"{DIM}{'─' * 52}{R}")

a_color = CYAN if agent_name == "claude" else GREEN
t_color = CYAN if target_agent == "claude" else GREEN

print(f"  {a_color}[{agent_name}]{R} {WHITE}{session_id[:8]}{R}  →  {t_color}[{target_agent}]{R}")
print(f"  {BLUE}{project}{R}")
print()

# Extract context
context = extract_context(fpath, agent_name)

print(f"  {WHITE}Extracted:{R}")
print(f"    {len(context['decisions'])} decisions")
print(f"    {len(context['files_modified'])} files modified")
print(f"    {len(context['errors_resolved'])} errors resolved")
print(f"    {len(context['key_messages'])} key messages")
print(f"    {len(context['commands_run'])} commands run")
print()

# Format output
if fmt == "json":
    result = format_json(context, agent_name, project, session_id, target_agent)
else:
    result = format_markdown(context, agent_name, project, session_id, target_agent)

# Save or print
if output and output != "-":
    with open(output, "w") as f:
        f.write(result)
    print(f"{GREEN}Bridge document saved: {output}{R}")
else:
    os.makedirs(BRIDGE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "json" if fmt == "json" else "md"
    bridge_file = os.path.join(BRIDGE_DIR, f"bridge-{session_id[:8]}-to-{target_agent}-{timestamp}.{ext}")
    with open(bridge_file, "w") as f:
        f.write(result)
    print(f"{GREEN}Bridge document saved:{R}")
    print(f"  {WHITE}{bridge_file}{R}")

print()
print(f"{DIM}Use this to start a new {target_agent} session with context:{R}")
if target_agent == "claude":
    print(f'{DIM}  cd "{project}" && claude "Read {bridge_file} for context, then continue the work"{R}')
elif target_agent == "codex":
    print(f'{DIM}  cd "{project}" && codex "Read {bridge_file} for context, then continue the work"{R}')
