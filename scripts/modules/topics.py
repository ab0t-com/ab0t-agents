#!/usr/bin/env python3
"""
Topic Modeling - detect topics within and across sessions.
Called by: agents topics [--project PATH]
Env vars: ACTION (detect/list/show), PROJECT (path), TOPIC_NAME
"""

import os
import sys
import json
import re
import time
import math
from collections import Counter, defaultdict
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
TOPICS_FILE = os.path.join(CACHE_DIR, "topics.json")

action = os.environ.get("ACTION", "detect")
project_filter = os.environ.get("PROJECT", "all")
topic_name = os.environ.get("TOPIC_NAME", "")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]

# Stop words to filter
STOP_WORDS = set("""
a an the is was were be been being have has had do does did will would shall
should may might can could am are it its this that these those i me my mine
we our us you your he him his she her they them their what which who whom
how when where why all each every both few many some any no not only very
just also than too so if or and but for with from by at in on to of as
""".split())

# Technical stop words (common but not topic-bearing)
TECH_STOP = set("""
file files code function method class import return true false null none
error line number string int type value key data list dict set
var let const def self cls args kwargs print run test check get
""".split())


def extract_terms(text):
    """Extract meaningful terms from text."""
    # Tokenize: split on non-alphanumeric, keep meaningful tokens
    tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', text.lower())
    # Filter stop words and very short tokens
    return [t for t in tokens if t not in STOP_WORDS and t not in TECH_STOP and len(t) > 2]


def extract_session_terms(fpath, agent_name):
    """Extract all meaningful terms from a session file."""
    terms = Counter()
    msg_count = 0
    first_ts = None
    last_ts = None

    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    ts_str = d.get("timestamp")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                            if first_ts is None or ts < first_ts:
                                first_ts = ts
                            if last_ts is None or ts > last_ts:
                                last_ts = ts
                        except ValueError:
                            pass

                    text = ""
                    if agent_name == "claude":
                        if d.get("type") == "user":
                            content = d.get("message", {}).get("content", "")
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                text = " ".join(
                                    item.get("text", "")
                                    for item in content
                                    if isinstance(item, dict) and item.get("type") == "text"
                                )
                        elif d.get("type") == "assistant":
                            content = d.get("message", {}).get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text += " " + item.get("text", "")
                    elif agent_name == "codex":
                        if d.get("type") == "response_item":
                            p = d.get("payload", d.get("item", {}))
                            content = p.get("content", [])
                            if isinstance(content, list):
                                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))

                    if text:
                        msg_count += 1
                        session_terms = extract_terms(text)
                        terms.update(session_terms)

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    return terms, msg_count, first_ts, last_ts


def detect_topics(term_counts, top_n=5):
    """Detect top topics from term frequency using TF weighting."""
    if not term_counts:
        return []
    # Filter to meaningful terms (appeared at least 3 times)
    meaningful = {t: c for t, c in term_counts.items() if c >= 3}
    if not meaningful:
        meaningful = dict(term_counts.most_common(top_n))
    # Score: frequency weighted by term length (longer = more specific)
    scored = {}
    for term, count in meaningful.items():
        specificity = min(2.0, len(term) / 5.0)
        scored[term] = count * specificity
    return sorted(scored, key=scored.get, reverse=True)[:top_n]


def cluster_topics(all_sessions_topics):
    """Cluster sessions by shared topics into topic threads."""
    # Build topic → sessions mapping
    topic_sessions = defaultdict(list)
    for sid, info in all_sessions_topics.items():
        for topic in info["topics"]:
            topic_sessions[topic].append(sid)

    # Merge closely related topics (e.g., "auth" and "authentication")
    merged = {}
    for topic in sorted(topic_sessions, key=lambda t: -len(topic_sessions[t])):
        # Check if this topic is a prefix/suffix of an existing merged topic
        found = False
        for existing in merged:
            if topic in existing or existing in topic:
                merged[existing].update(topic_sessions[topic])
                found = True
                break
        if not found:
            merged[topic] = set(topic_sessions[topic])

    return merged


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


def fmt_duration(s):
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h, m = divmod(s, 3600)
    m = m // 60
    return f"{h}h {m}m" if m else f"{h}h"


def cmd_detect():
    """Scan sessions and detect topics."""
    print(f"{BOLD}{CYAN}Detecting Topics...{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    all_sessions = {}
    now = time.time()
    week_ago = now - 604800

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            if project_filter != "all" and not display_path.startswith(project_filter):
                continue

            sid = os.path.basename(fpath).replace(".jsonl", "")
            terms, msg_count, first_ts, last_ts = extract_session_terms(fpath, adapter.name)

            if msg_count < 2:
                continue

            topics = detect_topics(terms)
            if topics:
                all_sessions[sid] = {
                    "topics": topics,
                    "terms": terms,
                    "agent": adapter.name,
                    "project": display_path,
                    "mtime": mtime,
                    "first_ts": first_ts,
                    "last_ts": last_ts,
                    "msg_count": msg_count,
                }

    if not all_sessions:
        print(f"  {GRAY}No sessions with detectable topics.{R}")
        return

    # Cluster into topic threads
    clusters = cluster_topics(all_sessions)

    # Filter to topics with 2+ sessions or very recent
    significant = {}
    for topic, sids in sorted(clusters.items(), key=lambda x: -len(x[1])):
        if len(sids) >= 2 or any(all_sessions.get(s, {}).get("mtime", 0) > week_ago for s in sids):
            significant[topic] = sids

    # Save topics index
    topics_data = {
        "topics": {},
        "sessions": {},
        "scanned_at": datetime.utcnow().isoformat() + "Z",
    }
    for topic, sids in significant.items():
        latest_mtime = max(all_sessions[s]["mtime"] for s in sids if s in all_sessions)
        projects = set(all_sessions[s]["project"] for s in sids if s in all_sessions)
        agents = set(all_sessions[s]["agent"] for s in sids if s in all_sessions)
        total_time = sum(
            (all_sessions[s].get("last_ts", 0) or 0) - (all_sessions[s].get("first_ts", 0) or 0)
            for s in sids if s in all_sessions
        )
        topics_data["topics"][topic] = {
            "sessions": list(sids),
            "projects": list(projects),
            "agents": list(agents),
            "latest_mtime": latest_mtime,
            "total_time": max(0, total_time),
        }
    for sid, info in all_sessions.items():
        topics_data["sessions"][sid] = {
            "topics": info["topics"],
            "agent": info["agent"],
            "project": info["project"],
            "mtime": info["mtime"],
        }

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(TOPICS_FILE, "w") as f:
        json.dump(topics_data, f, indent=2)

    # Display
    print(f"{BOLD}Recent Topics{R} {DIM}({len(significant)} detected from {len(all_sessions)} sessions){R}")
    print()

    for topic, sids in sorted(significant.items(), key=lambda x: -max(
        all_sessions.get(s, {}).get("mtime", 0) for s in x[1]
    ))[:15]:
        session_count = len(sids)
        projects = set(all_sessions[s]["project"] for s in sids if s in all_sessions)
        agents = set(all_sessions[s]["agent"] for s in sids if s in all_sessions)
        latest = max(all_sessions[s]["mtime"] for s in sids if s in all_sessions)

        agents_str = " ".join(
            f"{CYAN if a == 'claude' else GREEN}[{a}]{R}" for a in sorted(agents)
        )
        age_str = time_ago(latest)
        age_color = GREEN if (now - latest) < 86400 else (YELLOW if (now - latest) < 604800 else GRAY)

        print(f"  {WHITE}{topic}{R}  {DIM}{session_count} session{'s' if session_count != 1 else ''}, "
              f"{len(projects)} project{'s' if len(projects) != 1 else ''}{R}  {agents_str}")
        print(f"    Last: {age_color}{age_str}{R}", end="")
        # Show project names
        for p in list(projects)[:3]:
            short = os.path.basename(p) if p else "?"
            print(f"  {BLUE}{short}{R}", end="")
        if len(projects) > 3:
            print(f" {DIM}+{len(projects) - 3} more{R}", end="")
        print()
        print()

    print(f"{DIM}Saved to {TOPICS_FILE}{R}")


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

    for topic, info in sorted(topics.items(), key=lambda x: -x[1].get("latest_mtime", 0)):
        scount = len(info["sessions"])
        pcount = len(info["projects"])
        latest = info.get("latest_mtime", 0)
        age_str = time_ago(latest) if latest else "?"
        agents_str = " ".join(
            f"{CYAN if a == 'claude' else GREEN}[{a}]{R}" for a in info.get("agents", [])
        )
        print(f"  {WHITE}{topic:20s}{R} {DIM}{scount} sessions, {pcount} projects{R}  {agents_str}  {GRAY}{age_str}{R}")

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

    # Find matching topic (substring match)
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
    now = time.time()

    print(f"{BOLD}{CYAN}Topic: {WHITE}{matched}{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"  {WHITE}Sessions:{R} {len(info['sessions'])}")
    print(f"  {WHITE}Projects:{R} {', '.join(info.get('projects', []))}")
    print()

    for sid in info["sessions"]:
        sinfo = sessions_data.get(sid, {})
        agent = sinfo.get("agent", "?")
        project = sinfo.get("project", "?")
        mtime = sinfo.get("mtime", 0)
        topics_list = sinfo.get("topics", [])

        a_color = CYAN if agent == "claude" else GREEN
        age_str = time_ago(mtime) if mtime else "?"

        print(f"  {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R}  {GRAY}{age_str}{R}")
        short_path = project
        if len(short_path) > 35:
            short_path = "..." + short_path[-32:]
        print(f"    {BLUE}{short_path}{R}")
        other_topics = [t for t in topics_list if t != matched]
        if other_topics:
            print(f"    {DIM}also: {', '.join(other_topics[:5])}{R}")
        print()


# Dispatch
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
