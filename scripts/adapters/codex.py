"""
Adapter for OpenAI Codex CLI sessions stored in ~/.codex/.

Session layout:
  ~/.codex/history.jsonl        - user messages with session_id + ts + text
  ~/.codex/sessions/YYYY/MM/DD/rollout-<iso>-<uuid>.jsonl - full session logs

Session file record types:
  session_meta    - id, cwd, model_provider, cli_version, git info
  response_item   - payload.role (user/assistant/developer), payload.content
  event_msg       - tool execution events
  turn_context    - model, cwd, approval_policy per turn
  compacted       - context compaction markers

Resume: codex resume <session_id> [prompt]
"""

import os
import json
import glob
from datetime import datetime
from .base import BaseAdapter, SessionInfo


class CodexAdapter(BaseAdapter):
    name = "codex"
    color = "\033[0;32m"  # green

    def __init__(self):
        self.codex_dir = os.path.expanduser("~/.codex")
        self.sessions_dir = os.path.join(self.codex_dir, "sessions")
        self.history_file = os.path.join(self.codex_dir, "history.jsonl")

    def is_available(self):
        return os.path.isdir(self.sessions_dir)

    def _get_session_meta(self, fpath):
        """Read session_meta from first line of session file."""
        try:
            with open(fpath) as f:
                d = json.loads(f.readline())
                if d.get("type") == "session_meta":
                    return d.get("payload", {})
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _session_id_from_filename(self, fname):
        """Extract UUID from rollout-<iso>-<uuid>.jsonl filename."""
        # Format: rollout-2026-02-11T00-19-56-019c4a11-a501-7761-9d9e-71d21b8de353.jsonl
        base = fname.replace(".jsonl", "")
        # UUID is the last 5 hyphen-groups (36 chars)
        # Find it by looking for the UUID pattern at the end
        parts = base.split("-")
        # UUID parts are the last 5 segments of the dash-split
        if len(parts) >= 5:
            uuid_candidate = "-".join(parts[-5:])
            if len(uuid_candidate) == 36:
                return uuid_candidate
        return base

    def _get_first_user_msg(self, fpath):
        """Get first user message from session file."""
        try:
            with open(fpath) as f:
                for i, line in enumerate(f):
                    if i > 50:
                        break
                    try:
                        d = json.loads(line)
                        if d.get("type") == "response_item":
                            p = d.get("payload", {})
                            if p.get("role") == "user":
                                content = p.get("content", [])
                                if isinstance(content, list):
                                    for item in content:
                                        if isinstance(item, dict):
                                            text = item.get("text", "")
                                            if text and not text.startswith("#"):
                                                return " ".join(text.split())[:60]
                    except (json.JSONDecodeError, KeyError):
                        pass
        except OSError:
            pass
        return ""

    def _first_msg_from_history(self, session_id):
        """Get first user message from history.jsonl for a session."""
        if not os.path.isfile(self.history_file):
            return ""
        try:
            with open(self.history_file) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        if d.get("session_id") == session_id:
                            return " ".join(d.get("text", "").split())[:60]
                    except (json.JSONDecodeError, KeyError):
                        pass
        except OSError:
            pass
        return ""

    def list_projects(self):
        if not self.is_available():
            return []
        # Group sessions by cwd from session_meta
        projects = {}  # cwd -> (count, latest_mtime)
        for sf in glob.glob(
            os.path.join(self.sessions_dir, "**", "*.jsonl"), recursive=True
        ):
            meta = self._get_session_meta(sf)
            cwd = meta.get("cwd", "")
            if not cwd:
                continue
            try:
                mt = os.path.getmtime(sf)
            except OSError:
                mt = 0
            if cwd in projects:
                count, latest = projects[cwd]
                projects[cwd] = (count + 1, max(latest, mt))
            else:
                projects[cwd] = (1, mt)
        return [(cwd, count, latest) for cwd, (count, latest) in projects.items()]

    def list_sessions(self, project_path):
        return []

    def parse_session_stats(self, fpath):
        """Parse codex session. Codex doesn't expose token usage in session
        files, so we only track time and model info."""
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
                        # Extract model from turn_context
                        if d.get("type") == "turn_context":
                            model = d.get("payload", {}).get("model", "")
                            if model:
                                stats["models"][model] = (
                                    stats["models"].get(model, 0) + 1
                                )
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
        except OSError:
            pass

        stats["session_active_s"] = session_active
        stats["earliest"] = earliest
        return stats

    def resume_command(self, session_id, project_path, query=None):
        cmd = f'cd "{project_path}" && codex resume "{session_id}"'
        if query:
            cmd += f' "{query}"'
        return cmd

    def iter_all_sessions(self):
        if not self.is_available():
            return
        for sf in glob.glob(
            os.path.join(self.sessions_dir, "**", "*.jsonl"), recursive=True
        ):
            meta = self._get_session_meta(sf)
            cwd = meta.get("cwd", "unknown")
            try:
                mtime = os.path.getmtime(sf)
            except OSError:
                mtime = 0
            yield cwd, sf, mtime, False
