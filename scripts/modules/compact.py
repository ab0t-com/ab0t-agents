#!/usr/bin/env python3
"""
Context Compaction - reversible summarization of long sessions.
Creates overlay files that summarize older portions while preserving originals.
Called by: agents compact <session> [--strategy time|size|topic] [--keep-last N]
Env vars: SESSION_KEY, STRATEGY (time/size), KEEP_LAST (int, messages to keep in full)
"""

import os
import sys
import json
import hashlib
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
COMPACT_DIR = os.path.join(CACHE_DIR, "compacted")

session_key = os.environ.get("SESSION_KEY", "")
strategy = os.environ.get("STRATEGY", "size")
keep_last = int(os.environ.get("KEEP_LAST", "30"))
action = os.environ.get("ACTION", "compact")


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


def file_sha256(fpath):
    h = hashlib.sha256()
    try:
        with open(fpath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def extract_text(content, agent_name):
    """Extract readable text from message content."""
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
                    if name == "Bash":
                        parts.append(f"[Bash: {inp.get('command', '')[:60]}]")
                    elif name in ("Write", "Edit"):
                        parts.append(f"[{name}: {inp.get('file_path', '')}]")
                    elif name == "Read":
                        parts.append(f"[Read: {inp.get('file_path', '')}]")
        return " ".join(parts)
    return ""


def parse_messages(fpath, agent_name):
    """Parse session into structured messages with line numbers."""
    messages = []
    try:
        with open(fpath) as f:
            for line_num, line in enumerate(f):
                try:
                    d = json.loads(line)
                    rec_type = d.get("type", "")
                    ts = d.get("timestamp", "")

                    if agent_name == "claude":
                        if rec_type == "user":
                            text = extract_text(d.get("message", {}).get("content", ""), agent_name)
                            if text:
                                messages.append({
                                    "role": "user", "text": text, "ts": ts,
                                    "line_start": line_num, "line_end": line_num,
                                })
                        elif rec_type == "assistant":
                            text = extract_text(d.get("message", {}).get("content", []), agent_name)
                            if text:
                                messages.append({
                                    "role": "assistant", "text": text, "ts": ts,
                                    "line_start": line_num, "line_end": line_num,
                                })
                    elif agent_name == "codex":
                        if rec_type == "response_item":
                            p = d.get("payload", d.get("item", {}))
                            role = p.get("role", "")
                            content = p.get("content", [])
                            text = ""
                            if isinstance(content, list):
                                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                            if text and role in ("user", "assistant"):
                                messages.append({
                                    "role": role, "text": text, "ts": ts,
                                    "line_start": line_num, "line_end": line_num,
                                })
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    return messages


def segment_by_topic_shift(messages, min_segment=5):
    """Split messages into segments based on topic shifts.
    Simple heuristic: user messages that introduce new topics start new segments."""
    if len(messages) <= min_segment:
        return [messages]

    segments = []
    current = []
    prev_terms = set()

    for msg in messages:
        if msg["role"] == "user":
            # Extract key terms
            words = set(w.lower() for w in msg["text"].split() if len(w) > 4)
            # Check overlap with previous terms
            if prev_terms and len(words & prev_terms) < 2 and len(current) >= min_segment:
                segments.append(current)
                current = []
            prev_terms = words

        current.append(msg)

    if current:
        segments.append(current)

    return segments


def summarize_segment(segment):
    """Create a compact summary of a message segment.
    This is a local heuristic summary, not LLM-generated."""
    user_msgs = [m for m in segment if m["role"] == "user"]
    assistant_msgs = [m for m in segment if m["role"] == "assistant"]

    # Extract key phrases from user messages
    topics = []
    for m in user_msgs[:3]:
        text = " ".join(m["text"].split())[:100]
        topics.append(text)

    # Extract file operations from assistant messages
    files = set()
    commands = []
    for m in assistant_msgs:
        for match in __import__("re").finditer(r'\[(?:Write|Edit|Read): ([^\]]+)\]', m["text"]):
            files.add(match.group(1))
        for match in __import__("re").finditer(r'\[Bash: ([^\]]+)\]', m["text"]):
            commands.append(match.group(1))

    # Build summary
    parts = []
    if topics:
        parts.append(f"User requested: {topics[0]}")
        for t in topics[1:3]:
            parts.append(f"Then: {t}")
    if files:
        parts.append(f"Files touched: {', '.join(list(files)[:5])}")
    if commands:
        parts.append(f"Commands: {', '.join(commands[:3])}")

    return {
        "summary": " | ".join(parts) if parts else f"({len(segment)} messages)",
        "message_count": len(segment),
        "user_count": len(user_msgs),
        "files": list(files),
        "commands": commands[:5],
    }


def cmd_compact():
    """Create a compacted overlay of a session."""
    if not session_key:
        print(f"{RED}Usage: agents compact <session> [--keep-last N]{R}")
        raise SystemExit(1)

    fpath, agent_name, project = resolve_session()
    if not fpath or not os.path.isfile(fpath):
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)

    session_id = os.path.basename(fpath).replace(".jsonl", "")
    messages = parse_messages(fpath, agent_name)

    if len(messages) <= keep_last:
        print(f"{GRAY}Session has {len(messages)} messages (keep_last={keep_last}). Nothing to compact.{R}")
        return

    print(f"{BOLD}{CYAN}Compacting Session{R}")
    print(f"{DIM}{'─' * 52}{R}")
    a_color = CYAN if agent_name == "claude" else GREEN
    print(f"  {a_color}[{agent_name}]{R} {WHITE}{session_id[:8]}{R}")
    print(f"  {WHITE}Messages:{R} {len(messages)}")
    print(f"  {WHITE}Keep last:{R} {keep_last}")
    print(f"  {WHITE}Strategy:{R} {strategy}")
    print()

    # Split: compact older messages, keep recent in full
    to_compact = messages[:-keep_last]
    to_keep = messages[-keep_last:]

    # Segment the compactable portion
    segments = segment_by_topic_shift(to_compact)

    # Generate summaries for each segment
    compacted_sections = []
    for i, segment in enumerate(segments):
        summary = summarize_segment(segment)
        compacted_sections.append({
            "section_index": i,
            "original_lines": [segment[0]["line_start"], segment[-1]["line_end"]],
            "summary": summary["summary"],
            "message_count": summary["message_count"],
            "files": summary["files"],
            "commands": summary["commands"],
            "reversible": True,
        })

    # Build manifest
    original_hash = file_sha256(fpath)
    manifest = {
        "original": fpath,
        "original_hash": f"sha256:{original_hash}",
        "session_id": session_id,
        "agent": agent_name,
        "project": project,
        "compacted_at": datetime.utcnow().isoformat() + "Z",
        "strategy": strategy,
        "keep_last": keep_last,
        "total_messages": len(messages),
        "compacted_messages": len(to_compact),
        "kept_messages": len(to_keep),
        "sections": compacted_sections,
        "kept_from_line": to_keep[0]["line_start"] if to_keep else 0,
    }

    # Build compacted JSONL overlay
    overlay_lines = []
    # Add compaction header
    overlay_lines.append(json.dumps({
        "type": "compaction_header",
        "original": fpath,
        "original_hash": f"sha256:{original_hash}",
        "compacted_at": manifest["compacted_at"],
    }))
    # Add summarized sections
    for section in compacted_sections:
        overlay_lines.append(json.dumps({
            "type": "compacted_section",
            "summary": section["summary"],
            "original_lines": section["original_lines"],
            "message_count": section["message_count"],
            "files": section["files"],
        }))
    # Add kept messages (copy original lines)
    try:
        with open(fpath) as f:
            all_lines = f.readlines()
        start = to_keep[0]["line_start"] if to_keep else len(all_lines)
        for line in all_lines[start:]:
            overlay_lines.append(line.rstrip())
    except OSError:
        pass

    # Save
    os.makedirs(COMPACT_DIR, exist_ok=True)
    overlay_file = os.path.join(COMPACT_DIR, f"{session_id}.jsonl")
    manifest_file = os.path.join(COMPACT_DIR, f"{session_id}.manifest.json")

    with open(overlay_file, "w") as f:
        for line in overlay_lines:
            f.write(line + "\n")

    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    # Report
    original_size = os.path.getsize(fpath)
    overlay_size = os.path.getsize(overlay_file)
    reduction = ((original_size - overlay_size) / original_size * 100) if original_size else 0

    print(f"{GREEN}{BOLD}Compaction complete.{R}")
    print()
    print(f"  {WHITE}Sections:{R}   {len(compacted_sections)} topic segments summarized")
    print(f"  {WHITE}Compacted:{R}  {len(to_compact)} messages → {len(compacted_sections)} summaries")
    print(f"  {WHITE}Kept full:{R}  {len(to_keep)} recent messages")
    print(f"  {WHITE}Size:{R}       {overlay_size:,} bytes ({reduction:.0f}% reduction)")
    print()

    # Show section summaries
    print(f"{BOLD}  Sections:{R}")
    for s in compacted_sections:
        print(f"    {DIM}[{s['message_count']} msgs]{R} {GRAY}{s['summary'][:60]}{R}")

    print()
    print(f"  {WHITE}Overlay:{R}  {overlay_file}")
    print(f"  {WHITE}Manifest:{R} {manifest_file}")
    print()
    print(f"{DIM}Original file is untouched. Uncompact: agents uncompact {session_key}{R}")


def cmd_uncompact():
    """Remove compaction overlay, restoring full session."""
    if not session_key:
        print(f"{RED}Usage: agents uncompact <session>{R}")
        raise SystemExit(1)

    fpath, agent_name, project = resolve_session()
    if not fpath:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)

    session_id = os.path.basename(fpath).replace(".jsonl", "")
    overlay_file = os.path.join(COMPACT_DIR, f"{session_id}.jsonl")
    manifest_file = os.path.join(COMPACT_DIR, f"{session_id}.manifest.json")

    if not os.path.isfile(overlay_file):
        print(f"{GRAY}Session is not compacted.{R}")
        return

    os.remove(overlay_file)
    if os.path.isfile(manifest_file):
        os.remove(manifest_file)

    print(f"{GREEN}Uncompacted{R} {WHITE}{session_id[:8]}{R}")
    print(f"{DIM}Original session file was never modified.{R}")


def cmd_status():
    """Show compaction status for all sessions."""
    if not os.path.isdir(COMPACT_DIR):
        print(f"{GRAY}No compacted sessions.{R}")
        return

    manifests = [f for f in os.listdir(COMPACT_DIR) if f.endswith(".manifest.json")]
    if not manifests:
        print(f"{GRAY}No compacted sessions.{R}")
        return

    print(f"{BOLD}{CYAN}Compacted Sessions{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    for mf in sorted(manifests):
        try:
            with open(os.path.join(COMPACT_DIR, mf)) as f:
                manifest = json.load(f)
            sid = manifest.get("session_id", "?")
            agent = manifest.get("agent", "?")
            total = manifest.get("total_messages", 0)
            compacted = manifest.get("compacted_messages", 0)
            kept = manifest.get("kept_messages", 0)
            sections = len(manifest.get("sections", []))
            when = manifest.get("compacted_at", "?")

            a_color = CYAN if agent == "claude" else GREEN
            print(f"  {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R}")
            print(f"    {DIM}{compacted}/{total} messages compacted into {sections} sections, "
                  f"{kept} kept in full{R}")
            print(f"    {DIM}Compacted: {when}{R}")
            print()
        except (OSError, json.JSONDecodeError):
            pass


# Dispatch
actions = {
    "compact": cmd_compact,
    "uncompact": cmd_uncompact,
    "status": cmd_status,
}

handler = actions.get(action)
if handler:
    handler()
else:
    print(f"{RED}Unknown action: {action}{R}")
    print(f"{DIM}Actions: compact, uncompact, status{R}")
    raise SystemExit(1)
