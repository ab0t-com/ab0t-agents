# agents

**Claude Code Session Browser, Manager, and Launcher**

A command-line utility for browsing, managing, and resuming [Claude Code](https://claude.ai/code) sessions across your projects.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Claude Code](https://img.shields.io/badge/tested%20with-Claude%20Code%202.0.76-green)
![Shell](https://img.shields.io/badge/shell-bash-orange)

---

## The Problem

When using Claude Code across multiple projects, conversations get scattered:
- Sessions are stored in `~/.claude/projects/` with encoded path names
- No easy way to see which projects have active sessions
- Hard to remember which session had that useful conversation
- Resuming sessions requires knowing the session ID

## The Solution

`agents` provides a simple interface to:
- **List** all your Claude Code projects sorted by recent activity
- **Show** sessions for any project with previews of conversation content
- **Tree** view combining sessions with project file structure
- **Resume** sessions with a simple numbered shortcut

---

## Installation

### Quick Install (curl)

```bash
curl -sSL https://raw.githubusercontent.com/ab0t-com/agents/main/install.sh | bash
```

### Quick Install (wget)

```bash
wget -qO- https://raw.githubusercontent.com/ab0t-com/agents/main/install.sh | bash
```

### Manual Install

```bash
git clone https://github.com/ab0t-com/agents.git
cd agents
./install.sh
```

### Uninstall

```bash
~/.local/bin/agents  # or wherever you installed it
./install.sh --uninstall
```

---

## Quick Start

```bash
agents              # List your recent projects
agents tree .       # Tree view of current directory with sessions
agents show .       # Show sessions for current directory
agents resume 1     # Resume session #1 from last show
agents man          # Full documentation
```

---

## Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `agents list` | `ls` | List all projects with sessions |
| `agents show [path\|num]` | `s` | Show sessions for a project |
| `agents tree [path\|num]` | `t` | Tree view with sessions + files |
| `agents resume <num>` | `r` | Resume a session |
| `agents stats` | | Show usage statistics |
| `agents help` | `-h` | Brief help |
| `agents man` | | Detailed manual |
| `agents --version` | `-v` | Show version |

---

## Usage Examples

### Finding Your Projects

```bash
agents                  # List 10 most recent projects
agents list -a          # List ALL projects
agents list -n 20       # List 20 projects
```

### Exploring a Project

```bash
agents tree .           # Current directory: sessions + files
agents tree . -d 2      # Shallow tree (depth 2)
agents tree . --no-files # Only show sessions
agents show 3           # Sessions for project #3 from list
```

### Resuming Work

```bash
agents show .           # See sessions with previews
agents resume 1         # Resume session #1
agents r 2 "continue"   # Resume #2 with initial message
```

### Daily Workflow

```bash
# Start of day - find where you left off
agents                  # 1. See recent projects
agents tree 1           # 2. Check most recent
agents resume 1         # 3. Continue working
```

---

## Output Examples

### `agents list`

```
Claude Code Projects
────────────────────────────────────────────────────

[ 1] /home/user/myproject
     5m ago     sessions: 3 last: a1b2c3d4
[ 2] /home/user/webapp
     2h ago     sessions: 7 last: e5f6g7h8
[ 3] /home/user/api-server
     1d ago     sessions: 2
```

### `agents tree .`

```
/home/user/myproject
├── .claude-sessions/ (3 sessions)
│   ├── [1] a1b2c3d4 5m ago   2.1M ⎇ main
│   │   "Help me refactor the authentication module..."
│   ├── [2] x9y8z7w6 2d ago   890K ⎇ feature/payments
│   │   "Fix the bug in the payment processing..."
│   └── [3] m4n5o6p7 1w ago   156K
├── files/
    ├── README.md
    ├── src/
    │   ├── index.ts
    │   └── auth/
    (2 directories hidden: .venv, node_modules, etc.)

Quick resume: cd /home/user/myproject && claude -c
```

---

## Core Concepts

### Sessions

Each time you use Claude Code in a directory, it creates a **session** - a JSONL file containing your conversation history. Sessions are identified by UUIDs like `a1b2c3d4-e5f6-7890-abcd-ef1234567890`.

### Projects

A **project** is a directory where you've used Claude Code. Projects are stored in `~/.claude/projects/` with encoded path names (e.g., `/home/user/foo` becomes `-home-user-foo`).

### Resuming

Claude Code supports resuming sessions with:
- `claude -c` - Continue the last session
- `claude -r <id>` - Resume a specific session by ID

`agents` makes this easier by showing session previews and providing numbered shortcuts.

### Data Storage

```
~/.claude/
├── projects/                   # Session data per project
│   └── -home-user-myproj/      # Encoded project path
│       ├── abc123.jsonl        # Main session files
│       └── agent-xyz.jsonl     # Subagent sessions
├── file-history/               # File version backups
├── .credentials.json           # Authentication
└── ...

~/.claude.json                  # Global settings & metadata
```

---

## Features

### Smart Filtering

The tree view automatically hides common bloat directories:
- **Python**: `.venv`, `venv`, `__pycache__`, `.pytest_cache`
- **JavaScript**: `node_modules`, `.next`, `.nuxt`, `dist`
- **Build**: `build`, `target`, `coverage`
- **IDE**: `.git`, `.idea`, `.vscode`

Use `-a` to show hidden directories.

### Color Coding

**Time indicators:**
- 🟢 Green: Less than 1 hour ago
- 🟡 Yellow: Less than 24 hours ago
- ⚪ Gray: Older than 24 hours

**File types in tree:**
- 🔵 Blue: Directories
- 🟢 Green: Python (.py)
- 🟡 Yellow: JavaScript/TypeScript
- 🔵 Cyan: Config files (JSON, YAML)
- 🟣 Magenta: Shell scripts

### Session Previews

Sessions show the first user message as a preview, helping you identify what each conversation was about without opening it.

---

## Requirements

- **Bash** 4.0+
- **Python 3** (for JSON parsing)
- **Claude Code** installed and used at least once

Optional:
- `tree` command (for enhanced file tree display)
- `less` (for man page scrolling)

---

## Tested With

| Component | Version |
|-----------|---------|
| Claude Code | 2.0.76 |
| Claude Model | claude-opus-4-5-20251101 |
| Bash | 4.0+ |
| Ubuntu | 22.04+ |

---

## Future Direction

### Planned Features

- [ ] **Search**: `agents search "authentication"` - Find sessions by content
- [ ] **Tags**: Add custom tags to sessions for organization
- [ ] **Export**: Export session conversations to markdown
- [ ] **Cleanup**: `agents prune` - Remove old/empty sessions
- [ ] **Bookmarks**: Mark important sessions for quick access
- [ ] **Integration**: Shell completions (bash, zsh, fish)
- [ ] **TUI**: Interactive terminal UI with session browser

### Potential Enhancements

- Session rename/alias support
- Cross-machine session sync awareness
- Session size analytics and cleanup recommendations
- Integration with git branches (show sessions per branch)
- Fuzzy finding for projects and sessions

### Contributing

Contributions welcome! Areas of interest:
- Shell completion scripts
- Additional output formats (JSON, etc.)
- Performance improvements for large session counts
- Documentation improvements

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTS_INSTALL_DIR` | `~/.local/bin` | Installation directory |
| `AGENTS_MAN_DIR` | `~/.local/share/man/man1` | Man page directory |

---

## Troubleshooting

### "No Claude projects found"

You haven't used Claude Code yet, or `~/.claude/projects/` doesn't exist. Use Claude Code in any directory first.

### "command not found: agents"

Add the installation directory to your PATH:

```bash
export PATH="$PATH:$HOME/.local/bin"
```

Add this line to your `~/.bashrc` or `~/.zshrc`.

### Sessions not showing for a project

The project path must match exactly. Use `agents list -a` to see all projects and find the correct path encoding.

---

## License

MIT License - see LICENSE file

---

## Acknowledgments

- Built for use with [Claude Code](https://claude.ai/code) by Anthropic
- Inspired by the need to manage conversations across multiple projects

---

*Generated with Claude Code*
