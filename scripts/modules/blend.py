#!/usr/bin/env python3
"""
Blend context from multiple sessions into a synthesized context document.
LLM-powered synthesis instead of raw concatenation.
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
from adapters.gemini import GeminiAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, time_ago, resolve_session as _resolve_session,
                   extract_text_from_record)
from llm import get_llm, LLMError, ANTHROPIC_LARGE, OPENAI_LARGE
from schemas import BlendOutput

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]

BLENDS_DIR = os.path.join(CACHE_DIR, "blends")

sessions_str = os.environ.get("SESSIONS", "")
mode = os.environ.get("MODE", "summary")

session_keys = [s.strip() for s in sessions_str.split(",") if s.strip()]


def resolve_session(key):
    fpath, agent_name, project, _sid = _resolve_session(key, ALL_ADAPTERS)
    return fpath, agent_name, project


def extract_session_context(fpath, agent_name):
    """Extract key context from a session using shared utils."""
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

                    role, text = extract_text_from_record(d, agent_name)
                    if role and text and role in ("user", "assistant"):
                        context["messages"].append({"role": role, "text": text})
                        context["message_count"] += 1
                        if role == "user" and not context["first_message"]:
                            context["first_message"] = " ".join(text.split())[:80]

                    # Extract tool usage from Claude assistant messages
                    if agent_name == "claude" and d.get("type") == "assistant":
                        content = d.get("message", {}).get("content", [])
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "tool_use":
                                    name = item.get("name", "")
                                    inp = item.get("input", {})
                                    if name in ("Write", "Edit"):
                                        fp = inp.get("file_path", "")
                                        if fp:
                                            context["files_touched"].add(fp)
                                    elif name == "Bash":
                                        cmd = inp.get("command", "")
                                        if cmd:
                                            context["commands"].append(cmd[:100])

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    context["files_touched"] = list(context["files_touched"])
    return context


def build_session_summary(ctx):
    """Build a text summary of a session for the LLM prompt."""
    user_msgs = [m for m in ctx["messages"] if m["role"] == "user"]
    asst_msgs = [m for m in ctx["messages"] if m["role"] == "assistant"]

    parts = []
    if user_msgs:
        parts.append(f"Initial request: {user_msgs[0]['text'][:200]}")
    if len(user_msgs) > 1:
        parts.append(f"Latest request: {user_msgs[-1]['text'][:200]}")
    if asst_msgs:
        parts.append(f"Last response: {asst_msgs[-1]['text'][:200]}")
    return " | ".join(parts) if parts else "(empty session)"


def llm_synthesize(llm, project, session_infos):
    """Use LLM to synthesize a unified context from multiple sessions."""
    sessions_data = []
    for info in session_infos:
        sessions_data.append({
            "agent": info["agent"],
            "time_ago": info["time_ago"],
            "first_message": info["first_message"],
            "summary": info["summary"],
            "files": info["files"],
        })

    raw = llm.render_and_call_json("blend_synthesize", {
        "project": project,
        "sessions": sessions_data,
    }, model=ANTHROPIC_LARGE if llm.provider == "anthropic" else OPENAI_LARGE,
       max_tokens=2048, temperature=0.3)
    return BlendOutput.from_dict(raw)


def format_blend_markdown(blend, project, resolved, mode_str):
    """Format the blend output as a markdown document."""
    lines = []
    lines.append("# Blended Session Context")
    lines.append("")
    lines.append(f"**Project:** {project}")
    lines.append(f"**Generated:** {datetime.utcnow().isoformat()}Z")
    lines.append(f"**Sources:** {len(resolved)} sessions")
    lines.append(f"**Mode:** {mode_str}")
    lines.append("")

    lines.append("## Synthesized Context")
    lines.append(blend.synthesized_context)
    lines.append("")

    if blend.active_tasks:
        lines.append("## Active Tasks")
        for task in blend.active_tasks:
            lines.append(f"- {task}")
        lines.append("")

    if blend.completed_tasks:
        lines.append("## Completed Tasks")
        for task in blend.completed_tasks:
            lines.append(f"- {task}")
        lines.append("")

    if blend.key_files:
        lines.append("## Key Files")
        for f in blend.key_files:
            lines.append(f"- `{f}`")
        lines.append("")

    if blend.decisions:
        lines.append("## Decisions")
        for d in blend.decisions:
            lines.append(f"- {d}")
        lines.append("")

    if blend.blockers:
        lines.append("## Blockers")
        for b in blend.blockers:
            lines.append(f"- {b}")
        lines.append("")

    if blend.recommended_next_steps:
        lines.append("## Recommended Next Steps")
        for i, step in enumerate(blend.recommended_next_steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by agents blend*")
    return "\n".join(lines)


def format_fallback_markdown(resolved, contexts, mode_str):
    """Fallback: format without LLM (concatenation mode)."""
    lines = []
    lines.append("# Blended Session Context")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    lines.append(f"Mode: {mode_str} (fallback — no LLM)")
    lines.append(f"Sources: {len(resolved)} sessions")
    lines.append("")

    for i, (r, ctx) in enumerate(zip(resolved, contexts)):
        lines.append(f"## Source {i+1}: {r['agent']} session {r['session_id'][:8]}")
        if r["project"]:
            lines.append(f"Project: {r['project']}")
        lines.append("")

        if mode_str == "artifacts":
            if ctx["files_touched"]:
                lines.append("### Files Modified")
                for fp in ctx["files_touched"]:
                    lines.append(f"- {fp}")
                lines.append("")
            if ctx["commands"]:
                lines.append("### Commands Run")
                for cmd in ctx["commands"][:10]:
                    lines.append(f"- `{cmd[:80]}`")
                lines.append("")
        elif mode_str == "summary":
            user_msgs = [m for m in ctx["messages"] if m["role"] == "user"]
            if user_msgs:
                lines.append("### Initial Request")
                lines.append(user_msgs[0]["text"][:500])
                lines.append("")
            if len(user_msgs) > 1:
                lines.append("### Latest Request")
                lines.append(user_msgs[-1]["text"][:500])
                lines.append("")
            if ctx["files_touched"]:
                lines.append(f"### Files Touched ({len(ctx['files_touched'])})")
                for fp in ctx["files_touched"][:20]:
                    lines.append(f"- {fp}")
                lines.append("")
        else:  # full
            for msg in ctx["messages"]:
                r_label = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"**{r_label}:** {msg['text'][:1000]}")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def cmd_blend():
    if not session_keys:
        print(f"{RED}Usage: agents blend <session1> <session2> [--mode full|summary|artifacts]{R}")
        raise SystemExit(1)

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

    now_time = time.time()
    contexts = []
    session_infos = []

    for r in resolved:
        ctx = extract_session_context(r["fpath"], r["agent"])
        contexts.append(ctx)

        mtime = os.path.getmtime(r["fpath"]) if os.path.isfile(r["fpath"]) else now_time
        ago = time_ago(mtime)

        a_color = CYAN if r["agent"] == "claude" else GREEN
        badge = f"{a_color}[{r['agent']}]{R}"
        print(f"  {badge} {WHITE}{r['session_id'][:8]}{R}  {DIM}{ctx['message_count']} messages, {len(ctx['files_touched'])} files{R}")
        if ctx["first_message"]:
            print(f"    {GRAY}\"{ctx['first_message']}\"{R}")

        session_infos.append({
            "agent": r["agent"],
            "time_ago": ago,
            "first_message": ctx["first_message"],
            "summary": build_session_summary(ctx),
            "files": ctx["files_touched"][:20],
        })

    print()

    # Determine primary project (most common across sessions)
    projects = [r["project"] for r in resolved if r["project"]]
    primary_project = max(set(projects), key=projects.count) if projects else "unknown"

    # Try LLM synthesis
    llm = get_llm()
    blend = None
    if llm.available():
        print(f"  {DIM}Synthesizing unified context with LLM...{R}", flush=True)
        try:
            blend = llm_synthesize(llm, primary_project, session_infos)
        except LLMError as e:
            print(f"  {DIM}LLM synthesis failed, falling back to concatenation{R}")

    # Format output
    if blend:
        content = format_blend_markdown(blend, primary_project, resolved, mode)
    else:
        content = format_fallback_markdown(resolved, contexts, mode)

    # Save
    os.makedirs(BLENDS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    blend_file = os.path.join(BLENDS_DIR, f"blend-{timestamp}.md")

    with open(blend_file, "w") as f:
        f.write(content)

    total_msgs = sum(c["message_count"] for c in contexts)
    total_files = len(set(fp for c in contexts for fp in c["files_touched"]))

    print()
    print(f"{GREEN}{BOLD}Blend complete.{R}")
    print(f"  {WHITE}File:{R}     {blend_file}")
    print(f"  {WHITE}Messages:{R} {total_msgs} across {len(resolved)} sessions")
    print(f"  {WHITE}Files:{R}    {total_files} unique files touched")

    # Show synthesis highlights if LLM was used
    if blend:
        print()
        print(f"  {WHITE}{BOLD}Synthesis:{R}")
        print(f"    {GRAY}{blend.synthesized_context[:120]}{R}")
        if blend.active_tasks:
            print(f"  {WHITE}Active:{R}   {', '.join(blend.active_tasks[:3])}")
        if blend.recommended_next_steps:
            print(f"  {WHITE}Next:{R}     {blend.recommended_next_steps[0]}")
        if blend.blockers:
            print(f"  {YELLOW}Blocked:{R}  {blend.blockers[0]}")

    print()
    print(f"{DIM}Use this file as context when starting a new session:{R}")
    print(f"{DIM}  claude \"Read {blend_file} for context, then...\"{R}")

    if llm.available() and llm.total_calls > 0:
        llm.print_cost_summary()


if __name__ == "__main__":
    cmd_blend()
