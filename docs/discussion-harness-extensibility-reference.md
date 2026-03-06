# Harness Extensibility Reference: Hooks, Skills, Commands & Agents

**Date:** 2026-03-06
**Purpose:** Complete reference for every extensibility point across Claude Code, Gemini CLI, and Codex CLI — what exists, what it does, where it fires in the lifecycle, and what data flows through it. This document is intended to be machine-readable enough that an agent could use it to manage hooks and skills on behalf of a user.

---

## 1. Lifecycle Comparison

Each harness runs an "agentic loop" — the cycle of receiving a prompt, planning, calling tools, and responding. The hooks intercept this loop at different points. Understanding the lifecycle ordering is critical for knowing what comes before/after each hook.

### Claude Code Lifecycle

```
SessionStart
  │
  ├── InstructionsLoaded (async, fires as CLAUDE.md / rules load)
  │
  ▼
UserPromptSubmit ──→ [user prompt validated]
  │
  ▼
┌─── Agentic Loop ──────────────────────────────┐
│                                                │
│  PreToolUse ──→ PermissionRequest (if needed)  │
│       │                                        │
│       ▼                                        │
│  [tool executes]                               │
│       │                                        │
│       ├── PostToolUse (on success)             │
│       └── PostToolUseFailure (on failure)      │
│                                                │
│  SubagentStart ──→ [subagent runs] ──→ SubagentStop │
│                                                │
│  PreCompact (if context full)                  │
│                                                │
│  ConfigChange (if settings modified)           │
│                                                │
└── repeats until Stop ─────────────────────────┘
  │
  ├── TeammateIdle (agent teams only)
  ├── TaskCompleted (when tasks marked done)
  │
  ▼
Stop
  │
  ▼
SessionEnd
  │
  ├── WorktreeRemove (if worktree session)
```

**Standalone async events:** `WorktreeCreate`, `WorktreeRemove`, `InstructionsLoaded`

### Gemini CLI Lifecycle

```
SessionStart
  │
  ▼
BeforeAgent ──→ [user prompt + context prepared]
  │
  ▼
┌─── Agentic Loop ──────────────────────────────┐
│                                                │
│  BeforeModel ──→ [LLM request]                │
│       │                                        │
│       ▼                                        │
│  AfterModel ──→ [response received]           │
│       │                                        │
│       ▼                                        │
│  BeforeToolSelection ──→ [tools filtered]     │
│       │                                        │
│       ▼                                        │
│  BeforeTool ──→ [tool executes] ──→ AfterTool │
│                                                │
│  PreCompress (if context full)                 │
│                                                │
│  Notification (system events)                  │
│                                                │
└── repeats until AfterAgent ───────────────────┘
  │
  ▼
AfterAgent
  │
  ▼
SessionEnd
```

### Codex CLI Lifecycle

```
[AGENTS.md loaded]
  │
  ▼
[session starts]
  │
  ▼
┌─── Agentic Loop ──────────────────────────────┐
│                                                │
│  [no hook intercept points]                    │
│  [tool approval via approval_policy config]    │
│                                                │
└── repeats until done ─────────────────────────┘
  │
  ▼
[notify script called if configured]
```

Codex has **no hook system**. It has a `notify` config option (a command run on session events) and approval policies, but no programmable lifecycle hooks.

---

## 2. Claude Code — Complete Hook Reference

### 2.1 Hook Types

| Type | Description | Events Supported |
|------|-------------|-----------------|
| `command` | Shell script, receives JSON on stdin, returns via stdout + exit code | All 17 events |
| `http` | HTTP POST to a URL, JSON body, response parsed same as command | 8 events (tool + prompt events) |
| `prompt` | Single-turn LLM evaluation, returns `{ok: true/false}` | 8 events (tool + prompt events) |
| `agent` | Multi-turn subagent with tool access (Read, Grep, Glob), returns `{ok: true/false}` | 8 events (tool + prompt events) |

**Events supporting all 4 types:** `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `TaskCompleted`

**Events supporting only `command`:** `SessionStart`, `SessionEnd`, `InstructionsLoaded`, `ConfigChange`, `Notification`, `SubagentStart`, `TeammateIdle`, `PreCompact`, `WorktreeCreate`, `WorktreeRemove`

### 2.2 Hook Events — Full Catalog

#### SessionStart
- **When:** Session begins or resumes
- **Lifecycle position:** First event in session
- **Matcher values:** `startup`, `resume`, `clear`, `compact`
- **Can block:** No
- **Input fields:** `source`, `model`, `agent_type` (optional)
- **Output capability:** `additionalContext` — injected into Claude's context. Also supports `CLAUDE_ENV_FILE` for persisting environment variables for the session
- **Use cases:** Load dev context (open issues, recent changes), set environment variables, initialize tooling

#### InstructionsLoaded
- **When:** CLAUDE.md or `.claude/rules/*.md` loaded into context
- **Lifecycle position:** Async, fires at session start and on lazy directory traversal
- **Matcher:** None (fires on every load)
- **Can block:** No
- **Input fields:** `file_path`, `memory_type` (User/Project/Local/Managed), `load_reason` (session_start/nested_traversal/path_glob_match/include), `globs`, `trigger_file_path`, `parent_file_path`
- **Output capability:** None (observability only)
- **Use cases:** Audit logging, compliance tracking, understanding which instructions are active

#### UserPromptSubmit
- **When:** User submits a prompt, before Claude processes it
- **Lifecycle position:** After SessionStart, before agentic loop
- **Matcher:** None (fires on every prompt)
- **Can block:** Yes — `decision: "block"` prevents processing and erases the prompt
- **Input fields:** `prompt`
- **Output capability:** `additionalContext`, plain text stdout added as context, `decision: "block"` with `reason`
- **Use cases:** Prompt validation, content filtering, auto-inject context based on prompt content

#### PreToolUse
- **When:** After Claude creates tool parameters, before execution
- **Lifecycle position:** Inside agentic loop, before tool runs
- **Matcher:** Tool name regex — `Bash`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Agent`, `WebFetch`, `WebSearch`, `mcp__*`
- **Can block:** Yes — `permissionDecision: "deny"` blocks the call
- **Input fields:** `tool_name`, `tool_input` (varies by tool — command, file_path, pattern, etc.), `tool_use_id`
- **Output capability:** `permissionDecision` (allow/deny/ask), `permissionDecisionReason`, `updatedInput` (modify tool args before execution), `additionalContext`
- **Use cases:** Block dangerous commands (`rm -rf`), enforce file access policies, rewrite tool inputs, auto-approve safe operations

#### PermissionRequest
- **When:** Permission dialog is about to be shown to user
- **Lifecycle position:** Inside agentic loop, after PreToolUse (only if permission needed)
- **Matcher:** Tool name regex (same as PreToolUse)
- **Can block:** Yes — `decision.behavior: "deny"` denies permission
- **Input fields:** `tool_name`, `tool_input`, `permission_suggestions` (array of "always allow" options)
- **Output capability:** `decision.behavior` (allow/deny), `decision.updatedInput`, `decision.updatedPermissions`, `decision.message`, `decision.interrupt`
- **Use cases:** Auto-approve known-safe operations, enforce security policies, modify tool inputs before approval

#### PostToolUse
- **When:** After a tool completes successfully
- **Lifecycle position:** Inside agentic loop, after tool execution
- **Matcher:** Tool name regex (same as PreToolUse)
- **Can block:** No (tool already ran) — but `decision: "block"` feeds reason back to Claude
- **Input fields:** `tool_name`, `tool_input`, `tool_response`, `tool_use_id`
- **Output capability:** `decision: "block"` with `reason`, `additionalContext`, `updatedMCPToolOutput` (MCP tools only)
- **Use cases:** Auto-lint after Write/Edit, log operations, inject corrective feedback, modify MCP tool output

#### PostToolUseFailure
- **When:** After a tool execution fails
- **Lifecycle position:** Inside agentic loop, after failed tool execution
- **Matcher:** Tool name regex (same as PreToolUse)
- **Can block:** No (tool already failed)
- **Input fields:** `tool_name`, `tool_input`, `tool_use_id`, `error`, `is_interrupt`
- **Output capability:** `additionalContext`
- **Use cases:** Log failures, send alerts, provide Claude with corrective context

#### Notification
- **When:** Claude Code sends a notification
- **Lifecycle position:** Any time during session
- **Matcher:** Notification type — `permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_dialog`
- **Can block:** No
- **Input fields:** `message`, `title`, `notification_type`
- **Output capability:** `additionalContext`
- **Use cases:** Forward to Slack/email, desktop notifications, custom alerting

#### SubagentStart
- **When:** A subagent is spawned via the Agent tool
- **Lifecycle position:** Inside agentic loop, when Agent tool fires
- **Matcher:** Agent type — `Bash`, `Explore`, `Plan`, or custom agent names
- **Can block:** No
- **Input fields:** `agent_id`, `agent_type`
- **Output capability:** `additionalContext` (injected into subagent's context)
- **Use cases:** Inject security guidelines, log agent spawning, add context to subagents

#### SubagentStop
- **When:** A subagent finishes responding
- **Lifecycle position:** Inside agentic loop, after subagent completes
- **Matcher:** Agent type (same as SubagentStart)
- **Can block:** Yes — `decision: "block"` prevents the subagent from stopping
- **Input fields:** `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message`
- **Output capability:** `decision: "block"` with `reason`
- **Use cases:** Quality gates on subagent output, force subagent to continue if work incomplete

#### Stop
- **When:** Main Claude agent finishes responding (not on user interrupt)
- **Lifecycle position:** End of agentic loop
- **Matcher:** None (fires on every stop)
- **Can block:** Yes — `decision: "block"` with `reason` forces Claude to continue
- **Input fields:** `stop_hook_active`, `last_assistant_message`
- **Output capability:** `decision: "block"` with `reason`
- **Use cases:** Verify all tasks complete, run test suite before stopping, enforce checklist completion

#### TeammateIdle
- **When:** An agent team teammate is about to go idle
- **Lifecycle position:** After teammate finishes its turn
- **Matcher:** None (fires on every occurrence)
- **Can block:** Yes — exit code 2 sends feedback and continues; `continue: false` stops entirely
- **Input fields:** `teammate_name`, `team_name`
- **Output capability:** Exit code 2 stderr feedback, or `continue: false` with `stopReason`
- **Use cases:** Enforce quality gates, verify build artifacts exist, require passing tests

#### TaskCompleted
- **When:** A task is being marked as completed
- **Lifecycle position:** When agent or teammate marks task done
- **Matcher:** None (fires on every occurrence)
- **Can block:** Yes — exit code 2 prevents completion and feeds back stderr
- **Input fields:** `task_id`, `task_subject`, `task_description`, `teammate_name`, `team_name`
- **Output capability:** Exit code 2 stderr feedback, or `continue: false` with `stopReason`
- **Use cases:** Run tests before task closure, verify acceptance criteria, enforce code review

#### ConfigChange
- **When:** A configuration file changes during a session
- **Lifecycle position:** Any time during session
- **Matcher:** Config source — `user_settings`, `project_settings`, `local_settings`, `policy_settings`, `skills`
- **Can block:** Yes — `decision: "block"` prevents change (except `policy_settings`)
- **Input fields:** `source`, `file_path`
- **Output capability:** `decision: "block"` with `reason`
- **Use cases:** Audit config changes, enforce admin-only settings, security policies

#### WorktreeCreate
- **When:** Worktree being created (`--worktree` or subagent with `isolation: "worktree"`)
- **Lifecycle position:** Before isolated session starts
- **Matcher:** None
- **Can block:** Yes — non-zero exit fails creation
- **Input fields:** `name` (worktree slug)
- **Output:** Must print absolute path to created worktree on stdout
- **Use cases:** Custom VCS (SVN, Perforce, Mercurial), custom worktree setup

#### WorktreeRemove
- **When:** Worktree being removed (session exit or subagent finish)
- **Lifecycle position:** After isolated session ends
- **Matcher:** None
- **Can block:** No
- **Input fields:** `worktree_path`
- **Output capability:** None (cleanup only)
- **Use cases:** Custom VCS cleanup, archive changes

#### PreCompact
- **When:** Before context compaction
- **Lifecycle position:** Inside agentic loop, when context window full
- **Matcher:** `manual` or `auto`
- **Can block:** No
- **Input fields:** `trigger`, `custom_instructions`
- **Output capability:** None (observability)
- **Use cases:** Save state before compaction, notify user, log compaction events

#### SessionEnd
- **When:** Session terminates
- **Lifecycle position:** Last event in session
- **Matcher:** Reason — `clear`, `logout`, `prompt_input_exit`, `bypass_permissions_disabled`, `other`
- **Can block:** No
- **Input fields:** `reason`
- **Output capability:** None (cleanup only)
- **Use cases:** Log session stats, save state, cleanup resources

### 2.3 Common Input Fields (all events)

| Field | Description |
|-------|-------------|
| `session_id` | Current session identifier |
| `transcript_path` | Path to conversation JSONL |
| `cwd` | Current working directory |
| `permission_mode` | `default`, `plan`, `acceptEdits`, `dontAsk`, `bypassPermissions` |
| `hook_event_name` | Name of the event that fired |
| `agent_id` | (subagent only) Unique subagent identifier |
| `agent_type` | (subagent/--agent only) Agent name |

### 2.4 Configuration Locations

| Location | Scope | Shareable |
|----------|-------|-----------|
| `~/.claude/settings.json` | All projects | No |
| `.claude/settings.json` | Single project | Yes (commit) |
| `.claude/settings.local.json` | Single project | No (gitignored) |
| Managed policy settings | Organization | Yes (admin) |
| Plugin `hooks/hooks.json` | When plugin enabled | Yes |
| Skill/Agent YAML frontmatter | While component active | Yes |

### 2.5 Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAUDE_PROJECT_DIR` | Project root path |
| `CLAUDE_PLUGIN_ROOT` | Plugin root directory |
| `CLAUDE_SESSION_ID` | Current session ID |
| `CLAUDE_ENV_FILE` | (SessionStart only) File path for persisting env vars |
| `CLAUDE_CODE_REMOTE` | `"true"` in remote web environments |

---

## 3. Gemini CLI — Complete Hook Reference

### 3.1 Hook Types

| Type | Description |
|------|-------------|
| `command` | Shell script, receives JSON on stdin, returns JSON on stdout. **Only type currently supported.** |

### 3.2 Hook Events — Full Catalog

#### SessionStart
- **When:** Session begins (startup, resume, or clear)
- **Lifecycle position:** First event
- **Matcher:** Exact string match
- **Can block:** No (inject context only)
- **Use cases:** Initialize resources, load context, set up logging

#### SessionEnd
- **When:** Session ends (exit or clear)
- **Lifecycle position:** Last event
- **Matcher:** Exact string match
- **Can block:** No (advisory)
- **Use cases:** Clean up resources, save state, log session summary

#### BeforeAgent
- **When:** After user submits prompt, before agent planning begins
- **Lifecycle position:** Before agentic loop starts
- **Matcher:** Exact string or regex
- **Can block:** Yes (Block Turn) — can also inject context
- **Use cases:** Add context to prompts, validate user input, inject system instructions

#### AfterAgent
- **When:** Agent loop completes
- **Lifecycle position:** After agentic loop ends
- **Matcher:** Exact string or regex
- **Can block:** Yes (Retry/Halt) — can force agent to retry
- **Use cases:** Review output quality, force retry on poor results, post-processing

#### BeforeModel
- **When:** Before sending request to LLM
- **Lifecycle position:** Inside agentic loop, before each LLM call
- **Matcher:** Exact string or regex
- **Can block:** Yes (Block Turn/Mock) — can mock responses
- **Use cases:** Modify prompts, swap models dynamically, rate limiting, inject system messages

#### AfterModel
- **When:** After receiving LLM response
- **Lifecycle position:** Inside agentic loop, after each LLM response
- **Matcher:** Exact string or regex
- **Can block:** Yes (Block Turn/Redact) — can redact response content
- **Use cases:** Filter sensitive data from responses, log model interactions, content moderation

#### BeforeToolSelection
- **When:** Before LLM selects which tools to use
- **Lifecycle position:** Inside agentic loop, between model response and tool execution
- **Matcher:** Exact string or regex
- **Can block:** Yes (Filter Tools) — can remove tools from available set
- **Use cases:** Restrict tool access per-project, optimize tool availability, security policies

#### BeforeTool
- **When:** Before a specific tool executes
- **Lifecycle position:** Inside agentic loop, before tool execution
- **Matcher:** Tool name regex
- **Can block:** Yes (Block Tool/Rewrite) — can block or modify tool arguments
- **Use cases:** Validate arguments, block dangerous operations, rewrite file paths, security checks

#### AfterTool
- **When:** After a tool execution completes
- **Lifecycle position:** Inside agentic loop, after tool execution
- **Matcher:** Tool name regex
- **Can block:** Yes (Block Result/Context) — can hide results or inject context
- **Use cases:** Process tool output, inject additional context, redact sensitive results

#### PreCompress
- **When:** Before context compression
- **Lifecycle position:** Inside agentic loop, when context window full
- **Matcher:** Exact string
- **Can block:** No (advisory)
- **Use cases:** Save important state before compression, notify user

#### Notification
- **When:** System notification occurs
- **Lifecycle position:** Any time during session
- **Matcher:** Exact string
- **Can block:** No (advisory)
- **Use cases:** Forward to external logging, Slack alerts, desktop notifications

### 3.3 Configuration

```json
{
  "hooks": {
    "EventName": [
      {
        "matcher": "pattern",
        "hooks": [
          {
            "name": "hook-identifier",
            "type": "command",
            "command": "/path/to/script.sh",
            "timeout": 5000,
            "description": "What this hook does"
          }
        ]
      }
    ]
  }
}
```

### 3.4 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — JSON output parsed |
| `2` | System Block — critical failure, blocks action |
| Other | Warning — proceeds with original parameters |

### 3.5 Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_PROJECT_DIR` | Project root path |
| `GEMINI_SESSION_ID` | Unique session identifier |
| `GEMINI_CWD` | Current working directory |
| `CLAUDE_PROJECT_DIR` | Compatibility alias |

### 3.6 Configuration Locations

| Location | Scope |
|----------|-------|
| `.gemini/settings.json` (project) | Single project (highest priority) |
| `~/.gemini/settings.json` (user) | All projects |
| System settings | System-wide |
| Extensions | Via extensions |

---

## 4. Codex CLI — Extensibility Reference

Codex has **no hook system**. Its extensibility is configuration-driven.

### 4.1 What Codex Has Instead

| Feature | How It Works |
|---------|--------------|
| **Approval policies** | `approval_policy` in config.toml — `untrusted`, `on-request`, `never` — controls tool auto-approval |
| **Notify command** | `notify = ["python3", "/path/to/script.py"]` — external command called on session events |
| **MCP servers** | `[mcp_servers.<name>]` in config.toml — STDIO/HTTP servers launched at session start, expose tools |
| **AGENTS.md** | System prompt — narrative instructions, no structured fields |
| **Profiles** | `[profiles.<name>]` — named config sets switchable via `--profile` |
| **Multi-agent** | `[agents]` section — role-based agent definitions |

### 4.2 AGENTS.md Discovery Chain

```
~/.codex/AGENTS.override.md   (global override)
~/.codex/AGENTS.md             (global default)
  │
  ├── <git-root>/AGENTS.override.md
  ├── <git-root>/AGENTS.md
  │     │
  │     ├── <subdir>/AGENTS.override.md
  │     └── <subdir>/AGENTS.md
  │           │
  │           └── ... (walks toward cwd)
```

Files concatenate from root toward cwd. Later files override earlier guidance. Max combined size: `project_doc_max_bytes` (default 32 KiB).

### 4.3 Configuration File

`~/.codex/config.toml` (user) and `.codex/config.toml` (project):

| Key | Description |
|-----|-------------|
| `model` | Primary model |
| `model_reasoning_effort` | `low`, `medium`, `high` |
| `approval_policy` | Tool approval behavior |
| `sandbox_mode` | `workspace-write` or `danger-full-access` |
| `writable_roots` | Directories Codex can write to |
| `network_access` | Allow outbound network |
| `notify` | External notification command |
| `[profiles.<name>]` | Named config presets |
| `[mcp_servers.<name>]` | MCP server definitions |
| `[agents]` | Multi-agent role definitions |

---

## 5. Skills & Commands Comparison

### 5.1 Claude Code Skills

**Location:** `~/.claude/skills/<name>/SKILL.md` (user) or `.claude/skills/<name>/SKILL.md` (project)

**Format:** YAML frontmatter + markdown instructions

```yaml
---
name: my-skill
description: What it does and when to use it
disable-model-invocation: true    # manual /slash only
user-invocable: false             # Claude-only, hidden from / menu
allowed-tools: Read, Grep, Glob   # restrict tool access
model: opus                       # model override
context: fork                     # run in subagent
agent: Explore                    # subagent type
argument-hint: "[filename]"       # autocomplete hint
hooks:                            # scoped hooks (active while skill runs)
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/check.sh"
---

Instructions here...
$ARGUMENTS         # replaced with user input
$ARGUMENTS[0]      # positional args
$0, $1, $2         # shorthand
${CLAUDE_SESSION_ID}
${CLAUDE_SKILL_DIR}
!`shell command`   # dynamic context injection (runs before skill)
```

**Supporting files:**
```
my-skill/
├── SKILL.md           # required
├── template.md        # optional templates
├── examples/
│   └── sample.md      # example output
└── scripts/
    └── helper.py      # executable scripts
```

**Invocation control:**

| Config | User can invoke | Claude can invoke |
|--------|----------------|-------------------|
| (default) | Yes (`/name`) | Yes (auto) |
| `disable-model-invocation: true` | Yes | No |
| `user-invocable: false` | No | Yes |

### 5.2 Claude Code Subagents

**Location:** `.claude/agents/<name>.md` (project) or `~/.claude/agents/<name>.md` (user)

**Format:** YAML frontmatter + markdown system prompt

```yaml
---
name: fleet-orchestrator
description: Orchestrates multi-agent workflows
tools: Read(//.claude/fleet/**), Write(//.claude/fleet/bus/**)
model: opus
---

System prompt / instructions here...
```

**Key fields:** `name`, `description`, `tools` (permission scoping with glob patterns), `model`

### 5.3 Gemini CLI Custom Commands

**Location:** `~/.gemini/commands/` (global) or `<project>/.gemini/commands/` (project)

**Format:** TOML files

```toml
description = "Run and explain test failures"
prompt = """
Run the test suite and explain any failures:
!{npm test 2>&1}

Focus on: {{args}}
"""
```

**Features:**
- `{{args}}` — argument injection (shell-escaped in `!{...}` blocks)
- `!{command}` — shell command execution (output injected into prompt)
- `@{path}` — file/directory content injection (supports images, PDFs, audio, video)
- Subdirectories create namespaced commands: `git/commit.toml` → `/git:commit`
- `/commands reload` to hot-reload without restarting

### 5.4 Codex CLI

No custom commands or skills system. Built-in slash commands only (25+). MCP servers are the extensibility mechanism.

---

## 6. Hook Event Cross-Reference

This table maps equivalent hooks across harnesses. Where a harness lacks a specific hook, the closest alternative is noted.

| Lifecycle Point | Claude Code | Gemini CLI | Codex CLI |
|----------------|-------------|------------|-----------|
| Session start | `SessionStart` | `SessionStart` | — (`notify` cmd) |
| Session end | `SessionEnd` | `SessionEnd` | — (`notify` cmd) |
| User prompt received | `UserPromptSubmit` | `BeforeAgent` | — |
| Before LLM call | — | `BeforeModel` | — |
| After LLM response | — | `AfterModel` | — |
| Tool selection | — | `BeforeToolSelection` | — |
| Before tool execution | `PreToolUse` | `BeforeTool` | — (`approval_policy`) |
| Permission dialog | `PermissionRequest` | — | — |
| After tool success | `PostToolUse` | `AfterTool` | — |
| After tool failure | `PostToolUseFailure` | — | — |
| Agent turn complete | `Stop` | `AfterAgent` | — |
| Subagent start | `SubagentStart` | — | — |
| Subagent stop | `SubagentStop` | — | — |
| Teammate idle | `TeammateIdle` | — | — |
| Task completed | `TaskCompleted` | — | — |
| Config changed | `ConfigChange` | — | — |
| Instructions loaded | `InstructionsLoaded` | — | — |
| Before compaction | `PreCompact` | `PreCompress` | — |
| Notification | `Notification` | `Notification` | — (`notify` cmd) |
| Worktree create | `WorktreeCreate` | — | — |
| Worktree remove | `WorktreeRemove` | — | — |

**Totals:** Claude Code: 17 events | Gemini CLI: 11 events | Codex CLI: 0 events (config only)

---

## 7. What Can Block (Decision Control Summary)

Understanding which hooks can actually prevent an action is critical for security and governance.

### Claude Code — Blocking Hooks

| Event | Block Mechanism | Effect |
|-------|----------------|--------|
| `PreToolUse` | `permissionDecision: "deny"` | Prevents tool call |
| `PermissionRequest` | `decision.behavior: "deny"` | Denies permission |
| `UserPromptSubmit` | `decision: "block"` | Erases and rejects prompt |
| `Stop` | `decision: "block"` | Forces Claude to continue |
| `SubagentStop` | `decision: "block"` | Forces subagent to continue |
| `TeammateIdle` | Exit code 2 | Teammate continues with feedback |
| `TaskCompleted` | Exit code 2 | Task stays open with feedback |
| `ConfigChange` | `decision: "block"` | Settings change rejected |
| `WorktreeCreate` | Non-zero exit | Worktree creation fails |

### Gemini CLI — Blocking Hooks

| Event | Block Mechanism | Effect |
|-------|----------------|--------|
| `BeforeAgent` | Block Turn | Prompt rejected |
| `AfterAgent` | Retry/Halt | Force retry or stop |
| `BeforeModel` | Block Turn/Mock | LLM call blocked or mocked |
| `AfterModel` | Block Turn/Redact | Response blocked or redacted |
| `BeforeToolSelection` | Filter Tools | Tools removed from available set |
| `BeforeTool` | Block Tool/Rewrite | Tool call blocked or args rewritten |
| `AfterTool` | Block Result | Tool result hidden or modified |

---

## 8. Why This Matters for `agents`

With this reference, an agent managing hooks/skills can:

1. **Know what's available** — enumerate all 17 Claude events and 11 Gemini events, understand what each does
2. **Know the chain order** — understand that `PreToolUse` fires before `PermissionRequest`, which fires before the tool runs, which fires `PostToolUse` or `PostToolUseFailure`
3. **Know what data flows** — each hook receives specific JSON fields; a registry entry can declare what fields it reads
4. **Know what can be blocked** — security hooks need blocking capability; logging hooks don't
5. **Know where config lives** — install hooks to the right settings file for the right scope
6. **Know harness gaps** — Codex has no hooks, Gemini has no subagent or permission events, Claude lacks model-level intercept

This enables the `agents registry` to intelligently install, validate, and describe hooks — and for agents themselves to suggest or configure hooks based on what the user wants to accomplish.

---

## References

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Skills](https://code.claude.com/docs/en/skills)
- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)
- [Gemini CLI Hooks](https://geminicli.com/docs/hooks/)
- [Gemini CLI Custom Commands](https://geminicli.com/docs/cli/custom-commands/)
- [Gemini CLI Configuration](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/configuration.md)
- [Codex CLI Features](https://developers.openai.com/codex/cli/features/)
- [Codex CLI AGENTS.md](https://developers.openai.com/codex/guides/agents-md/)
- [Codex CLI Advanced Config](https://developers.openai.com/codex/config-advanced/)
- [Codex CLI Slash Commands](https://developers.openai.com/codex/cli/slash-commands/)
- [Agent Skills Open Standard](https://agentskills.io)
