# Discussion: Managing Hooks, Skills & Agents Across Harnesses

**Date:** 2026-03-06
**Status:** Exploration / RFC

## The Opportunity

Each coding agent harness (Claude, Codex, Gemini) has its own extensibility system — but they're all variations of the same idea: **files in folders** that customize agent behavior.

| Concept | Claude | Codex | Gemini |
|---------|--------|-------|--------|
| **System prompt** | `CLAUDE.md` | `AGENTS.md` | `GEMINI.md` |
| **Hooks** | `.claude/settings.json` → `hooks` | MCP servers in `config.toml` | `.gemini/settings.json` → `hooks` |
| **Skills / Commands** | `.claude/skills/<name>/SKILL.md` | `.codex/commands/` (slash commands) | `.gemini/commands/` |
| **Subagents** | `.claude/agents/<name>.md` | `[agents]` in `config.toml` | N/A (yet) |
| **Config** | `.claude/settings.json` | `~/.codex/config.toml` | `.gemini/settings.json` |
| **Scope** | project `.claude/` + user `~/.claude/` | project + `~/.codex/` | project `.gemini/` + `~/.gemini/` |

The `agents` CLI already unifies **session browsing** across harnesses. The question is: can it also unify **extensibility management** — hooks, skills, agents, and md files?

## What's Actually in These Folders

### Subagents (`.claude/agents/*.md`)

Markdown files with YAML frontmatter defining specialized subagents:

```yaml
---
name: fleet-orchestrator
description: Metacognitive orchestrator managing the agent fleet
tools: Read(//.claude/fleet/**), Write(//.claude/fleet/bus/**)
model: opus
---

# Fleet Orchestrator
Instructions here...
```

Key fields: `name`, `description`, `tools` (permission scoping), `model`.

### Skills (`.claude/skills/<name>/SKILL.md`)

Directories with a `SKILL.md` entrypoint plus supporting files:

```yaml
---
name: explain-code
description: Explains code with visual diagrams and analogies
disable-model-invocation: true  # only manual /slash invocation
allowed-tools: Read, Grep
context: fork  # run in subagent
---

Instructions here...
```

Key fields: `name`, `description`, `disable-model-invocation`, `user-invocable`, `allowed-tools`, `model`, `context`, `agent`, `hooks`.

Skills follow the [Agent Skills](https://agentskills.io) open standard — which means they're theoretically portable across tools.

### Hooks

Claude and Gemini both use `settings.json` with similar structures:

**Claude hook events:** `PreToolUse`, `PostToolUse`, `Notification`, `Stop`, `SubagentStop`
**Gemini hook events:** `SessionStart`, `SessionEnd`, `BeforeAgent`, `AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `BeforeTool`, `AfterTool`, `PreCompress`, `Notification`

Gemini has richer lifecycle coverage. Claude has hook support embedded in skill frontmatter. Both execute shell commands synchronously.

Codex doesn't have hooks — it uses MCP servers for extensibility.

### MD Files (System Prompts)

- `CLAUDE.md` — read by Claude Code at session start
- `AGENTS.md` — read by Codex at session start
- `GEMINI.md` — read by Gemini CLI at session start

Same purpose, different filenames. Projects that use multiple harnesses need to maintain parallel files.

## What Could `agents` Manage?

### Tier 1: Visibility (low risk, high value)

Just **list and inspect** what's configured across all harnesses, without modifying anything.

```
agents config                    # overview of all agent configs
agents config hooks              # list hooks across all harnesses
agents config skills             # list skills
agents config agents             # list subagent definitions
agents config md                 # list all CLAUDE.md / AGENTS.md / GEMINI.md files
agents config show <name>        # show a specific skill/agent/hook
```

This is pure read — no writes. Gives you a unified view of what's configured everywhere.

### Tier 2: Sync / Mirror (medium risk, medium value)

Keep system prompt files in sync across harnesses:

```
agents sync md                   # sync CLAUDE.md → AGENTS.md + GEMINI.md
agents sync md --from claude     # explicit source
agents sync md --dry-run         # preview changes
```

The md files serve the same purpose. A project using all three harnesses shouldn't need to manually maintain three copies. The sync could handle format differences (e.g., Codex uses `AGENTS.override.md` for global, Claude uses `~/.claude/CLAUDE.md`).

### Tier 3: Portable Skills Registry (high ambition)

Since skills follow the [Agent Skills open standard](https://agentskills.io), there's an opportunity for a local registry:

```
agents skills list               # list all installed skills
agents skills install <url>      # install from git/registry
agents skills sync               # sync skills across harnesses
agents skills publish <name>     # package for sharing
```

**The cross-harness translation problem:**

A Claude skill (`SKILL.md` with frontmatter) could theoretically be translated to:
- A Gemini custom command (`.gemini/commands/`)
- A Codex slash command (`.codex/commands/`)

The core content (markdown instructions) is portable. The frontmatter fields differ but map roughly:

| Claude SKILL.md | Gemini equivalent | Codex equivalent |
|-----------------|-------------------|------------------|
| `name` | command filename | command filename |
| `description` | file content | file content |
| `allowed-tools` | hook-based restriction | approval mode |
| `context: fork` | N/A | multi-agent |
| `disable-model-invocation` | N/A | N/A |

### Tier 4: Unified Hook Management (high complexity)

Hooks are the hardest to unify because the event models differ significantly. But common patterns exist:

| Pattern | Claude | Gemini |
|---------|--------|--------|
| Pre-tool validation | `PreToolUse` | `BeforeTool` |
| Post-tool action | `PostToolUse` | `AfterTool` |
| Session lifecycle | N/A | `SessionStart` / `SessionEnd` |
| Notifications | `Notification` | `Notification` |

A unified hook config could abstract over these:

```yaml
# ~/.ab0t/.agents/hooks.yaml
hooks:
  before_tool:
    - name: block-rm-rf
      match: "Bash(rm *)"
      action: deny
      message: "Blocked dangerous rm command"

  after_tool:
    - name: log-writes
      match: "Write(*)"
      command: "echo 'File written: $FILE' >> ~/agent-log.txt"
```

The `agents` CLI would translate this into each harness's native format.

## The Subagent Registry Idea

The `.claude/agents/` folder is the most interesting primitive. These are full agent definitions — personality, tools, model selection. Currently they're project-scoped and Claude-only.

A registry could make them:
- **Shareable** — publish/install agent definitions
- **Cross-project** — user-level agents at `~/.claude/agents/`
- **Discoverable** — `agents registry search "code review"`

```
agents registry list             # local agent definitions
agents registry search <query>   # search remote registry
agents registry install <name>   # install an agent definition
agents registry publish <name>   # publish to registry
```

This is more ambitious than skill management because agents have tool permissions, model preferences, and complex system prompts. But the format is just markdown + YAML frontmatter — inherently portable.

## Architecture Considerations

### Where Does State Live?

Following existing conventions:
- **Per-project config** stays in `.claude/`, `.gemini/`, `.codex/` (we never write to these directly)
- **`agents` CLI metadata** stays in `~/.ab0t/.agents/`
- **Shared/synced definitions** could live in `~/.ab0t/.agents/skills/`, `~/.ab0t/.agents/hooks/` etc.
- **Registry cache** at `~/.ab0t/.agents/registry/`

### Safety Rules (Existing)

- NEVER write to `~/.claude/settings.json` or `~/.codex/config.json`
- NEVER write to original session files
- All writes isolated to `~/.ab0t/.agents/` namespace
- Read-only access to harness config directories

This means Tier 1 (visibility) is safe immediately. Tier 2+ would need to write to project-level `.claude/`, `.gemini/`, `.codex/` dirs — which requires relaxing the safety rules for specific, well-defined operations (like creating/updating AGENTS.md from CLAUDE.md).

### What Exists Already

- [anthropics/skills](https://github.com/anthropics/skills) — official Anthropic skill repository
- [SkillsMP](https://skillsmp.com) — community skills marketplace (96k+ skills)
- [SkillHub](https://www.skillhub.club/) — another community marketplace
- [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — 500+ skills compatible with Claude, Codex, Gemini, Cursor
- [Agent Skills open standard](https://agentskills.io) — cross-tool skill format
- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) — curated hooks, skills, commands, plugins

The ecosystem is already converging on a common skill format. The gap is **local management and cross-harness sync**.

## Recommended Approach

**Start with Tier 1** — pure visibility. Add `agents config` as a new module that scans all three harness directories and reports what's configured. No writes, no risk, immediate value.

Then evaluate whether Tier 2 (md sync) solves a real pain point in daily workflow before building further.

## Open Questions

1. **Is md-file sync actually useful?** Or do people intentionally diverge their CLAUDE.md vs AGENTS.md because each harness has different strengths?
2. **Should skills be copied or symlinked?** Symlinks keep a single source of truth but break if the source moves.
3. **How do we handle harness-specific frontmatter?** A skill using `context: fork` has no Gemini equivalent.
4. **Who owns the registry?** Self-hosted git repos? A central index? Package manager model (npm-style)?
5. **Do hooks even need unification?** The event models are so different that a common abstraction might be more confusing than helpful.

## Clarification: Not Unification — Management

The goal is **not** to create a unified hook/skill abstraction that papers over differences between harnesses. Each harness exposes its own rich set of hooks, events, and skill formats — and that's fine. The goal is to **manage what each harness already offers**, through a registry and package-manager-like workflow.

Think of it like `apt` or `brew` — you don't redesign the software, you manage installing, listing, and updating it.

### The Real Use Cases

**1. "I want to set up my system based on a preset"**

A new developer joins the team, or you set up a new machine. Instead of manually configuring hooks and skills for each harness:

```
agents setup preset team-standard      # install team's standard hooks + skills
agents setup preset security-hardened  # pre-built security-focused config
agents setup preset fullstack          # hooks + skills for a typical web project
```

A preset is a manifest that says: install these Claude hooks, these Gemini hooks, these skills, these agents. Each item is native to its harness — no translation layer.

```yaml
# presets/team-standard.yaml
name: team-standard
description: Standard setup for the engineering team

claude:
  hooks:
    - registry: community/block-dangerous-commands
    - registry: community/auto-lint-on-save
  skills:
    - registry: anthropic/claude-api
    - registry: community/pr-review
    - registry: team/deploy-staging

gemini:
  hooks:
    - registry: community/session-logger
  commands:
    - registry: community/explain-code

codex:
  commands:
    - registry: community/test-runner
```

**2. "I want to browse and install community hooks and skills"**

Each harness has its own growing ecosystem. The registry indexes them all, tagged by harness:

```
agents registry search "code review"
  [claude:skill]  anthropic/pr-review         ★ 2.3k  Official PR review skill
  [claude:skill]  community/deep-review       ★ 891   Multi-agent code review
  [claude:hook]   community/auto-review       ★ 445   Auto-trigger review on commit
  [gemini:cmd]    community/review-diff       ★ 312   Review git diff with Gemini
  [codex:cmd]     community/review-changes    ★ 198   Codex code review command

agents registry install community/pr-review          # installs to ~/.claude/skills/
agents registry install community/session-logger      # installs to ~/.gemini/settings.json hooks
agents registry install community/auto-review         # installs to ~/.claude/settings.json hooks
```

The install target is determined by the item's harness tag. A Claude skill goes to `~/.claude/skills/`. A Gemini hook gets merged into `.gemini/settings.json`. No abstraction — just routing to the right place.

**3. "I want to see what I have installed and where"**

```
agents config

Claude Code
  hooks: 3 (PreToolUse: 2, PostToolUse: 1)
  skills: 5 (user: ~/.claude/skills/, project: .claude/skills/)
  agents: 12 (project: .claude/agents/)
  md: CLAUDE.md (1.2K)

Gemini CLI
  hooks: 1 (BeforeTool: 1)
  commands: 2 (user: ~/.gemini/commands/)
  md: (none)

Codex CLI
  commands: 0
  md: AGENTS.md (800B)

agents config hooks              # detailed hook listing per harness
agents config skills             # all skills across harnesses
agents config agents             # subagent definitions
```

**4. "I want to share my hooks/skills with the team"**

```
agents registry publish .claude/skills/deploy/    # publish a skill
agents registry publish --hooks block-rm           # publish a hook config
agents registry publish --preset my-setup          # publish your whole setup as a preset
```

### Registry Architecture

The registry is just a **git-backed index** — no central server needed.

```
~/.ab0t/.agents/registry/
├── index.json              # cached registry index
├── sources.json            # list of registry sources (git repos)
└── installed.json          # what's installed, where, from which source
```

Default source could be a public GitHub repo (like `awesome-agent-skills`). Teams add their own private sources:

```
agents registry add-source https://github.com/myteam/agent-configs.git
agents registry add-source /path/to/local/repo    # local git repo works too
agents registry update                             # pull latest from all sources
```

Each registry entry is a directory in the source repo:

```
registry-repo/
├── claude/
│   ├── skills/
│   │   └── pr-review/
│   │       ├── SKILL.md
│   │       ├── manifest.yaml    # metadata, version, dependencies
│   │       └── scripts/
│   └── hooks/
│       └── block-dangerous/
│           ├── manifest.yaml
│           └── hook.json        # native Claude hook config fragment
├── gemini/
│   ├── hooks/
│   │   └── session-logger/
│   │       ├── manifest.yaml
│   │       └── hook.json        # native Gemini hook config fragment
│   └── commands/
│       └── explain-code/
│           └── explain-code.md
├── codex/
│   └── commands/
│       └── test-runner/
│           └── test-runner.md
└── presets/
    └── team-standard/
        └── preset.yaml
```

The key insight: **every item in the registry is already in its native harness format**. The registry just indexes, versions, and distributes them. No translation, no abstraction.

### What This Means for `agents`

The `agents` CLI becomes a **package manager for agent extensibility**:

| Analogy | `agents` equivalent |
|---------|---------------------|
| `brew search` | `agents registry search` |
| `brew install` | `agents registry install` |
| `brew list` | `agents config` |
| `brew bundle` | `agents setup preset` |
| `apt update` | `agents registry update` |

It doesn't replace or abstract the harnesses. It manages the files they already read.

## References

- [Claude Code Skills docs](https://code.claude.com/docs/en/skills)
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks)
- [Gemini CLI Hooks](https://geminicli.com/docs/hooks/)
- [Gemini CLI Custom Commands](https://geminicli.com/docs/cli/custom-commands/)
- [Codex CLI AGENTS.md](https://developers.openai.com/codex/guides/agents-md/)
- [Codex CLI Features](https://developers.openai.com/codex/cli/features/)
- [Agent Skills open standard](https://agentskills.io)
- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills)
