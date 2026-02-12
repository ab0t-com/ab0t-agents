"""
Base adapter interface for coding agent session providers.

Each adapter normalizes an agent's session data into a common format
so the agents CLI can display unified stats, listings, and resume commands.
"""


class SessionInfo:
    """Normalized session data returned by adapters."""
    __slots__ = (
        "session_id", "project_path", "mtime", "first_message",
        "git_branch", "model", "agent_name",
        # stats fields (optional, filled by parse_session_stats)
        "input_tokens", "output_tokens", "cache_read", "cache_create",
        "turn_duration_ms", "session_active_s", "earliest_ts",
        "models",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))
        if self.models is None:
            self.models = {}


class BaseAdapter:
    """Interface that each agent adapter must implement."""

    # Short name shown in UI, e.g. "claude", "codex"
    name = ""
    # Color code for the agent badge
    color = ""

    def is_available(self):
        """Return True if this agent's data directory exists."""
        raise NotImplementedError

    def list_projects(self):
        """
        Return list of (project_path, session_count, latest_mtime).
        project_path is the real filesystem path the sessions were run in.
        """
        raise NotImplementedError

    def list_sessions(self, project_path):
        """
        Return list of SessionInfo for a given project path,
        sorted by mtime descending.
        """
        raise NotImplementedError

    def parse_session_stats(self, session_file):
        """
        Parse a session file and return a dict of stats suitable for caching:
        {input, output, cache_read, cache_create, turn_duration_ms,
         session_active_s, earliest, models: {name: count}}
        """
        raise NotImplementedError

    def resume_command(self, session_id, project_path, query=None):
        """Return the shell command string to resume a session."""
        raise NotImplementedError

    def iter_all_sessions(self):
        """
        Yield (project_name, session_file_path, mtime, is_agent) for every
        session file. Used by stats aggregation. project_name is a display key.
        """
        raise NotImplementedError
