"""
Adapter for Google Gemini CLI sessions stored in ~/.gemini/.

Session layout:
  ~/.gemini/tmp/<project_hash>/chats/  - per-project session files
    Each project_hash is derived from the project root directory.
    Sessions are JSON files (checkpoint-tag-*.json, logs.json).
    Transitioning to JSONL format for new sessions.

Resume:
  gemini --resume              # resume latest session
  gemini --resume <index>      # resume by index
  gemini --resume <uuid>       # resume by session ID
  gemini --list-sessions       # list available sessions
"""

import os
import json
import glob
import hashlib
from datetime import datetime
from .base import BaseAdapter, SessionInfo


class GeminiAdapter(BaseAdapter):
    name = "gemini"
    color = "\033[0;33m"  # yellow

    def __init__(self):
        self.gemini_dir = os.path.expanduser("~/.gemini")
        self.tmp_dir = os.path.join(self.gemini_dir, "tmp")

    def is_available(self):
        return os.path.isdir(self.tmp_dir)

    def _find_chat_dirs(self):
        """Find all project chat directories under ~/.gemini/tmp/*/chats/."""
        if not self.is_available():
            return []
        chat_dirs = []
        try:
            for project_hash in os.listdir(self.tmp_dir):
                chats_dir = os.path.join(self.tmp_dir, project_hash, "chats")
                if os.path.isdir(chats_dir):
                    chat_dirs.append((project_hash, chats_dir))
        except OSError:
            pass
        return chat_dirs

    def _guess_project_path(self, project_hash):
        """Try to resolve a project hash back to a real path.

        Gemini hashes the project root to create the directory name.
        We check known project paths to find a match, or fall back
        to reading session metadata.
        """
        # Try common hash algorithms against known directories
        # by scanning for any session file that contains cwd info
        return None

    def _get_session_cwd(self, fpath):
        """Try to extract cwd/project path from a session file."""
        try:
            with open(fpath) as f:
                content = f.read(8192)  # Read first 8KB
                # Try as JSON first
                try:
                    d = json.loads(content)
                    return self._extract_cwd_from_data(d)
                except json.JSONDecodeError:
                    pass
                # Try as JSONL (first line)
                first_line = content.split("\n", 1)[0].strip()
                if first_line:
                    try:
                        d = json.loads(first_line)
                        return self._extract_cwd_from_data(d)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        return ""

    def _extract_cwd_from_data(self, d):
        """Extract cwd from a parsed JSON record."""
        if isinstance(d, dict):
            for key in ("cwd", "working_directory", "workingDirectory",
                        "projectRoot", "project_root"):
                val = d.get(key, "")
                if val:
                    return val
                # Check nested payload/metadata
                for nested in ("payload", "metadata", "session_metadata"):
                    nest = d.get(nested, {})
                    if isinstance(nest, dict) and nest.get(key):
                        return nest[key]
        return ""

    def _get_first_user_msg(self, fpath):
        """Get first user message from session file."""
        try:
            with open(fpath) as f:
                content = f.read(16384)
            # Try as JSON (full conversation array)
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for msg in data[:20]:
                        if isinstance(msg, dict) and msg.get("role") == "user":
                            text = self._extract_text(msg)
                            if text:
                                return text
                elif isinstance(data, dict):
                    # Might have a messages array
                    messages = data.get("messages", data.get("history", []))
                    if isinstance(messages, list):
                        for msg in messages[:20]:
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                text = self._extract_text(msg)
                                if text:
                                    return text
            except json.JSONDecodeError:
                pass
            # Try as JSONL
            for line in content.split("\n")[:50]:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if isinstance(d, dict) and d.get("role") == "user":
                        text = self._extract_text(d)
                        if text:
                            return text
                except json.JSONDecodeError:
                    pass
        except OSError:
            pass
        return ""

    def _extract_text(self, msg):
        """Extract text content from a message record."""
        content = msg.get("content", msg.get("text", msg.get("parts", "")))
        if isinstance(content, str) and content:
            return " ".join(content.split())[:60]
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text", item.get("content", ""))
                    if text:
                        return " ".join(str(text).split())[:60]
                elif isinstance(item, str):
                    return " ".join(item.split())[:60]
        return ""

    def _iter_session_files(self, chats_dir):
        """Yield session files from a chats directory (json and jsonl)."""
        try:
            for fname in os.listdir(chats_dir):
                if fname.endswith((".json", ".jsonl")):
                    yield os.path.join(chats_dir, fname)
        except OSError:
            pass

    def list_projects(self):
        if not self.is_available():
            return []
        projects = {}  # cwd -> (count, latest_mtime)
        for project_hash, chats_dir in self._find_chat_dirs():
            cwd = ""
            count = 0
            latest = 0
            for sf in self._iter_session_files(chats_dir):
                if not cwd:
                    cwd = self._get_session_cwd(sf)
                count += 1
                try:
                    mt = os.path.getmtime(sf)
                    if mt > latest:
                        latest = mt
                except OSError:
                    pass
            if not cwd:
                continue
            if cwd in projects:
                old_count, old_latest = projects[cwd]
                projects[cwd] = (old_count + count, max(old_latest, latest))
            else:
                projects[cwd] = (count, latest)
        return [(cwd, count, latest) for cwd, (count, latest) in projects.items()]

    def list_sessions(self, project_path):
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
                content = f.read()
            # Try JSON array or JSONL
            records = []
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = data.get("messages", data.get("history", [data]))
            except json.JSONDecodeError:
                for line in content.split("\n"):
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            for d in records:
                if not isinstance(d, dict):
                    continue
                ts_str = d.get("timestamp", d.get("created_at", ""))
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
                model = d.get("model", "")
                if model:
                    stats["models"][model] = stats["models"].get(model, 0) + 1
                # Token usage if available
                usage = d.get("usage", d.get("usageMetadata", {}))
                if isinstance(usage, dict):
                    stats["input"] += usage.get("input_tokens",
                                     usage.get("promptTokenCount", 0))
                    stats["output"] += usage.get("output_tokens",
                                      usage.get("candidatesTokenCount", 0))
                    stats["cache_read"] += usage.get("cachedContentTokenCount", 0)
        except OSError:
            pass

        stats["session_active_s"] = session_active
        stats["earliest"] = earliest
        return stats

    def resume_command(self, session_id, project_path, query=None):
        cmd = f'cd "{project_path}" && gemini --resume'
        if session_id:
            cmd += f' "{session_id}"'
        return cmd

    def iter_all_sessions(self):
        if not self.is_available():
            return
        for project_hash, chats_dir in self._find_chat_dirs():
            cwd = ""
            for sf in self._iter_session_files(chats_dir):
                if not cwd:
                    cwd = self._get_session_cwd(sf) or "unknown"
                try:
                    mtime = os.path.getmtime(sf)
                except OSError:
                    mtime = 0
                yield cwd, sf, mtime, False
