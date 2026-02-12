"""Adapter for Claude Code sessions stored in ~/.claude/projects/."""

import os
import json
import itertools
from datetime import datetime
from .base import BaseAdapter, SessionInfo

# Shared cache with the bash agents script
_CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")
_CACHE_FILE = os.path.join(_CACHE_DIR, "decode_cache")


def _load_decode_cache():
    """Load the shared decode cache (encoded|path lines)."""
    cache = {}
    try:
        with open(_CACHE_FILE) as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    key, val = line.split("|", 1)
                    cache[key] = val
    except OSError:
        pass
    return cache


def _save_to_cache(encoded, decoded):
    """Append a resolved mapping to the shared cache."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_CACHE_FILE, "a") as f:
            f.write(f"{encoded}|{decoded}\n")
    except OSError:
        pass


def _generate_segment_candidates(parts):
    """Generate candidate dir names by joining parts with _, ., or -."""
    if len(parts) == 1:
        return list(parts)
    candidates = []
    # Common uniform patterns first
    candidates.append("_".join(parts))
    candidates.append(".".join(parts))
    candidates.append("-".join(parts))
    # Mixed separators for small segment counts
    if len(parts) > 2 and len(parts) <= 4:
        seps = ["_", ".", "-"]
        for combo in itertools.product(seps, repeat=len(parts) - 1):
            result = parts[0]
            for i, sep in enumerate(combo):
                result += sep + parts[i + 1]
            if result not in candidates:
                candidates.append(result)
    return candidates


def _find_real_path(encoded):
    """Resolve an encoded project dir name to its real filesystem path.

    Claude Code encodes paths by replacing /, _, . and @ with -.
    This is ambiguous, so we walk the filesystem to find which path
    actually exists.
    """
    if encoded.startswith("-"):
        encoded = encoded[1:]

    parts = encoded.split("-")

    def recurse(current, remaining):
        if not remaining:
            return current if os.path.exists(current) else None

        for n in range(1, len(remaining) + 1):
            seg_parts = remaining[:n]
            rest = remaining[n:]

            if n == 1:
                candidates = [seg_parts[0]]
            else:
                candidates = _generate_segment_candidates(seg_parts)

            for cand in candidates:
                tests = [cand]
                if not cand.startswith("."):
                    tests.append("." + cand)

                for t in tests:
                    test_path = os.path.join(current, t) if current else "/" + t
                    if os.path.exists(test_path):
                        if not rest:
                            return test_path
                        result = recurse(test_path, rest)
                        if result:
                            return result
        return None

    return recurse("", parts)


def decode_path(encoded):
    """Decode an encoded Claude Code project dir name to a real path.

    Uses a shared cache (~/.ab0t/.agents/decode_cache) and filesystem
    checks to correctly resolve ambiguous dash-encoded paths.
    """
    # 1. Check shared cache
    cache = _load_decode_cache()
    if encoded in cache:
        return cache[encoded]

    # 2. Quick check: maybe all dashes really are slashes
    stripped = encoded[1:] if encoded.startswith("-") else encoded
    simple = "/" + stripped.replace("-", "/")
    if os.path.isdir(simple):
        _save_to_cache(encoded, simple)
        return simple

    # 3. Smart filesystem walk
    resolved = _find_real_path(encoded)
    if resolved:
        _save_to_cache(encoded, resolved)
        return resolved

    # 4. Fallback (path may no longer exist)
    return simple


class ClaudeAdapter(BaseAdapter):
    name = "claude"
    color = "\033[0;36m"  # cyan

    def __init__(self):
        self.claude_dir = os.path.expanduser("~/.claude")
        self.projects_dir = os.path.join(self.claude_dir, "projects")

    def is_available(self):
        return os.path.isdir(self.projects_dir)

    def _decode_path(self, encoded):
        """Decode project dir name to real filesystem path."""
        return decode_path(encoded)

    def list_projects(self):
        if not self.is_available():
            return []
        results = []
        for entry in os.listdir(self.projects_dir):
            proj_path = os.path.join(self.projects_dir, entry)
            if not os.path.isdir(proj_path):
                continue
            count = 0
            latest = 0
            for root, dirs, files in os.walk(proj_path):
                for fname in files:
                    if not fname.endswith(".jsonl"):
                        continue
                    if fname.startswith("agent-") or "subagents" in root:
                        continue
                    count += 1
                    fpath = os.path.join(root, fname)
                    try:
                        mt = os.path.getmtime(fpath)
                        if mt > latest:
                            latest = mt
                    except OSError:
                        pass
            if count > 0:
                display_path = self._decode_path(entry)
                results.append((display_path, count, latest))
        return results

    def list_sessions(self, project_path):
        # Not used by stats - implemented for completeness
        return []

    def parse_session_stats(self, fpath):
        stats = {
            "input": 0, "output": 0,
            "cache_read": 0, "cache_create": 0,
            "turn_duration_ms": 0,
            "session_active_s": 0,
            "earliest": None,
            "models": {},
        }
        prev_ts = None
        session_active = 0
        earliest = None

        try:
            with open(fpath) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        ts_str = d.get("timestamp")
                        if ts_str and isinstance(ts_str, str):
                            try:
                                ts = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00")
                                )
                                ts_epoch = ts.timestamp()
                                if earliest is None or ts_epoch < earliest:
                                    earliest = ts_epoch
                                if prev_ts is not None:
                                    gap = ts_epoch - prev_ts
                                    if 0 < gap <= 3600:
                                        session_active += gap
                                prev_ts = ts_epoch
                            except ValueError:
                                pass
                        rec_type = d.get("type")
                        if rec_type == "assistant":
                            msg = d.get("message", {})
                            model = msg.get("model", "")
                            if model:
                                stats["models"][model] = (
                                    stats["models"].get(model, 0) + 1
                                )
                            usage = msg.get("usage", {})
                            stats["input"] += usage.get("input_tokens", 0)
                            stats["output"] += usage.get("output_tokens", 0)
                            stats["cache_read"] += usage.get(
                                "cache_read_input_tokens", 0
                            )
                            stats["cache_create"] += usage.get(
                                "cache_creation_input_tokens", 0
                            )
                        elif (
                            rec_type == "system"
                            and d.get("subtype") == "turn_duration"
                        ):
                            stats["turn_duration_ms"] += d.get("durationMs", 0)
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
        except OSError:
            pass

        stats["session_active_s"] = session_active
        stats["earliest"] = earliest
        return stats

    def resume_command(self, session_id, project_path, query=None):
        cmd = f'cd "{project_path}" && claude -r "{session_id}"'
        if query:
            cmd += f' "{query}"'
        return cmd

    def iter_all_sessions(self):
        if not self.is_available():
            return
        for proj_entry in os.listdir(self.projects_dir):
            proj_path = os.path.join(self.projects_dir, proj_entry)
            if not os.path.isdir(proj_path):
                continue
            display = self._decode_path(proj_entry)
            for root, dirs, files in os.walk(proj_path):
                for fname in files:
                    if not fname.endswith(".jsonl"):
                        continue
                    fpath = os.path.join(root, fname)
                    is_agent = (
                        fname.startswith("agent-") or "subagents" in root
                    )
                    try:
                        mtime = os.path.getmtime(fpath)
                    except OSError:
                        mtime = 0
                    yield display, fpath, mtime, is_agent
