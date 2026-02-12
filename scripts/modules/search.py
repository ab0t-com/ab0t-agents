#!/usr/bin/env python3
"""
Full-text search across all coding agent sessions.
Called by: agents search <query>
Env vars: QUERY, CASE_SENSITIVE (true/false), MAX_RESULTS (int)
"""

import os
import sys
import re
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

query = os.environ.get("QUERY", "")
case_sensitive = os.environ.get("CASE_SENSITIVE", "false") == "true"
max_results = int(os.environ.get("MAX_RESULTS", "20"))

if not query:
    print("Usage: agents search <query>")
    raise SystemExit(1)

# ANSI
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

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
now = time.time()


def time_ago(ts):
    s = int(now - ts)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    if s < 604800:
        return f"{s // 86400}d ago"
    return f"{s // 604800}w ago"


def highlight(text, pattern, flags):
    """Highlight matching portions of text."""
    def replacer(m):
        return f"{RED}{BOLD}{m.group()}{R}"
    return re.sub(pattern, replacer, text, flags=flags)


def extract_text_from_record(d, agent_name):
    """Extract user-visible text from a session record."""
    texts = []
    rec_type = d.get("type", "")

    if agent_name == "claude":
        if rec_type == "user":
            content = d.get("message", {}).get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text", ""))
        elif rec_type == "assistant":
            msg = d.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text", ""))
        elif rec_type == "summary":
            texts.append(d.get("summary", ""))

    elif agent_name == "codex":
        if rec_type == "response_item":
            p = d.get("payload", {})
            for item in p.get("content", []):
                if isinstance(item, dict):
                    texts.append(item.get("text", ""))

    return texts


# Build regex pattern
flags = 0 if case_sensitive else re.IGNORECASE
try:
    pattern = re.compile(query, flags)
except re.error:
    pattern = re.compile(re.escape(query), flags)

print(f"{BOLD}{CYAN}Search: {WHITE}{query}{R}")
print(f"{DIM}{'─' * 52}{R}")
print()

results = []  # (mtime, display_path, agent_name, session_id, matches)

for adapter in ALL_ADAPTERS:
    if not adapter.is_available():
        continue

    for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
        if is_agent:
            continue

        session_matches = []
        try:
            with open(fpath) as f:
                for i, line in enumerate(f):
                    if len(session_matches) >= 3:
                        break
                    try:
                        d = json.loads(line)
                        for text in extract_text_from_record(d, adapter.name):
                            if pattern.search(text):
                                # Clean and truncate the match context
                                clean = " ".join(text.split())
                                # Find match position and show context around it
                                m = pattern.search(clean)
                                if m:
                                    start = max(0, m.start() - 40)
                                    end = min(len(clean), m.end() + 40)
                                    snippet = clean[start:end]
                                    if start > 0:
                                        snippet = "..." + snippet
                                    if end < len(clean):
                                        snippet = snippet + "..."
                                    session_matches.append(snippet)
                                break
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
        except OSError:
            continue

        if session_matches:
            sid = os.path.basename(fpath).replace(".jsonl", "")
            # For codex, get session ID from meta
            if adapter.name == "codex":
                try:
                    with open(fpath) as f:
                        first = json.loads(f.readline())
                        if first.get("type") == "session_meta":
                            sid = first.get("payload", {}).get("id", sid)
                except (OSError, json.JSONDecodeError):
                    pass
            results.append((mtime, display_path, adapter.name, sid, session_matches))

# Sort by recency
results.sort(key=lambda x: -x[0])

if not results:
    print(f"{GRAY}No matches found.{R}")
    raise SystemExit(0)

shown = 0
for mtime, display_path, aname, sid, matches in results:
    if shown >= max_results:
        break
    shown += 1

    a_color = CYAN if aname == "claude" else GREEN
    age_str = time_ago(mtime)
    age_color = GREEN if (now - mtime) < 3600 else (YELLOW if (now - mtime) < 86400 else GRAY)

    print(f"  {a_color}[{aname}]{R} {YELLOW}{display_path}{R}  {age_color}{age_str}{R}")
    print(f"  {DIM}session {MAGENTA}{sid[:8]}{R}")
    for snippet in matches[:2]:
        highlighted = highlight(snippet, pattern, flags)
        print(f"    {GRAY}\"{R}{highlighted}{GRAY}\"{R}")
    print()

remaining = len(results) - shown
print(f"{DIM}{'─' * 52}{R}")
print(f"{BOLD}{shown}{R} match{'es' if shown != 1 else ''} across {len(set(r[1] for r in results))} project{'s' if len(set(r[1] for r in results)) != 1 else ''}", end="")
if remaining > 0:
    print(f" {DIM}({remaining} more, use --max N){R}")
else:
    print()
