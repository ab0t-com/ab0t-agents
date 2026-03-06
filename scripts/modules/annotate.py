#!/usr/bin/env python3
"""
Session annotations, tags, bookmarks, and stars.
Called by: agents tag|note|star|untag|unstar|bookmarks <session> [args]
Env vars: ACTION (tag/untag/note/star/unstar/list-tags/show/bookmarks),
          SESSION_KEY, TAGS (comma-sep), NOTE_TEXT, BOOKMARK_MSG (int)
"""

import os
import sys
import json
import re
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR)
ANNOTATIONS_FILE = os.path.join(CACHE_DIR, "annotations.json")

action = os.environ.get("ACTION", "show")
session_key = os.environ.get("SESSION_KEY", "")
tags_str = os.environ.get("TAGS", "")
note_text = os.environ.get("NOTE_TEXT", "")
bookmark_msg = os.environ.get("BOOKMARK_MSG", "")


def load_annotations():
    try:
        with open(ANNOTATIONS_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_annotations(data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(ANNOTATIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def resolve_session_id():
    """Resolve session key to a stable session ID."""
    cache_file = os.path.join(CACHE_DIR, "sessions_cache.json")
    if session_key.isdigit() and os.path.isfile(cache_file):
        try:
            with open(cache_file) as f:
                sessions = json.load(f)
            idx = int(session_key) - 1
            if 0 <= idx < len(sessions):
                s = sessions[idx]
                return s.get("session_id", ""), s.get("agent", "claude"), s.get("path", "")
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    # Try as direct session ID
    for adapter in [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]:
        if not adapter.is_available():
            continue
        for display, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            basename = os.path.basename(fpath).replace(".jsonl", "")
            if basename.startswith(session_key) or session_key in basename:
                return basename, adapter.name, display
    return "", "", ""


def get_annotation(annotations, sid):
    if sid not in annotations:
        annotations[sid] = {
            "tags": [],
            "notes": [],
            "bookmarks": [],
            "starred": False,
            "created": datetime.utcnow().isoformat() + "Z",
        }
    return annotations[sid]


def time_ago(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        s = int(time.time() - dt.timestamp())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except (ValueError, TypeError):
        return ""


def cmd_tag():
    if not session_key or not tags_str:
        print(f"{RED}Usage: agents tag <session> <tag1,tag2,...>{R}")
        raise SystemExit(1)
    sid, agent, project = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    ann = get_annotation(annotations, sid)
    # Accept both comma-separated and space-separated tags
    new_tags = [t.strip().lower() for t in re.split(r'[,\s]+', tags_str) if t.strip()]
    added = []
    for tag in new_tags:
        if tag not in ann["tags"]:
            ann["tags"].append(tag)
            added.append(tag)
    save_annotations(annotations)
    if added:
        tag_display = " ".join(f"{MAGENTA}#{t}{R}" for t in added)
        print(f"{GREEN}Tagged{R} {WHITE}{sid[:8]}{R} with {tag_display}")
    else:
        print(f"{GRAY}Session already has those tags.{R}")


def cmd_untag():
    if not session_key or not tags_str:
        print(f"{RED}Usage: agents untag <session> <tag1,tag2,...>{R}")
        raise SystemExit(1)
    sid, _, _ = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    if sid not in annotations:
        print(f"{GRAY}Session has no annotations.{R}")
        return
    ann = annotations[sid]
    remove_tags = [t.strip().lower() for t in re.split(r'[,\s]+', tags_str) if t.strip()]
    removed = []
    for tag in remove_tags:
        if tag in ann["tags"]:
            ann["tags"].remove(tag)
            removed.append(tag)
    save_annotations(annotations)
    if removed:
        print(f"{GREEN}Removed{R} tags: {', '.join(removed)} from {WHITE}{sid[:8]}{R}")
    else:
        print(f"{GRAY}Tags not found on session.{R}")


def cmd_note():
    if not session_key or not note_text:
        print(f"{RED}Usage: agents note <session> \"your note here\"{R}")
        raise SystemExit(1)
    sid, _, _ = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    ann = get_annotation(annotations, sid)
    ann["notes"].append({
        "text": note_text,
        "created": datetime.utcnow().isoformat() + "Z",
    })
    save_annotations(annotations)
    print(f"{GREEN}Note added{R} to {WHITE}{sid[:8]}{R}")
    print(f"  {GRAY}\"{note_text}\"{R}")


def cmd_star():
    if not session_key:
        print(f"{RED}Usage: agents star <session>{R}")
        raise SystemExit(1)
    sid, _, _ = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    ann = get_annotation(annotations, sid)
    ann["starred"] = True
    save_annotations(annotations)
    print(f"{YELLOW}Starred{R} {WHITE}{sid[:8]}{R}")


def cmd_unstar():
    if not session_key:
        print(f"{RED}Usage: agents unstar <session>{R}")
        raise SystemExit(1)
    sid, _, _ = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    if sid in annotations:
        annotations[sid]["starred"] = False
        save_annotations(annotations)
    print(f"{GREEN}Unstarred{R} {WHITE}{sid[:8]}{R}")


def cmd_bookmark():
    if not session_key or not bookmark_msg:
        print(f"{RED}Usage: agents bookmark <session> <msg-num> [note]{R}")
        raise SystemExit(1)
    sid, _, _ = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    ann = get_annotation(annotations, sid)
    ann["bookmarks"].append({
        "message": int(bookmark_msg),
        "note": note_text or "",
        "created": datetime.utcnow().isoformat() + "Z",
    })
    save_annotations(annotations)
    print(f"{GREEN}Bookmarked{R} message {WHITE}{bookmark_msg}{R} in {WHITE}{sid[:8]}{R}")


def cmd_show():
    """Show annotations for a specific session."""
    if not session_key:
        print(f"{RED}Usage: agents annotate show <session>{R}")
        raise SystemExit(1)
    sid, agent, project = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    annotations = load_annotations()
    if sid not in annotations:
        print(f"{GRAY}No annotations for session {sid[:8]}.{R}")
        return
    ann = annotations[sid]
    a_color = CYAN if agent == "claude" else GREEN
    print(f"{BOLD}{CYAN}Annotations{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"  {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R}", end="")
    if ann.get("starred"):
        print(f"  {YELLOW}★{R}", end="")
    print()
    if project:
        print(f"  {BLUE}{project}{R}")
    print()
    if ann.get("tags"):
        tags_display = " ".join(f"{MAGENTA}#{t}{R}" for t in ann["tags"])
        print(f"  {BOLD}Tags:{R} {tags_display}")
    if ann.get("notes"):
        print(f"  {BOLD}Notes:{R}")
        for n in ann["notes"]:
            age = time_ago(n.get("created", ""))
            print(f"    {GRAY}{age}{R} {n['text']}")
    if ann.get("bookmarks"):
        print(f"  {BOLD}Bookmarks:{R}")
        for b in ann["bookmarks"]:
            note = f" - {b['note']}" if b.get("note") else ""
            print(f"    {YELLOW}msg {b['message']}{R}{note}")
    print()


def cmd_list_tags():
    """List all tags across all annotated sessions."""
    annotations = load_annotations()
    tag_counts = {}
    for sid, ann in annotations.items():
        for tag in ann.get("tags", []):
            if tag not in tag_counts:
                tag_counts[tag] = []
            tag_counts[tag].append(sid)
    if not tag_counts:
        print(f"{GRAY}No tags yet. Tag a session: agents tag <session> <tag>{R}")
        return
    print(f"{BOLD}{CYAN}All Tags{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()
    for tag in sorted(tag_counts, key=lambda t: -len(tag_counts[t])):
        sids = tag_counts[tag]
        print(f"  {MAGENTA}#{tag}{R}  {DIM}({len(sids)} session{'s' if len(sids) != 1 else ''}){R}")
    print()
    print(f"{DIM}Filter: agents list --tag <tag>{R}")


def cmd_starred():
    """List all starred sessions."""
    annotations = load_annotations()
    starred = [(sid, ann) for sid, ann in annotations.items() if ann.get("starred")]
    if not starred:
        print(f"{GRAY}No starred sessions. Star one: agents star <session>{R}")
        return
    print(f"{BOLD}{CYAN}Starred Sessions{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()
    # Try to enrich with session cache info
    cache_file = os.path.join(CACHE_DIR, "sessions_cache.json")
    session_info = {}
    try:
        with open(cache_file) as f:
            for s in json.load(f):
                session_info[s.get("session_id", "")] = s
    except (OSError, json.JSONDecodeError):
        pass
    for sid, ann in starred:
        info = session_info.get(sid, {})
        agent = info.get("agent", "?")
        path = info.get("path", "")
        a_color = CYAN if agent == "claude" else GREEN if agent == "codex" else GRAY
        print(f"  {YELLOW}★{R} {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R}", end="")
        if path:
            print(f"  {BLUE}{path}{R}", end="")
        print()
        if ann.get("tags"):
            tags_display = " ".join(f"{MAGENTA}#{t}{R}" for t in ann["tags"])
            print(f"    {tags_display}")
        if ann.get("notes"):
            latest = ann["notes"][-1]
            print(f"    {GRAY}\"{latest['text'][:50]}\"{R}")
    print()


if __name__ == "__main__":
    actions = {
        "tag": cmd_tag,
        "untag": cmd_untag,
        "note": cmd_note,
        "star": cmd_star,
        "unstar": cmd_unstar,
        "bookmark": cmd_bookmark,
        "show": cmd_show,
        "list-tags": cmd_list_tags,
        "starred": cmd_starred,
    }

    handler = actions.get(action)
    if handler:
        handler()
    else:
        print(f"{RED}Unknown action: {action}{R}")
        print(f"{DIM}Actions: tag, untag, note, star, unstar, bookmark, show, list-tags, starred{R}")
        raise SystemExit(1)
