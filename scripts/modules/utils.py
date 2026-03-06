#!/usr/bin/env python3
"""
Shared utilities for agents CLI modules.
Provides: ANSI colors, time formatting, JSON I/O, session resolution, text extraction.

Does NOT own the adapter layer — modules import adapters directly.
Session resolution functions accept adapters as parameters to stay decoupled.
"""

import os
import sys
import json
import time
from datetime import datetime

# ── ANSI color constants ───────────────────────────────────

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

AGENT_COLORS = {"claude": CYAN, "codex": GREEN}


def agent_color(name):
    """Get the ANSI color for an agent name."""
    return AGENT_COLORS.get(name, GRAY)


# ── Paths ──────────────────────────────────────────────────

CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")


def ensure_cache_dir():
    """Create the cache directory if it doesn't exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)


# ── Time formatting ────────────────────────────────────────

def time_ago(ts):
    """Human-friendly relative time from a unix timestamp."""
    s = int(time.time() - ts)
    if s < 5:
        return "just now"
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    if s < 604800:
        return f"{s // 86400}d ago"
    return f"{s // 604800}w ago"


def fmt_duration(seconds):
    """Format seconds as Xh Ym Zs."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m}m {s}s" if s else f"{m}m"
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"


def human_size(n):
    """Format bytes as K/M/G."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}G"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return f"{n}B"


# ── JSON I/O ───────────────────────────────────────────────

def load_json(path, default=None):
    """Safely load a JSON file. Returns default on any error."""
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return default


def save_json(path, data, indent=2):
    """Safely write a JSON file, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent)


# ── Session resolution ─────────────────────────────────────

def resolve_session(session_key, adapters):
    """Resolve a numeric key or session ID prefix to (fpath, agent_name, project, session_id).

    Args:
        session_key: Numeric index (1-based) or session ID prefix/substring
        adapters: List of adapter instances to search through

    Returns ("", "", "", "") if not found.
    """
    cache_file = os.path.join(CACHE_DIR, "sessions_cache.json")

    # Try numeric resolution from cache
    if session_key.isdigit() and os.path.isfile(cache_file):
        try:
            with open(cache_file) as f:
                sessions = json.load(f)
            idx = int(session_key) - 1
            if 0 <= idx < len(sessions):
                s = sessions[idx]
                fpath = s.get("file", "")
                agent = s.get("agent", "claude")
                project = s.get("path", "")
                sid = s.get("session_id", os.path.basename(fpath).replace(".jsonl", ""))
                return fpath, agent, project, sid
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    # Try matching by session ID prefix/substring
    for adapter in adapters:
        if not adapter.is_available():
            continue
        for display, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            basename = os.path.basename(fpath).replace(".jsonl", "")
            if basename.startswith(session_key) or session_key in basename:
                return fpath, adapter.name, display, basename

    return "", "", "", ""


# ── Text extraction ────────────────────────────────────────

def extract_text_content(content):
    """Extract plain text from a Claude/Codex content field.
    Handles both string content and list-of-blocks content.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return " ".join(parts)
    return ""


def get_first_message(fpath, agent_name):
    """Extract the first user message preview from a session file."""
    try:
        with open(fpath) as f:
            for i, line in enumerate(f):
                if i > 50:
                    break
                try:
                    d = json.loads(line)
                    if agent_name == "claude" and d.get("type") == "user":
                        content = d.get("message", {}).get("content", "")
                        text = extract_text_content(content)
                        if text:
                            return " ".join(text.split())[:80]
                    elif agent_name == "codex" and d.get("type") == "response_item":
                        p = d.get("payload", d.get("item", {}))
                        if p.get("role") == "user":
                            content = p.get("content", [])
                            text = extract_text_content(content)
                            if text:
                                return " ".join(text.split())[:80]
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    return ""


def extract_text_from_record(record, agent_name):
    """Extract text content from a single JSONL record dict.
    Returns (role, text) tuple or (None, None) if not a text record.
    """
    rec_type = record.get("type", "")

    if agent_name == "claude":
        if rec_type == "user":
            content = record.get("message", {}).get("content", "")
            text = extract_text_content(content)
            return ("user", text) if text else (None, None)
        elif rec_type == "assistant":
            content = record.get("message", {}).get("content", [])
            text = extract_text_content(content)
            return ("assistant", text) if text else (None, None)

    elif agent_name == "codex":
        if rec_type == "response_item":
            p = record.get("payload", record.get("item", {}))
            role = p.get("role", "")
            content = p.get("content", [])
            text = extract_text_content(content)
            if text and role in ("user", "assistant"):
                return (role, text)

    return (None, None)


# ── Session cache auto-build ──────────────────────────────

def ensure_sessions_cache(adapters):
    """Build sessions_cache.json if it doesn't exist.

    Args:
        adapters: List of adapter instances to gather sessions from
    """
    cache_file = os.path.join(CACHE_DIR, "sessions_cache.json")
    if os.path.isfile(cache_file):
        return cache_file

    sessions = []
    for adapter in adapters:
        if not adapter.is_available():
            continue
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            sid = os.path.basename(fpath).replace(".jsonl", "")
            sessions.append({
                "session_id": sid,
                "agent": adapter.name,
                "path": display_path,
                "file": fpath,
                "mtime": mtime,
            })

    sessions.sort(key=lambda s: -s["mtime"])
    ensure_cache_dir()
    with open(cache_file, "w") as f:
        json.dump(sessions, f)

    return cache_file


# ── Print helpers ──────────────────────────────────────────

def header(title, width=52):
    """Print a standard module header."""
    print(f"{BOLD}{CYAN}{title}{R}")
    print(f"{DIM}{'─' * width}{R}")
    print()


def error(msg):
    """Print an error message and exit."""
    print(f"{RED}{msg}{R}")
    raise SystemExit(1)
