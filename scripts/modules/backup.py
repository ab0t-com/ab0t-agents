#!/usr/bin/env python3
"""
Backup and restore coding agent session data.
Called by: agents backup [--restore FILE] [--list] [--incremental]
Env vars: ACTION (create/restore/list), TARGET (file for restore),
          INCREMENTAL (true/false), AGENT (claude/codex/all),
          PROJECT (path or "all"), CONFIRM (true/false for restore),
          CONFLICT (keep-newer/keep-backup/keep-both)
"""

import os
import sys
import json
import time
import tarfile
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from utils import (WHITE, CYAN, GREEN, YELLOW, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, human_size)

BACKUP_DIR = os.path.join(CACHE_DIR, "backups")
MANIFEST_FILE = os.path.join(BACKUP_DIR, "last_backup.json")

action = os.environ.get("ACTION", "create")
target = os.environ.get("TARGET", "")
incremental = os.environ.get("INCREMENTAL", "false") == "true"
agent_filter = os.environ.get("AGENT", "all")
project_filter = os.environ.get("PROJECT", "all")
confirm = os.environ.get("CONFIRM", "false") == "true"
conflict_mode = os.environ.get("CONFLICT", "keep-newer")  # keep-newer, keep-backup, keep-both

# Data directories to back up
DATA_DIRS = [
    ("claude_sessions", os.path.expanduser("~/.claude/projects")),
    ("claude_config", os.path.expanduser("~/.claude/settings.json")),
    ("claude_global", os.path.expanduser("~/.claude.json")),
    ("codex_sessions", os.path.expanduser("~/.codex/sessions")),
    ("codex_config", os.path.expanduser("~/.codex/config.json")),
    ("codex_history", os.path.expanduser("~/.codex/history.jsonl")),
    ("agents_cache", os.path.expanduser("~/.ab0t/.agents")),
]


def dir_size(path):
    total = 0
    if os.path.isfile(path):
        return os.path.getsize(path)
    if not os.path.isdir(path):
        return 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def count_sessions(path):
    if not os.path.isdir(path):
        return 0
    count = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.endswith(".jsonl") and not f.startswith("agent-"):
                count += 1
    return count


def load_manifest():
    try:
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_manifest(data):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def cmd_list():
    """List existing backups."""
    if not os.path.isdir(BACKUP_DIR):
        print(f"{GRAY}No backups found.{R}")
        return

    backups = []
    for f in sorted(os.listdir(BACKUP_DIR)):
        if f.startswith("agents-") and (f.endswith(".tar.gz") or f.endswith(".tar")):
            fpath = os.path.join(BACKUP_DIR, f)
            size = os.path.getsize(fpath)
            mtime = os.path.getmtime(fpath)
            backups.append((f, size, mtime))

    if not backups:
        print(f"{GRAY}No backups found in {BACKUP_DIR}{R}")
        return

    print(f"{BOLD}{CYAN}Backups{R} {DIM}({BACKUP_DIR}){R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    total = 0
    for fname, size, mtime in backups:
        total += size
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        kind = "incr" if "incr" in fname else "full"
        print(f"  {WHITE}{fname}{R}")
        print(f"    {DIM}{date_str}  {human_size(size)}  {kind}{R}")

    print()
    print(f"{DIM}Total: {human_size(total)} ({len(backups)} backups){R}")


def cmd_create():
    """Create a backup."""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Determine what to back up
    manifest = load_manifest() if incremental else {}
    last_time = manifest.get("timestamp", 0) if incremental else 0

    print(f"{BOLD}{CYAN}Creating {'incremental ' if incremental else ''}backup...{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    # Survey data
    total_size = 0
    total_files = 0
    items = []

    for label, path in DATA_DIRS:
        if not os.path.exists(path):
            continue

        # Agent filter
        if agent_filter != "all":
            if agent_filter == "claude" and "codex" in label:
                continue
            if agent_filter == "codex" and "claude" in label:
                continue

        size = dir_size(path)
        if os.path.isfile(path):
            files = 1
            sessions = 0
        else:
            files = sum(len(fs) for _, _, fs in os.walk(path))
            sessions = count_sessions(path) if "sessions" in label else 0

        items.append((label, path, size, files, sessions))
        total_size += size
        total_files += files

        size_str = human_size(size)
        if sessions > 0:
            print(f"  {WHITE}{label:20s}{R} {size_str:>8}  {DIM}({sessions} sessions){R}")
        elif files > 0:
            print(f"  {WHITE}{label:20s}{R} {size_str:>8}  {DIM}({files} files){R}")
        else:
            print(f"  {WHITE}{label:20s}{R} {size_str:>8}")

    if total_size == 0:
        print(f"\n{GRAY}Nothing to back up.{R}")
        return

    print(f"\n  {DIM}Total: {human_size(total_size)} ({total_files} files){R}")

    # Create tarball
    kind = "incr" if incremental else "full"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = f"agents-{kind}-{timestamp}.tar.gz"
    fpath = os.path.join(BACKUP_DIR, fname)

    print(f"\n{DIM}Compressing...{R}")

    files_added = 0
    with tarfile.open(fpath, "w:gz") as tar:
        for label, path, size, files, sessions in items:
            if os.path.isfile(path):
                if not incremental or os.path.getmtime(path) > last_time:
                    arcname = os.path.join(label, os.path.basename(path))
                    tar.add(path, arcname=arcname)
                    files_added += 1
            elif os.path.isdir(path):
                for root, dirs, flist in os.walk(path):
                    for f in flist:
                        full = os.path.join(root, f)
                        if incremental:
                            try:
                                if os.path.getmtime(full) <= last_time:
                                    continue
                            except OSError:
                                continue
                        rel = os.path.relpath(full, os.path.dirname(path))
                        arcname = os.path.join(label, rel)
                        tar.add(full, arcname=arcname)
                        files_added += 1

    if files_added == 0 and incremental:
        os.remove(fpath)
        print(f"\n{GREEN}No changes since last backup.{R}")
        return

    backup_size = os.path.getsize(fpath)

    # Save manifest
    save_manifest({
        "timestamp": time.time(),
        "file": fname,
        "files_count": files_added,
        "uncompressed_size": total_size,
        "compressed_size": backup_size,
    })

    print(f"\n{GREEN}{BOLD}Backup complete.{R}")
    print(f"  {WHITE}File:{R}     {fpath}")
    print(f"  {WHITE}Files:{R}    {files_added}")
    print(f"  {WHITE}Size:{R}     {human_size(backup_size)} {DIM}({human_size(total_size)} uncompressed){R}")


def resolve_restore_path(arcname):
    """Map archive label prefix back to the original filesystem path."""
    label_to_dir = {
        "claude_sessions": os.path.expanduser("~/.claude/projects"),
        "claude_config": os.path.expanduser("~/.claude"),
        "claude_global": os.path.expanduser("~"),
        "codex_sessions": os.path.expanduser("~/.codex/sessions"),
        "codex_config": os.path.expanduser("~/.codex"),
        "codex_history": os.path.expanduser("~/.codex"),
        "agents_cache": os.path.expanduser("~/.ab0t/.agents"),
    }
    parts = arcname.split("/", 1)
    label = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    base = label_to_dir.get(label)
    if not base:
        return None
    if rest:
        return os.path.join(base, rest)
    return base


def cmd_restore():
    """Restore from a backup."""
    if not target:
        # Find most recent backup
        if not os.path.isdir(BACKUP_DIR):
            print(f"{RED}No backups found.{R}")
            raise SystemExit(1)
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR)
             if f.startswith("agents-") and f.endswith(".tar.gz")],
            reverse=True,
        )
        if not backups:
            print(f"{RED}No backups found in {BACKUP_DIR}{R}")
            raise SystemExit(1)
        restore_file = os.path.join(BACKUP_DIR, backups[0])
    else:
        restore_file = target
        if not os.path.isfile(restore_file):
            restore_file = os.path.join(BACKUP_DIR, target)

    if not os.path.isfile(restore_file):
        print(f"{RED}Backup file not found: {target}{R}")
        raise SystemExit(1)

    print(f"{BOLD}{CYAN}Restore {'Preview' if not confirm else 'In Progress'}{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"  {WHITE}File:{R} {restore_file}")
    print(f"  {WHITE}Size:{R} {human_size(os.path.getsize(restore_file))}")
    print()

    with tarfile.open(restore_file, "r:gz") as tar:
        members = tar.getmembers()

        # Summary by label
        by_label = {}
        for m in members:
            label = m.name.split("/")[0] if "/" in m.name else m.name
            if label not in by_label:
                by_label[label] = 0
            by_label[label] += 1

        for label, count in sorted(by_label.items()):
            print(f"  {WHITE}{label:20s}{R} {count} files")

        print(f"\n  {DIM}Total: {len(members)} files{R}")

        if not confirm:
            print(f"\n{YELLOW}Restore would extract files to their original locations.{R}")
            print(f"{DIM}Run with --confirm to proceed. Conflict mode: {conflict_mode}{R}")
            return

        # Actually restore
        print(f"\n{DIM}Conflict mode: {conflict_mode}{R}")
        print(f"{DIM}Restoring...{R}")

        restored = 0
        skipped = 0
        conflicts = 0

        for member in members:
            if not member.isfile():
                continue
            dest = resolve_restore_path(member.name)
            if not dest:
                skipped += 1
                continue

            # Conflict resolution
            if os.path.exists(dest):
                conflicts += 1
                if conflict_mode == "keep-newer":
                    try:
                        existing_mtime = os.path.getmtime(dest)
                        backup_mtime = member.mtime
                        if existing_mtime >= backup_mtime:
                            skipped += 1
                            continue
                    except OSError:
                        pass
                elif conflict_mode == "keep-both":
                    # Rename existing with .pre-restore suffix
                    backup_path = dest + ".pre-restore"
                    try:
                        os.rename(dest, backup_path)
                    except OSError:
                        pass
                elif conflict_mode == "keep-backup":
                    pass  # overwrite existing with backup version

            # Extract
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                with tar.extractfile(member) as src:
                    if src:
                        with open(dest, "wb") as dst:
                            dst.write(src.read())
                        os.utime(dest, (member.mtime, member.mtime))
                        restored += 1
            except (OSError, KeyError) as e:
                print(f"  {RED}Failed: {member.name}: {e}{R}")
                skipped += 1

    print()
    print(f"{GREEN}{BOLD}Restore complete.{R}")
    print(f"  {WHITE}Restored:{R}  {restored} files")
    if conflicts:
        print(f"  {WHITE}Conflicts:{R} {conflicts} ({conflict_mode})")
    if skipped:
        print(f"  {WHITE}Skipped:{R}   {skipped} files")


if __name__ == "__main__":
    if action == "list":
        cmd_list()
    elif action == "restore":
        cmd_restore()
    else:
        cmd_create()
