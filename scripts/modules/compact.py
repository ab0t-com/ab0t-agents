#!/usr/bin/env python3
"""
Context Compaction - LLM-powered summarization of long sessions.
Creates overlay files with intelligent summaries while preserving originals.
Called by: agents compact <session> [--keep-last N]
Env vars: SESSION_KEY, STRATEGY (time/size), KEEP_LAST (int), ACTION (compact/uncompact/status)
"""

import os
import sys
import json
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, resolve_session as _resolve_session, extract_text_from_record)
from llm import get_llm, LLMError, ANTHROPIC_SMALL, OPENAI_SMALL
from schemas import CompactOutput

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]

COMPACT_DIR = os.path.join(CACHE_DIR, "compacted")

session_key = os.environ.get("SESSION_KEY", "")
keep_last = int(os.environ.get("KEEP_LAST", "30"))
action = os.environ.get("ACTION", "compact")


def resolve_session():
    fpath, agent_name, project, _sid = _resolve_session(session_key, ALL_ADAPTERS)
    return fpath, agent_name, project


def file_sha256(fpath):
    h = hashlib.sha256()
    try:
        with open(fpath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def parse_messages(fpath, agent_name):
    """Parse session into structured messages with line numbers."""
    messages = []
    try:
        with open(fpath) as f:
            for line_num, line in enumerate(f):
                try:
                    record = json.loads(line)
                    role, text = extract_text_from_record(record, agent_name)
                    if role and text and role in ("user", "assistant"):
                        messages.append({
                            "role": role, "text": text,
                            "line_start": line_num, "line_end": line_num,
                        })
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    return messages


def summarize_segment(llm, segment):
    """Use LLM to summarize a message segment."""
    truncated = [{"role": m["role"], "text": m["text"][:500]} for m in segment]
    raw = llm.render_and_call_json("compact_summarize", {
        "messages": truncated,
    }, model=ANTHROPIC_SMALL if llm.provider == "anthropic" else OPENAI_SMALL,
       max_tokens=1024, temperature=0.2)
    return CompactOutput.from_dict(raw)


def segment_messages(llm, messages, target_segments=None):
    """Split messages into logical segments using message count heuristic.
    LLM handles the summarization quality, so simple chunking by size is fine."""
    if not target_segments:
        # ~15-25 messages per segment
        target_segments = max(1, len(messages) // 20)

    if len(messages) <= 20:
        return [messages]

    chunk_size = max(10, len(messages) // target_segments)
    segments = []
    for i in range(0, len(messages), chunk_size):
        seg = messages[i:i + chunk_size]
        if seg:
            segments.append(seg)
    return segments


def cmd_compact():
    """Create a compacted overlay of a session using LLM summarization."""
    if not session_key:
        print(f"{RED}Usage: agents compact <session> [--keep-last N]{R}")
        raise SystemExit(1)

    llm = get_llm()
    if not llm.available():
        print(f"{RED}No LLM API key found.{R}")
        print(f"{DIM}Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable compaction.{R}")
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
    print()

    # Split: compact older messages, keep recent in full
    to_compact = messages[:-keep_last]
    to_keep = messages[-keep_last:]

    # Segment and summarize with LLM
    segments = segment_messages(llm, to_compact)
    compacted_sections = []

    for i, segment in enumerate(segments):
        print(f"  {DIM}Summarizing segment {i + 1}/{len(segments)}...{R}", end="", flush=True)
        try:
            summary = summarize_segment(llm, segment)
            compacted_sections.append({
                "section_index": i,
                "original_lines": [segment[0]["line_start"], segment[-1]["line_end"]],
                "summary": summary.summary,
                "decisions": summary.decisions,
                "artifacts": summary.artifacts,
                "commands": summary.commands,
                "errors_resolved": summary.errors_resolved,
                "status": summary.status,
                "message_count": len(segment),
                "reversible": True,
            })
            print(f"\r  {GREEN}Segment {i + 1}/{len(segments)}: {len(summary.summary)} char summary, "
                  f"{len(summary.decisions)} decisions, {len(summary.artifacts)} artifacts{R}     ")
        except LLMError as e:
            print(f"\r  {RED}Segment {i + 1} failed: {e}{R}     ")
            # Fallback: just note the message count
            compacted_sections.append({
                "section_index": i,
                "original_lines": [segment[0]["line_start"], segment[-1]["line_end"]],
                "summary": f"({len(segment)} messages)",
                "decisions": [],
                "artifacts": [],
                "commands": [],
                "errors_resolved": [],
                "status": "in_progress",
                "message_count": len(segment),
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
        "keep_last": keep_last,
        "total_messages": len(messages),
        "compacted_messages": len(to_compact),
        "kept_messages": len(to_keep),
        "sections": compacted_sections,
        "kept_from_line": to_keep[0]["line_start"] if to_keep else 0,
    }

    # Build compacted JSONL overlay
    overlay_lines = []
    overlay_lines.append(json.dumps({
        "type": "compaction_header",
        "original": fpath,
        "original_hash": f"sha256:{original_hash}",
        "compacted_at": manifest["compacted_at"],
    }))
    for section in compacted_sections:
        overlay_lines.append(json.dumps({
            "type": "compacted_section",
            "summary": section["summary"],
            "decisions": section["decisions"],
            "artifacts": section["artifacts"],
            "original_lines": section["original_lines"],
            "message_count": section["message_count"],
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

    print()
    print(f"{GREEN}{BOLD}Compaction complete.{R}")
    print()
    print(f"  {WHITE}Sections:{R}   {len(compacted_sections)} segments summarized by LLM")
    print(f"  {WHITE}Compacted:{R}  {len(to_compact)} messages → {len(compacted_sections)} summaries")
    print(f"  {WHITE}Kept full:{R}  {len(to_keep)} recent messages")
    print(f"  {WHITE}Size:{R}       {overlay_size:,} bytes ({reduction:.0f}% reduction)")
    print()

    print(f"{BOLD}  Summaries:{R}")
    for s in compacted_sections:
        print(f"    {DIM}[{s['message_count']} msgs]{R} {GRAY}{s['summary'][:80]}{R}")
        if s["decisions"]:
            for d in s["decisions"][:2]:
                print(f"      {YELLOW}→ {d[:60]}{R}")

    print()
    print(f"  {WHITE}Overlay:{R}  {overlay_file}")
    print(f"  {WHITE}Manifest:{R} {manifest_file}")
    print()
    print(f"{DIM}Original file is untouched. Uncompact: agents uncompact {session_key}{R}")
    llm.print_cost_summary()


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


if __name__ == "__main__":
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
