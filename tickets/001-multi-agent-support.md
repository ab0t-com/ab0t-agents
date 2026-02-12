# Ticket #001: Multi-Agent Support - Universal Session Manager

**Status:** Open
**Priority:** High
**Type:** Feature
**Created:** 2026-01-06
**Labels:** `enhancement`, `architecture`, `v2.0`

---

## Summary

Transform `agents` from a Claude Code-specific session browser into a **universal agent session manager** that supports multiple AI coding assistants. The tool should become agent-agnostic while maintaining the current Claude Code functionality as the reference implementation.

---

## Background

### Current State

- `agents` currently only supports Claude Code sessions
- Session data is read from `~/.claude/projects/`
- The architecture assumes a single agent type

### Vision

Rename or rebrand to reflect broader scope:
- **agentops** - Agent Operations Manager
- **agents** (keep as-is, broader meaning)
- **aisessions** - AI Session Manager

Support multiple AI coding agents:
- Claude Code (Anthropic)
- GitHub Copilot CLI / Codex
- Google Gemini CLI Agent
- Amazon Q Developer
- Cursor AI
- Cody (Sourcegraph)
- Aider
- Continue.dev
- Future agents...

---

## Research Required

Before implementation, research the session storage structure for each agent:

### Claude Code (Reference - Known)

```
~/.claude/
├── projects/
│   └── -encoded-path/
│       └── <uuid>.jsonl
└── .claude.json
```

### GitHub Copilot / Codex CLI

```
Location: ???
Format: ???
Session structure: ???
```

### Google Gemini Agent

```
Location: ???
Format: ???
Session structure: ???
```

### Amazon Q Developer

```
Location: ???
Format: ???
Session structure: ???
```

### Others

Research and document session storage for each supported agent.

---

## Proposed Architecture

### 1. Agent Provider Interface

Create an abstraction layer for agent providers:

```bash
# Provider interface (conceptual)
provider_name()           # "claude", "copilot", "gemini"
provider_display_name()   # "Claude Code", "GitHub Copilot"
provider_session_dir()    # Where sessions are stored
provider_list_sessions()  # List all sessions for a project
provider_get_session()    # Get session details
provider_resume_cmd()     # Command to resume session
provider_is_installed()   # Check if agent is installed
```

### 2. Directory Structure

```
agents/
├── agents                    # Main script
├── providers/                # Agent provider plugins
│   ├── claude.sh             # Claude Code provider
│   ├── copilot.sh            # GitHub Copilot provider
│   ├── gemini.sh             # Gemini provider
│   └── ...
├── lib/                      # Shared functions
│   ├── common.sh
│   ├── display.sh
│   └── config.sh
└── ...
```

### 3. Configuration

```bash
# ~/.config/agents/config
# or ~/.agentsrc

# Default agent (if multiple installed)
DEFAULT_AGENT="claude"

# Enabled agents (auto-detect by default)
ENABLED_AGENTS="claude,copilot,gemini"

# Custom session directories (override auto-detect)
CLAUDE_SESSION_DIR="~/.claude/projects"
COPILOT_SESSION_DIR="~/.copilot/sessions"
```

### 4. Command Changes

```bash
# Current (single agent)
agents list
agents show .
agents tree .

# Proposed (multi-agent)
agents list                    # List all agents' projects
agents list --agent claude     # List only Claude projects
agents list -a copilot         # Short form

agents show . --agent gemini   # Show Gemini sessions
agents show .                  # Show all agents' sessions

# New commands
agents agents                  # List installed/detected agents
agents switch claude           # Set default agent
agents config                  # Show/edit configuration
```

### 5. Display Changes

```
My Projects (All Agents)
────────────────────────────────────────────────────

[Claude Code]
[ 1] /home/user/myproject
     5m ago     sessions: 3

[GitHub Copilot]
[ 2] /home/user/myproject
     2h ago     sessions: 1

[Gemini]
[ 3] /home/user/webapp
     1d ago     sessions: 5
```

Or unified view:

```
[ 1] /home/user/myproject
     Claude: 3 sessions (5m ago) | Copilot: 1 session (2h ago)
[ 2] /home/user/webapp
     Gemini: 5 sessions (1d ago)
```

---

## Implementation Phases

### Phase 1: Refactoring (Foundation)

- [ ] Extract Claude-specific code into `providers/claude.sh`
- [ ] Create provider interface specification
- [ ] Create `lib/common.sh` for shared functions
- [ ] Refactor main script to use provider abstraction
- [ ] Add configuration file support
- [ ] Ensure backward compatibility

### Phase 2: Research & Documentation

- [ ] Research GitHub Copilot CLI session storage
- [ ] Research Google Gemini CLI session storage
- [ ] Research Amazon Q Developer session storage
- [ ] Document findings in `docs/providers/`
- [ ] Create provider template

### Phase 3: Additional Providers

- [ ] Implement GitHub Copilot provider
- [ ] Implement Gemini provider
- [ ] Implement Amazon Q provider
- [ ] Add auto-detection for installed agents

### Phase 4: Enhanced Features

- [ ] Cross-agent session search
- [ ] Unified project view
- [ ] Agent comparison (sessions per agent per project)
- [ ] Migration tools (if applicable)

---

## Acceptance Criteria

1. **Backward Compatibility**: Existing Claude Code users experience no breaking changes
2. **Auto-Detection**: Automatically detect installed agents
3. **Graceful Degradation**: Work with only one agent installed
4. **Consistent UX**: Same commands work across all agents
5. **Extensible**: Easy to add new agent providers
6. **Documentation**: Each provider documented with setup instructions

---

## Technical Considerations

### Challenges

1. **Different Storage Formats**: Each agent may use different formats (JSONL, JSON, SQLite, etc.)
2. **Different Session Structures**: Message formats vary between agents
3. **Resume Commands**: Each agent has different CLI syntax
4. **Authentication**: Some agents may require auth tokens
5. **Platform Differences**: Storage locations may vary by OS

### Solutions

1. **Abstraction Layer**: Provider interface hides implementation details
2. **Normalization**: Convert to common internal format for display
3. **Config Per Provider**: Store agent-specific settings separately
4. **Fallback Handling**: Gracefully handle missing/broken providers

---

## Open Questions

1. Should we support agents that don't have local session storage?
2. How to handle agents with cloud-only session storage?
3. Should we provide a way to manually register custom session directories?
4. Support for non-CLI agents (IDE extensions)?
5. Should we track agent version compatibility?

---

## References

- [Claude Code Documentation](https://docs.anthropic.com/claude-code)
- [GitHub Copilot CLI](https://docs.github.com/copilot)
- [Google Gemini](https://ai.google.dev/)
- [Amazon Q Developer](https://aws.amazon.com/q/developer/)
- [Aider](https://github.com/paul-gauthier/aider)

---

## Notes

This ticket represents a significant architectural change. We should ensure the refactoring maintains the tool's simplicity and performance while enabling future extensibility.

The core philosophy: **"One tool to manage all your AI coding sessions"**

---

*Created by the agents development team*
