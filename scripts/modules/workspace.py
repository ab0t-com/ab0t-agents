#!/usr/bin/env python3
"""
Session Pinning & Workspaces - group related sessions into named workspaces.
Called by: agents workspace <action> [args]
Env vars: ACTION (create/add/remove/show/list/delete),
          WS_NAME (or WORKSPACE_NAME), SESSION_KEY, NOTE_TEXT
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, time_ago, get_first_message,
                   resolve_session as _resolve_session)

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
WORKSPACES_FILE = os.path.join(CACHE_DIR, "workspaces.json")

action = os.environ.get("ACTION", "list")
workspace_name = os.environ.get("WS_NAME", os.environ.get("WORKSPACE_NAME", ""))
session_key = os.environ.get("SESSION_KEY", "")
note_text = os.environ.get("NOTE_TEXT", "")


def load_workspaces():
    try:
        with open(WORKSPACES_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_workspaces(data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(WORKSPACES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def resolve_session_id():
    """Resolve session key to (session_id, agent, project, fpath)."""
    fpath, agent, project, sid = _resolve_session(session_key, ALL_ADAPTERS)
    return sid, agent, project, fpath


def cmd_create():
    if not workspace_name:
        print(f"{RED}Usage: agents workspace create <name>{R}")
        raise SystemExit(1)
    workspaces = load_workspaces()
    if workspace_name in workspaces:
        print(f"{YELLOW}Workspace '{workspace_name}' already exists.{R}")
        raise SystemExit(1)
    workspaces[workspace_name] = {
        "sessions": [],
        "created": datetime.utcnow().isoformat() + "Z",
        "description": note_text or "",
    }
    save_workspaces(workspaces)
    print(f"{GREEN}Workspace created: {WHITE}{workspace_name}{R}")
    if note_text:
        print(f"  {GRAY}{note_text}{R}")


def cmd_add():
    if not workspace_name or not session_key:
        print(f"{RED}Usage: agents workspace add <workspace> <session>{R}")
        raise SystemExit(1)
    workspaces = load_workspaces()
    if workspace_name not in workspaces:
        print(f"{RED}Workspace not found: {workspace_name}{R}")
        print(f"{DIM}Create it first: agents workspace create {workspace_name}{R}")
        raise SystemExit(1)
    sid, agent, project, fpath = resolve_session_id()
    if not sid:
        print(f"{RED}Could not find session: {session_key}{R}")
        raise SystemExit(1)
    ws = workspaces[workspace_name]
    # Check for duplicates
    for s in ws["sessions"]:
        if s["session_id"] == sid:
            print(f"{GRAY}Session already in workspace.{R}")
            return
    ws["sessions"].append({
        "session_id": sid,
        "agent": agent,
        "project": project,
        "file": fpath,
        "added": datetime.utcnow().isoformat() + "Z",
        "label": note_text or "",
    })
    save_workspaces(workspaces)
    a_color = CYAN if agent == "claude" else GREEN
    print(f"{GREEN}Added{R} {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R} to workspace {BOLD}{workspace_name}{R}")


def cmd_remove():
    if not workspace_name or not session_key:
        print(f"{RED}Usage: agents workspace remove <workspace> <session>{R}")
        raise SystemExit(1)
    workspaces = load_workspaces()
    if workspace_name not in workspaces:
        print(f"{RED}Workspace not found: {workspace_name}{R}")
        raise SystemExit(1)
    sid, _, _, _ = resolve_session_id()
    if not sid:
        sid = session_key  # Try direct match
    ws = workspaces[workspace_name]
    original_len = len(ws["sessions"])
    ws["sessions"] = [s for s in ws["sessions"] if not s["session_id"].startswith(sid)]
    if len(ws["sessions"]) < original_len:
        save_workspaces(workspaces)
        print(f"{GREEN}Removed{R} {WHITE}{sid[:8]}{R} from workspace {BOLD}{workspace_name}{R}")
    else:
        print(f"{GRAY}Session not found in workspace.{R}")


def cmd_show():
    if not workspace_name:
        print(f"{RED}Usage: agents workspace show <name>{R}")
        raise SystemExit(1)
    workspaces = load_workspaces()
    if workspace_name not in workspaces:
        print(f"{RED}Workspace not found: {workspace_name}{R}")
        raise SystemExit(1)
    ws = workspaces[workspace_name]
    sessions = ws.get("sessions", [])

    print(f"{BOLD}{CYAN}Workspace: {WHITE}{workspace_name}{R} {DIM}({len(sessions)} sessions){R}")
    print(f"{DIM}{'─' * 52}{R}")
    if ws.get("description"):
        print(f"  {GRAY}{ws['description']}{R}")
    print()

    if not sessions:
        print(f"  {GRAY}No sessions. Add one: agents workspace add {workspace_name} <session>{R}")
        print()
        return

    for i, s in enumerate(sessions, 1):
        sid = s["session_id"]
        agent = s.get("agent", "?")
        project = s.get("project", "")
        fpath = s.get("file", "")
        label = s.get("label", "")
        a_color = CYAN if agent == "claude" else GREEN

        # Get live mtime if file exists
        mtime_str = ""
        if fpath and os.path.isfile(fpath):
            try:
                mtime = os.path.getmtime(fpath)
                mtime_str = time_ago(mtime)
            except OSError:
                pass

        # Get preview
        preview = ""
        if fpath and os.path.isfile(fpath):
            preview = get_first_message(fpath, agent)

        short_path = project
        if len(short_path) > 30:
            short_path = "..." + short_path[-27:]

        print(f"  {YELLOW}[{i}]{R} {a_color}[{agent}]{R} {WHITE}{sid[:8]}{R}", end="")
        if mtime_str:
            print(f"  {DIM}{mtime_str}{R}", end="")
        print()
        if short_path:
            print(f"      {BLUE}{short_path}{R}")
        if label:
            print(f"      {MAGENTA}{label}{R}")
        elif preview:
            print(f"      {GRAY}\"{preview[:50]}\"{R}")

    print()
    print(f"{DIM}Resume: agents resume <num> (after 'agents show' in project){R}")


def cmd_list():
    workspaces = load_workspaces()
    if not workspaces:
        print(f"{GRAY}No workspaces. Create one: agents workspace create <name>{R}")
        return

    print(f"{BOLD}{CYAN}Workspaces{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    for name, ws in sorted(workspaces.items()):
        sessions = ws.get("sessions", [])
        desc = ws.get("description", "")

        # Count agents
        agents = set(s.get("agent", "") for s in sessions)
        agents_str = " ".join(
            f"{CYAN if a == 'claude' else GREEN}[{a}]{R}" for a in sorted(agents) if a
        )

        print(f"  {WHITE}{name}{R}  {DIM}({len(sessions)} sessions){R} {agents_str}")
        if desc:
            print(f"    {GRAY}{desc[:50]}{R}")

    print()
    print(f"{DIM}Usage: agents workspace show <name>{R}")


def cmd_delete():
    if not workspace_name:
        print(f"{RED}Usage: agents workspace delete <name>{R}")
        raise SystemExit(1)
    workspaces = load_workspaces()
    if workspace_name not in workspaces:
        print(f"{RED}Workspace not found: {workspace_name}{R}")
        raise SystemExit(1)
    del workspaces[workspace_name]
    save_workspaces(workspaces)
    print(f"{GREEN}Deleted workspace: {WHITE}{workspace_name}{R}")


if __name__ == "__main__":
    actions = {
        "create": cmd_create,
        "add": cmd_add,
        "remove": cmd_remove,
        "show": cmd_show,
        "list": cmd_list,
        "delete": cmd_delete,
    }

    handler = actions.get(action)
    if handler:
        handler()
    else:
        print(f"{RED}Unknown action: {action}{R}")
        print(f"{DIM}Actions: create, add, remove, show, list, delete{R}")
        raise SystemExit(1)
