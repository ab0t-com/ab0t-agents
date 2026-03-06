#!/usr/bin/env python3
"""
Export a session as clean markdown, text, or JSON.
Called by: agents export <session-num|session-id> [--format md|txt|json]
Env vars: SESSION_KEY, FORMAT (md/txt/json), OUTPUT (file or "-" for stdout)
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

from utils import (RED, GREEN, DIM, BOLD, CYAN, R,
                   resolve_session as _resolve_session)

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]

session_key = os.environ.get("SESSION_KEY", "")
fmt = os.environ.get("FORMAT", "md")
output = os.environ.get("OUTPUT", "-")


def resolve_session():
    fpath, agent_name, project, _sid = _resolve_session(session_key, ALL_ADAPTERS)
    return fpath, agent_name, project


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    name = item.get("name", "")
                    inp = item.get("input", {})
                    if name in ("Bash",):
                        parts.append(f"```bash\n$ {inp.get('command', '')}\n```")
                    elif name in ("Write", "Edit"):
                        fp = inp.get("file_path", "")
                        parts.append(f"[{name}: {fp}]")
        return "\n".join(parts)
    return ""


def parse_claude_session(fpath):
    messages = []
    metadata = {"agent": "claude", "session_id": os.path.basename(fpath).replace(".jsonl", "")}
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    rec_type = d.get("type")
                    ts = d.get("timestamp", "")

                    if rec_type == "user":
                        text = extract_text(d.get("message", {}).get("content", ""))
                        if text:
                            messages.append({"role": "user", "text": text, "ts": ts})
                    elif rec_type == "assistant":
                        text = extract_text(d.get("message", {}).get("content", []))
                        model = d.get("message", {}).get("model", "")
                        if text:
                            messages.append({"role": "assistant", "text": text, "ts": ts, "model": model})
                    elif rec_type == "summary":
                        metadata["summary"] = d.get("summary", "")
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    return metadata, messages


def parse_codex_session(fpath):
    messages = []
    metadata = {"agent": "codex", "session_id": ""}
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    rec_type = d.get("type")

                    if rec_type == "session_meta":
                        metadata["session_id"] = d.get("session_id", "")
                        metadata["cwd"] = d.get("cwd", "")
                    elif rec_type == "response_item":
                        item = d.get("item", {})
                        role = item.get("role", "")
                        content = item.get("content", [])
                        text = ""
                        if isinstance(content, list):
                            text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                        elif isinstance(content, str):
                            text = content
                        if text and role in ("user", "assistant"):
                            messages.append({"role": role, "text": text, "ts": d.get("ts", "")})
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    return metadata, messages


def format_markdown(metadata, messages, project):
    lines = []
    lines.append(f"# Session Export")
    lines.append("")
    lines.append(f"- **Agent:** {metadata.get('agent', 'unknown')}")
    lines.append(f"- **Session:** {metadata.get('session_id', 'unknown')[:8]}")
    if project:
        lines.append(f"- **Project:** {project}")
    if metadata.get("summary"):
        lines.append(f"- **Summary:** {metadata['summary']}")
    lines.append(f"- **Messages:** {len(messages)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for msg in messages:
        role = msg["role"]
        ts = msg.get("ts", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_str = dt.strftime("%H:%M")
            except ValueError:
                ts_str = ""
        else:
            ts_str = ""

        header = f"**{'User' if role == 'user' else 'Assistant'}**"
        if ts_str:
            header += f" ({ts_str})"
        if msg.get("model"):
            header += f" *{msg['model']}*"

        lines.append(header)
        lines.append("")
        lines.append(msg["text"])
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def format_text(metadata, messages, project):
    lines = []
    lines.append(f"Session: {metadata.get('session_id', '')[:8]} [{metadata.get('agent', '')}]")
    if project:
        lines.append(f"Project: {project}")
    lines.append(f"Messages: {len(messages)}")
    lines.append("=" * 60)
    lines.append("")

    for msg in messages:
        role = "USER" if msg["role"] == "user" else "ASSISTANT"
        lines.append(f"--- {role} ---")
        lines.append(msg["text"])
        lines.append("")

    return "\n".join(lines)


def format_json(metadata, messages, project):
    return json.dumps({
        "metadata": {**metadata, "project": project},
        "messages": messages,
    }, indent=2)


def cmd_export():
    if not session_key:
        print(f"{RED}Usage: agents export <session-num|session-id> [--format md|txt|json]{R}")
        raise SystemExit(1)

    fpath, agent_name, project = resolve_session()
    if not fpath or not os.path.isfile(fpath):
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)

    if agent_name == "codex":
        metadata, messages = parse_codex_session(fpath)
    else:
        metadata, messages = parse_claude_session(fpath)

    if fmt == "json":
        result = format_json(metadata, messages, project)
    elif fmt == "txt":
        result = format_text(metadata, messages, project)
    else:
        result = format_markdown(metadata, messages, project)

    if output == "-":
        print(result)
    else:
        with open(output, "w") as f:
            f.write(result)
        print(f"{GREEN}Exported to {output}{R} ({len(messages)} messages, {fmt} format)")


if __name__ == "__main__":
    cmd_export()
