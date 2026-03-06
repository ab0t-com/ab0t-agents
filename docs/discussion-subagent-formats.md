# Discussion: Subagent Definition Formats Across Harnesses

**Date:** 2026-03-06
**Status:** Reference / RFC

## Overview

All three major coding agent harnesses support some form of subagent — a specialized agent that operates within a parent session to handle scoped tasks. The formats differ significantly in structure and capability, but share a common pattern: **a named definition with instructions and constraints**.

This document compares the subagent definition formats across Claude Code, Gemini CLI, and Codex CLI, with full field references and real-world examples.

---

## Quick Comparison

| Aspect | Claude Code | Gemini CLI | Codex CLI |
|--------|-------------|------------|-----------|
| **Format** | Markdown + YAML frontmatter | Markdown + YAML frontmatter | TOML config tables |
| **Location** | `.claude/agents/<name>.md` | `.gemini/agents/<name>.md` | `[agents.<name>]` in `config.toml` |
| **Scope** | Project-level | Project or user (`~/.gemini/agents/`) | User-level (`~/.codex/config.toml`) |
| **Instructions** | Markdown body after frontmatter | Markdown body after frontmatter | `developer_instructions` in linked TOML |
| **Feature status** | Stable | Experimental | Experimental |
| **Enable flag** | None needed | `{"experimental": {"enableAgents": true}}` | `[features] multi_agent = true` |

---

## 1. Claude Code Subagents

### File Format

**Path:** `.claude/agents/<name>.md`

Structure: YAML frontmatter between `---` delimiters, followed by a markdown system prompt.

### Frontmatter Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Display name for the agent |
| `description` | string | Yes | — | When to invoke this agent (shown to parent) |
| `tools` | string[] | No | All tools | Allowed tools with glob patterns |
| `disallowedTools` | string[] | No | — | Explicit tool blocklist |
| `model` | enum | No | `inherit` | `sonnet`, `opus`, `haiku`, or `inherit` |
| `permissionMode` | enum | No | — | `default`, `plan`, `auto-edit` |
| `maxTurns` | number | No | — | Maximum conversation turns |
| `skills` | string[] | No | — | Skills to preload into agent |
| `mcpServers` | object | No | — | MCP server configs available to agent |
| `hooks` | object | No | — | Hook definitions scoped to this agent |
| `memory` | object | No | — | Memory access: `user`, `project`, `local` |
| `background` | boolean | No | false | Run as background task |
| `isolation` | enum | No | — | `worktree` for git worktree isolation |

### Tool Permission Syntax

Claude Code uses glob-style patterns for tool restrictions:

```yaml
tools:
  - Read                          # any Read call
  - Read(//.claude/fleet/**)      # Read only in .claude/fleet/ tree
  - Write(//.claude/fleet/bus/**) # Write only in .claude/fleet/bus/
  - Bash(git status)              # Bash limited to "git status"
  - Agent(worker, researcher)     # Can only spawn these subagents
```

The `//` prefix means project root. Patterns support `*` (single level) and `**` (recursive).

### Built-in Agents

Claude Code ships with several built-in agents:

| Agent | Model | Tools | Purpose |
|-------|-------|-------|---------|
| **Explore** | haiku | Read, Glob, Grep, Bash (read-only) | Codebase exploration |
| **Plan** | inherit | Read, Glob, Grep, Bash (read-only) | Task planning (no edits) |
| **general-purpose** | inherit | All | Default subagent |
| **Bash** | inherit | Bash only | Shell operations |
| **statusline-setup** | inherit | Bash, Read, Write | Terminal status line config |
| **Claude Code Guide** | inherit | Read-only + WebFetch | Documentation lookup |

### Example: Fleet Orchestrator

A real-world production subagent from a multi-agent architecture:

```yaml
---
name: fleet-orchestrator
description: Metacognitive orchestrator managing the agent fleet
tools:
  - Read(//.claude/fleet/**)
  - Write(//.claude/fleet/bus/**)
model: opus
---

# Fleet Orchestrator

You are the metacognitive orchestrator for the agent fleet. Your responsibilities:

1. Read the fleet bus for incoming task requests
2. Decompose complex tasks into subtasks
3. Assign subtasks to specialized agents via the bus
4. Monitor progress and handle failures
5. Synthesize results back to the requesting agent

## Communication Protocol

All inter-agent communication flows through `//.claude/fleet/bus/`:
- `requests/` — incoming task requests
- `assignments/` — task assignments to agents
- `results/` — completed task results
- `status/` — agent heartbeats and status

## Decision Framework

When receiving a task:
- If it requires code changes → assign to `coder` agent
- If it requires research → assign to `researcher` agent
- If it requires review → assign to `reviewer` agent
- If it's ambiguous → decompose further before assigning
```

### Example: Read-Only Reviewer

```yaml
---
name: reviewer
description: Reviews code changes for correctness and style
tools:
  - Read
  - Glob
  - Grep
  - Bash(git diff**)
  - Bash(git log**)
model: sonnet
permissionMode: plan
maxTurns: 20
---

# Code Reviewer

Review code changes for:
- Correctness and edge cases
- Security vulnerabilities (OWASP top 10)
- Performance implications
- Style consistency with the existing codebase

Output a structured review with severity levels: critical, warning, suggestion.
Never suggest fixes directly — only identify issues.
```

### Example: Background Worker with Isolation

```yaml
---
name: test-runner
description: Runs tests in an isolated worktree
tools:
  - Read
  - Bash
model: haiku
background: true
isolation: worktree
maxTurns: 10
---

Run the test suite and report results. Do not modify any files.
If tests fail, report the failures with file paths and line numbers.
```

### CLI-Defined Agents

Claude Code also supports defining agents inline via CLI flags:

```bash
claude --agents '[
  {"name": "researcher", "model": "haiku", "tools": ["Read", "Grep", "Glob"]},
  {"name": "writer", "model": "sonnet", "tools": ["Read", "Write"]}
]'
```

### Agent Invocation

From within a Claude Code session, agents are invoked via the `Agent` tool:

```
Use the Agent tool to call the "reviewer" agent with this task: review the changes in the last commit.
```

Or via slash command: `/agent reviewer review the last commit`

### Hooks in Agents

Agents can define their own hooks that only fire within that agent's context:

```yaml
---
name: safe-editor
description: Editor with safety hooks
hooks:
  PreToolUse:
    - matcher: Bash
      command: "echo 'Bash blocked in safe-editor' && exit 1"
---
```

---

## 2. Gemini CLI Subagents

### File Format

**Path:** `.gemini/agents/<name>.md` (project) or `~/.gemini/agents/<name>.md` (user)

Structure: YAML frontmatter between `---` delimiters, followed by markdown instructions.

**Requires explicit opt-in** in `settings.json`:
```json
{
  "experimental": {
    "enableAgents": true
  }
}
```

### Frontmatter Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Unique slug (lowercase, hyphens/underscores) |
| `description` | string | Yes | — | When to invoke this agent |
| `kind` | enum | No | `local` | `local` or `remote` (A2A protocol) |
| `tools` | string[] | No | — | Tool names the agent can access |
| `model` | string | No | inherit | Specific Gemini model ID |
| `temperature` | number | No | — | Sampling temperature (0.0–2.0) |
| `max_turns` | number | No | 15 | Conversation turn limit |
| `timeout_mins` | number | No | 5 | Execution timeout in minutes |

### Built-in Agents

| Agent | Purpose |
|-------|---------|
| **Codebase Investigator** (`codebase_investigator`) | Analyzes code dependencies and architecture |
| **CLI Help Agent** (`cli_help`) | Gemini CLI documentation |
| **Generalist Agent** (`generalist_agent`) | Routes tasks to specialists |
| **Browser Agent** (`browser_agent`) | Web automation (requires Chrome 144+) |

### Example: Security Auditor

```yaml
---
name: security-auditor
description: Finds security vulnerabilities in code
kind: local
tools:
  - read_file
  - grep_search
model: gemini-2.5-pro
temperature: 0.2
max_turns: 10
---

You are a Security Auditor. Analyze code for:
- SQL injection
- XSS vulnerabilities
- Hardcoded credentials
- Unsafe file operations
- Insecure deserialization

Report findings with severity ratings. Do not fix issues — only identify them.
```

### Example: Documentation Writer

```yaml
---
name: doc-writer
description: Generates and updates project documentation
kind: local
tools:
  - read_file
  - write_file
  - list_directory
model: gemini-2.5-flash
temperature: 0.3
max_turns: 20
timeout_mins: 10
---

You are a documentation specialist. When asked to document code:

1. Read the source files to understand the API surface
2. Generate clear, concise documentation with examples
3. Use the project's existing documentation style
4. Include type signatures and parameter descriptions
```

### Browser Agent Configuration

The browser agent has its own settings block in `settings.json`:

```json
{
  "agents": {
    "overrides": {
      "browser_agent": {
        "enabled": true
      }
    },
    "browser": {
      "sessionMode": "persistent",
      "headless": false,
      "visualModel": "gemini-2.5-computer-use-preview-10-2025"
    }
  }
}
```

Session modes: `persistent` (default), `isolated` (temp profile), `existing` (attach to running Chrome).

### Remote Subagents (A2A)

Gemini supports the Agent-to-Agent (A2A) protocol for delegating to remote agents:

```yaml
---
name: remote-analyzer
description: Delegates analysis to a remote service
kind: remote
---
```

Remote agent configuration is managed separately via A2A protocol settings.

### Security Notes

- Subagents operate in "YOLO mode" — they may execute tools without individual confirmation
- Browser agent blocks dangerous URL schemes: `file://`, `javascript:`, `data:text/html`, `chrome://extensions`
- Browser agent blocks password pages

---

## 3. Codex CLI Multi-Agent

### Configuration Format

**Path:** `~/.codex/config.toml` (user-level) or project-level `config.toml`

Codex uses **TOML tables** rather than markdown files. Agent definitions live in the main config alongside other settings.

**Requires explicit opt-in:**
```toml
[features]
multi_agent = true
```

Or use the `/experimental` slash command in-session to enable "Multi-agents".

### Config Schema

```toml
[agents]
max_threads = 4              # max concurrent agent threads
max_depth = 1                # max nesting depth for spawned agents
job_max_runtime_seconds = 300  # default per-worker timeout

[agents.explorer]
description = "Read-only codebase explorer"
config_file = "agents/explorer.toml"

[agents.reviewer]
description = "Security and quality reviewer"
config_file = "agents/reviewer.toml"
```

### Agent Config Fields (in main config)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `agents.max_threads` | number | No | — | Max concurrent agent threads |
| `agents.max_depth` | number | No | 1 | Max nesting depth |
| `agents.job_max_runtime_seconds` | number | No | — | Per-worker timeout |
| `agents.<name>.description` | string | No | — | When to use this role |
| `agents.<name>.config_file` | string | No | — | Path to role-specific TOML |

### Role Config File Fields

Each role's config file (e.g., `agents/explorer.toml`) can override:

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Model to use for this role |
| `model_reasoning_effort` | string | Reasoning effort level |
| `sandbox_mode` | string | e.g., `"read-only"` |
| `developer_instructions` | string | System prompt for this role |
| MCP server configs | object | Tool servers available to this role |

### Built-in Roles

| Role | Purpose |
|------|---------|
| **default** | General-purpose fallback |
| **worker** | Execution-focused implementation |
| **explorer** | Read-heavy codebase exploration |
| **monitor** | Long-running monitoring and polling |

### Example: Explorer Role

**In `~/.codex/config.toml`:**
```toml
[agents.explorer]
description = "Read-only codebase exploration and analysis"
config_file = "agents/explorer.toml"
```

**In `agents/explorer.toml`:**
```toml
model = "o3-mini"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
developer_instructions = """
You are a codebase explorer. Your job is to:
- Navigate the codebase to answer questions
- Find relevant files, functions, and patterns
- Report findings without modifying anything

Never create or modify files. Only read and report.
"""
```

### Example: Reviewer Role

**In `~/.codex/config.toml`:**
```toml
[agents.reviewer]
description = "Code review focused on security and quality"
config_file = "agents/reviewer.toml"
```

**In `agents/reviewer.toml`:**
```toml
model = "o3"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review code changes for:
1. Security vulnerabilities
2. Logic errors
3. Performance issues
4. Style consistency

Provide structured feedback with severity levels.
"""
```

### CSV Batch Processing

Codex has a unique feature for distributing work across agents via CSV:

```
Use spawn_agents_on_csv to process tasks.csv — for each row,
analyze the file in the "filepath" column and report issues.
```

Parameters:
- `csv_path` — source file with rows of work
- `instruction` — worker prompt with `{column_name}` placeholders
- `id_column` — stable row identifiers
- `output_schema` — JSON structure each worker must produce
- `output_csv_path` — where results go
- `max_concurrency` — parallel workers
- `max_runtime_seconds` — per-worker timeout

Workers must call `report_agent_job_result` exactly once.

### Key Constraints

- Relative `config_file` paths resolve from the defining `config.toml` location
- Unknown fields in `[agents.<name>]` are rejected (strict schema)
- User-defined roles override built-in roles with matching names
- Child agents inherit parent sandbox policy and runtime overrides

---

## 4. Format Comparison

### Structural Differences

| Aspect | Claude | Gemini | Codex |
|--------|--------|--------|-------|
| **File type** | `.md` (markdown) | `.md` (markdown) | `.toml` (config) |
| **Instructions** | Markdown body | Markdown body | `developer_instructions` string |
| **One agent per file** | Yes | Yes | No (all in one config) |
| **Supporting files** | No | No | Separate `.toml` per role |
| **Frontmatter** | YAML | YAML | N/A (TOML tables) |

### Feature Mapping

| Feature | Claude | Gemini | Codex |
|---------|--------|--------|-------|
| **Tool restrictions** | Glob patterns with path scoping | Tool name list | `sandbox_mode` |
| **Model selection** | `model: sonnet/opus/haiku/inherit` | `model: <model-id>` | `model = "<model-id>"` |
| **Turn limits** | `maxTurns` | `max_turns` | N/A (timeout-based) |
| **Timeout** | N/A | `timeout_mins` | `job_max_runtime_seconds` |
| **Temperature** | N/A | `temperature` | N/A |
| **Background execution** | `background: true` | N/A | Inherent (multi-threaded) |
| **Git isolation** | `isolation: worktree` | N/A | Sandbox modes |
| **Hooks** | Per-agent hooks in frontmatter | N/A | N/A |
| **Memory access** | `memory: {user, project, local}` | N/A | N/A |
| **Skills preloading** | `skills: [...]` | N/A | N/A |
| **MCP servers** | `mcpServers` in frontmatter | N/A | MCP in role config |
| **Remote agents** | N/A | `kind: remote` (A2A) | N/A |
| **Batch processing** | N/A | N/A | CSV spawn |
| **Concurrency control** | N/A | N/A | `max_threads`, `max_depth` |
| **Permission mode** | `permissionMode` | N/A (YOLO mode) | `approval_policy` |
| **Nesting** | Agent tool restrictions | N/A | `max_depth` |

### Portability Assessment

**What's portable:**
- Agent name and description — universal concept
- System prompt / instructions — markdown is markdown
- Basic tool restrictions — "read-only" maps across all three
- Model preference — conceptual mapping (though model IDs differ)

**What's NOT portable:**
- Claude's glob-pattern tool scoping — no equivalent elsewhere
- Claude's hooks-in-frontmatter — unique to Claude
- Claude's memory and skills references — unique to Claude
- Gemini's `temperature` and `timeout_mins` — no Claude equivalent
- Gemini's A2A remote agents — unique to Gemini
- Codex's TOML format — fundamentally different structure
- Codex's CSV batch processing — unique to Codex
- Codex's `max_threads` / `max_depth` — unique concurrency model

### Architectural Philosophy

Each harness approaches subagents differently:

**Claude Code** treats agents as **first-class markdown documents** — rich, self-contained definitions with fine-grained permissions, hooks, memory, and skill references. An agent file is essentially a complete agent specification. This enables sophisticated multi-agent architectures (fleet patterns, hierarchical delegation) but is the most complex format.

**Gemini CLI** takes a **lightweight markdown approach** — similar to Claude but with fewer fields and simpler constraints. The `kind: remote` field for A2A protocol is unique and forward-looking. The trade-off is less granular control (no per-agent hooks, no memory scoping, YOLO execution mode).

**Codex CLI** uses a **configuration-centric approach** — agents are defined in TOML alongside other settings, with instructions as string values rather than document bodies. This fits Codex's general config-file philosophy but makes agent definitions harder to browse and share as standalone artifacts. The CSV batch processing feature is unique and powerful for data-parallel workloads.

---

## 5. Implications for `agents` CLI Management

### What Management Could Look Like

Given the format differences, the `agents` CLI's role in managing subagents would focus on:

**1. Visibility** — unified listing of all defined agents across harnesses:
```
agents config agents

Claude Code (.claude/agents/)
  fleet-orchestrator   model:opus     tools:scoped   "Metacognitive orchestrator"
  reviewer             model:sonnet   tools:readonly "Reviews code changes"
  test-runner          model:haiku    background     "Runs tests in worktree"

Gemini CLI (.gemini/agents/)
  security-auditor     model:2.5-pro  tools:2        "Finds vulnerabilities"
  doc-writer           model:2.5-flash tools:3       "Documentation specialist"

Codex CLI (config.toml [agents])
  explorer             model:o3-mini  sandbox:ro     "Codebase exploration"
  reviewer             model:o3       sandbox:ro     "Security and quality review"
```

**2. Registry** — install community agent definitions in their native format:
```
agents registry search "code review"
  [claude:agent]  community/pr-reviewer     ★ 1.2k  Multi-file PR review agent
  [gemini:agent]  community/review-bot      ★ 340   Gemini code review agent
  [codex:agent]   community/quality-check   ★ 210   Codex review role config

agents registry install community/pr-reviewer
# → copies to .claude/agents/pr-reviewer.md
```

**3. Presets** — team-standard agent configurations:
```yaml
# presets/team-agents.yaml
claude:
  agents:
    - registry: community/pr-reviewer
    - registry: team/deploy-agent
    - registry: team/fleet-orchestrator

gemini:
  agents:
    - registry: community/security-auditor

codex:
  agents:
    - name: explorer
      config: agents/explorer.toml
```

### Translation Challenges

Unlike skills (which follow the Agent Skills open standard), subagent definitions are **not standardized**. A Claude agent `.md` cannot be mechanically translated to a Codex TOML role because:

1. **Tool permissions** — Claude's glob patterns have no equivalent
2. **Format** — markdown body vs `developer_instructions` string
3. **Features** — hooks, memory, skills, isolation are Claude-only
4. **Model IDs** — `sonnet` vs `gemini-2.5-pro` vs `o3`

The registry approach (items stored in native format, tagged by harness) avoids this problem entirely. You don't translate — you install the right version for your harness.

### Cross-Harness Agent Concept

For teams using multiple harnesses, a future possibility is a **concept-level manifest** that maps a logical role to harness-specific implementations:

```yaml
# .agents/roles/reviewer.yaml
concept: code-reviewer
description: Reviews code changes for quality and security

implementations:
  claude: .claude/agents/reviewer.md
  gemini: .gemini/agents/reviewer.md
  codex: agents/reviewer.toml
```

This doesn't translate formats — it just tracks that "reviewer" exists across harnesses and points to each native definition. The `agents` CLI could scaffold all three when you create a new role.

---

## References

- [Claude Code Sub-agents docs](https://code.claude.com/docs/en/sub-agents)
- [Gemini CLI Subagents docs](https://geminicli.com/docs/core/subagents/)
- [Codex CLI Multi-agent docs](https://developers.openai.com/codex/multi-agent/)
- [Agent Skills open standard](https://agentskills.io)
- [Discussion: Hooks, Skills & Agents management](./discussion-hooks-skills-agents.md)
- [Harness Extensibility Reference](./discussion-harness-extensibility-reference.md)
