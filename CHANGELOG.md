# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Search functionality: `agents search "query"` to find sessions by content
- Shell completions for bash, zsh, and fish
- Session tagging and bookmarks
- Export sessions to markdown
- Interactive TUI mode

---

## [1.0.0] - 2026-01-05

### Added
- Initial release
- **`agents list`** - List all Claude Code projects sorted by recent activity
  - `-a, --all` flag to show all projects (default: 10)
  - `-n NUM` to limit number of projects shown
  - Shows session count and last session ID per project
- **`agents show`** - Show sessions for a specific project
  - Supports project number, path, or `.` for current directory
  - Displays session ID, timestamp, size, and message preview
  - Shows ready-to-use resume commands
- **`agents tree`** - Tree view combining sessions with project files
  - `-d, --depth N` to control tree depth (default: 4)
  - `-a, --all` to show hidden directories
  - `--no-files` to show only sessions
  - Auto-hides common bloat directories (.venv, node_modules, etc.)
  - Color-coded file types and recency indicators
  - Shows git branch for each session
- **`agents resume`** - Quick session resume with numbered shortcuts
  - Supports optional initial query message
- **`agents stats`** - Usage statistics (projects, sessions, size)
- **`agents man`** - Detailed manual page with examples
- **`agents help`** - Brief usage help
- **`agents --version`** - Version information

### Installation
- `install.sh` script for easy installation
  - Supports `curl | bash` installation from GitHub
  - Local installation from cloned repository
  - `--dry-run` mode for previewing changes
  - `--uninstall` for clean removal
  - Automatic backup of existing installations
  - Idempotent (safe to run multiple times)

### Documentation
- Comprehensive man page (`agents.1.txt`) with:
  - Quick start section
  - Examples organized by use case
  - Workflow examples
  - Data structure documentation
- README with installation, usage, and future direction

### Technical
- Pure bash implementation (bash 4.0+)
- Python 3 required for JSON parsing
- No external dependencies beyond standard Unix tools
- Tested with Claude Code 2.0.76

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2026-01-05 | Initial release with list, show, tree, resume commands |

---

## Upgrade Notes

### To 1.0.0
First release - no upgrade path needed.

---

## Links

- [Repository](https://github.com/ab0t-com/agents)
- [Issues](https://github.com/ab0t-com/agents/issues)
- [Claude Code](https://claude.ai/code)
