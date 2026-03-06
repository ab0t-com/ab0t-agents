#!/usr/bin/env python3
"""
Topic Modeling - LLM-powered semantic topic detection across sessions.
Stage 1: Extract topics per session (Haiku)
Stage 2: Consolidate into taxonomy across all sessions (Sonnet)
Called by: agents topics [--project PATH]
Env vars: ACTION (detect/list/show), PROJECT (path), TOPIC_NAME
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

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, time_ago, extract_text_from_record)
from llm import get_llm, LLMError, ANTHROPIC_SMALL, ANTHROPIC_LARGE, OPENAI_SMALL, OPENAI_LARGE
from schemas import TopicExtractOutput, TopicConsolidateOutput

TOPICS_FILE = os.path.join(CACHE_DIR, "topics.json")

action = os.environ.get("ACTION", "detect")
project_filter = os.environ.get("PROJECT", "all")
topic_name = os.environ.get("TOPIC_NAME", "")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]


def extract_messages(fpath, agent_name, max_messages=30):
    """Extract key messages from a session for topic detection."""
    messages = []
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    role, text = extract_text_from_record(record, agent_name)
                    if role and text and role in ("user", "assistant"):
                        messages.append({"role": role, "text": text[:300]})
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    # Take first few + last few for coverage
    if len(messages) > max_messages:
        half = max_messages // 2
        messages = messages[:half] + messages[-half:]
    return messages


def stage_extract(llm, messages, agent, project):
    """Stage 1: Extract topics from a single session."""
    raw = llm.render_and_call_json("topics_extract", {
        "agent": agent,
        "project": project,
        "messages": messages,
    }, model=ANTHROPIC_SMALL if llm.provider == "anthropic" else OPENAI_SMALL,
       max_tokens=512, temperature=0.2)
    return TopicExtractOutput.from_dict(raw)


def stage_consolidate(llm, session_extracts):
    """Stage 2: Consolidate per-session topics into a taxonomy."""
    sessions_data = []
    for s in session_extracts:
        sessions_data.append({
            "agent": s["agent"],
            "project": s["project"],
            "topics": [{"label": t.label, "category": t.category} for t in s["extract"].topics],
            "technologies": s["extract"].technologies,
            "domain": s["extract"].domain,
        })
    raw = llm.render_and_call_json("topics_label", {
        "sessions": sessions_data,
    }, model=ANTHROPIC_LARGE if llm.provider == "anthropic" else OPENAI_LARGE,
       max_tokens=2048, temperature=0.2)
    return TopicConsolidateOutput.from_dict(raw)


def cmd_detect():
    """Scan sessions and detect topics using LLM."""
    llm = get_llm()
    if not llm.available():
        print(f"{RED}No LLM API key found.{R}")
        print(f"{DIM}Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable topic detection.{R}")
        raise SystemExit(1)

    print(f"{BOLD}{CYAN}Detecting Topics...{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    # Stage 1: Extract topics per session
    session_extracts = []
    session_meta = {}  # sid -> metadata
    now = time.time()

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            if project_filter != "all" and not display_path.startswith(project_filter):
                continue

            sid = os.path.basename(fpath).replace(".jsonl", "")
            messages = extract_messages(fpath, adapter.name)
            if len(messages) < 3:
                continue

            a_color = CYAN if adapter.name == "claude" else GREEN
            print(f"  {a_color}[{adapter.name}]{R} {WHITE}{sid[:8]}{R}", end="", flush=True)

            try:
                extract = stage_extract(llm, messages, adapter.name, display_path)
                topic_labels = [t.label for t in extract.topics]
                print(f"  {GREEN}{', '.join(topic_labels[:3])}{R}")

                session_extracts.append({
                    "sid": sid,
                    "agent": adapter.name,
                    "project": display_path,
                    "mtime": mtime,
                    "extract": extract,
                })
                session_meta[sid] = {
                    "agent": adapter.name,
                    "project": display_path,
                    "mtime": mtime,
                    "topics_raw": topic_labels,
                    "technologies": extract.technologies,
                    "domain": extract.domain,
                }
            except LLMError as e:
                print(f"  {RED}failed{R}")

    if not session_extracts:
        print(f"  {GRAY}No sessions with detectable topics.{R}")
        return

    # Stage 2: Consolidate into taxonomy
    print()
    print(f"  {DIM}Consolidating {len(session_extracts)} sessions into topic taxonomy...{R}", flush=True)

    try:
        consolidated = stage_consolidate(llm, session_extracts)
    except LLMError as e:
        print(f"  {RED}Consolidation failed: {e}{R}")
        # Fall back to raw topics
        consolidated = None

    # Build topics data for storage
    topics_data = {
        "topics": {},
        "sessions": {},
        "scanned_at": datetime.utcnow().isoformat() + "Z",
    }

    if consolidated:
        # Map consolidated topics back to sessions
        for ct in consolidated.topics:
            label = ct.label
            # Find which sessions match this topic
            matching_sids = []
            for se in session_extracts:
                raw_labels = [t.label.lower() for t in se["extract"].topics]
                # Check if any raw topic overlaps semantically (simple word overlap)
                ct_words = set(label.lower().split())
                for rl in raw_labels:
                    rl_words = set(rl.lower().split())
                    if ct_words & rl_words:
                        matching_sids.append(se["sid"])
                        break

            if not matching_sids:
                # If no word overlap match, assign to sessions that had similar categories
                for se in session_extracts:
                    raw_cats = [t.category for t in se["extract"].topics]
                    if ct.category in raw_cats:
                        matching_sids.append(se["sid"])

            topics_data["topics"][label] = {
                "description": ct.description,
                "category": ct.category,
                "session_count": ct.session_count,
                "technologies": ct.technologies,
                "sessions": matching_sids[:20],
                "projects": list(set(session_meta[s]["project"] for s in matching_sids if s in session_meta)),
                "agents": list(set(session_meta[s]["agent"] for s in matching_sids if s in session_meta)),
                "latest_mtime": max((session_meta[s]["mtime"] for s in matching_sids if s in session_meta), default=0),
            }
    else:
        # Use raw topics as fallback
        for se in session_extracts:
            for t in se["extract"].topics:
                label = t.label
                if label not in topics_data["topics"]:
                    topics_data["topics"][label] = {
                        "description": "",
                        "category": t.category,
                        "session_count": 0,
                        "technologies": se["extract"].technologies,
                        "sessions": [],
                        "projects": [],
                        "agents": [],
                        "latest_mtime": 0,
                    }
                td = topics_data["topics"][label]
                td["sessions"].append(se["sid"])
                td["session_count"] = len(td["sessions"])
                td["projects"] = list(set(td["projects"] + [se["project"]]))
                td["agents"] = list(set(td["agents"] + [se["agent"]]))
                td["latest_mtime"] = max(td["latest_mtime"], se["mtime"])

    for sid, meta in session_meta.items():
        topics_data["sessions"][sid] = {
            "topics": meta["topics_raw"],
            "agent": meta["agent"],
            "project": meta["project"],
            "mtime": meta["mtime"],
            "technologies": meta["technologies"],
            "domain": meta["domain"],
        }

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(TOPICS_FILE, "w") as f:
        json.dump(topics_data, f, indent=2)

    # Display
    print()
    topics = topics_data["topics"]
    print(f"{BOLD}Topics{R} {DIM}({len(topics)} detected from {len(session_extracts)} sessions){R}")
    print()

    for label, info in sorted(topics.items(), key=lambda x: -x[1].get("latest_mtime", 0))[:15]:
        scount = info.get("session_count", len(info.get("sessions", [])))
        category = info.get("category", "")
        desc = info.get("description", "")
        techs = info.get("technologies", [])
        latest = info.get("latest_mtime", 0)
        agents = info.get("agents", [])

        agents_str = " ".join(
            f"{CYAN if a == 'claude' else GREEN}[{a}]{R}" for a in sorted(agents)
        )
        age_str = time_ago(latest) if latest else "?"

        print(f"  {WHITE}{label}{R}  {DIM}({category}){R}  {agents_str}")
        if desc:
            print(f"    {GRAY}{desc[:70]}{R}")
        if techs:
            print(f"    {MAGENTA}{', '.join(techs[:5])}{R}", end="")
        print(f"  {DIM}{scount} session{'s' if scount != 1 else ''}  {age_str}{R}")
        print()

    print(f"{DIM}Saved to {TOPICS_FILE}{R}")
    llm.print_cost_summary()


def cmd_list():
    """List previously detected topics."""
    try:
        with open(TOPICS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"{GRAY}No topics detected yet. Run: agents topics{R}")
        return

    topics = data.get("topics", {})
    if not topics:
        print(f"{GRAY}No topics found. Run: agents topics{R}")
        return

    now = time.time()
    print(f"{BOLD}{CYAN}Topics{R} {DIM}(last scan: {data.get('scanned_at', 'unknown')}){R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    for label, info in sorted(topics.items(), key=lambda x: -x[1].get("latest_mtime", 0)):
        scount = info.get("session_count", len(info.get("sessions", [])))
        category = info.get("category", "")
        latest = info.get("latest_mtime", 0)
        age_str = time_ago(latest) if latest else "?"
        agents = info.get("agents", [])
        agents_str = " ".join(
            f"{CYAN if a == 'claude' else GREEN}[{a}]{R}" for a in sorted(agents)
        )
        print(f"  {WHITE}{label:30s}{R} {DIM}({category}){R}  {DIM}{scount} sessions{R}  {agents_str}  {GRAY}{age_str}{R}")

    print()
    print(f"{DIM}Details: agents topics show <topic>{R}")


def cmd_show():
    """Show sessions related to a specific topic."""
    if not topic_name:
        print(f"{RED}Usage: agents topics show <topic>{R}")
        raise SystemExit(1)

    try:
        with open(TOPICS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"{GRAY}No topics detected. Run: agents topics{R}")
        return

    topics = data.get("topics", {})
    sessions_data = data.get("sessions", {})

    # Find matching topic (case-insensitive substring)
    matched = None
    for t in topics:
        if topic_name.lower() in t.lower() or t.lower() in topic_name.lower():
            matched = t
            break
    if not matched:
        print(f"{RED}Topic not found: {topic_name}{R}")
        print(f"{DIM}Available: {', '.join(sorted(topics))}{R}")
        return

    info = topics[matched]

    print(f"{BOLD}{CYAN}Topic: {WHITE}{matched}{R}")
    print(f"{DIM}{'─' * 52}{R}")
    if info.get("description"):
        print(f"  {GRAY}{info['description']}{R}")
    print(f"  {WHITE}Category:{R}     {info.get('category', '?')}")
    print(f"  {WHITE}Sessions:{R}     {info.get('session_count', len(info.get('sessions', [])))}")
    if info.get("technologies"):
        print(f"  {WHITE}Technologies:{R} {MAGENTA}{', '.join(info['technologies'])}{R}")
    print()

    for sid in info.get("sessions", []):
        sinfo = sessions_data.get(sid, {})
        agent = sinfo.get("agent", "?")
        project = sinfo.get("project", "?")
        mtime = sinfo.get("mtime", 0)

        a_color = CYAN if agent == "claude" else GREEN
        age_str = time_ago(mtime) if mtime else "?"

        print(f"  {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R}  {GRAY}{age_str}{R}")
        short_path = project
        if len(short_path) > 35:
            short_path = "..." + short_path[-32:]
        print(f"    {BLUE}{short_path}{R}")
        other_topics = [t for t in sinfo.get("topics", []) if t.lower() != matched.lower()]
        if other_topics:
            print(f"    {DIM}also: {', '.join(other_topics[:5])}{R}")
        print()


if __name__ == "__main__":
    actions = {
        "detect": cmd_detect,
        "list": cmd_list,
        "show": cmd_show,
    }

    handler = actions.get(action)
    if handler:
        handler()
    else:
        print(f"{RED}Unknown action: {action}{R}")
        print(f"{DIM}Actions: detect, list, show{R}")
        raise SystemExit(1)
