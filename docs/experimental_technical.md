# Experimental Commands

`agents` ships with a large set of experimental commands behind a feature gate. These extend the core session browser into a full multi-agent management platform — search, export, cost analysis, cross-agent bridging, session forking, RAG, and more.

## Enabling

```bash
agents experimental on     # enable
agents experimental off    # disable
agents experimental        # check status
```

Or set the environment variable:

```bash
AGENTS_EXPERIMENTAL=1 agents search "auth bug"
```

---

## Command Reference

### Search & Discovery

#### `agents search <query>`

Full-text search across all Claude, Codex, and Gemini sessions.

```bash
agents search "authentication"
agents search "fix.*payment" -n 20
agents search "database migration" -i
```

| Option | Description |
|--------|-------------|
| `-n, --max N` | Max results (default: 10) |
| `-i, --case-sensitive` | Enable case-sensitive matching |

If an LLM is available, results are semantically reranked for relevance. Falls back to keyword ordering otherwise.

---

#### `agents log`

Chronological activity log grouped by date.

```bash
agents log                # this week (default)
agents log --today
agents log --month
agents log --all -n 100
```

| Option | Description |
|--------|-------------|
| `--today` | Today's sessions only |
| `--week` | This week (default) |
| `--month` | This month |
| `--all` | All time |
| `-n, --limit N` | Max entries (default: 50) |

Shows session previews, active duration (excluding gaps > 1h), and per-day groupings.

---

#### `agents cost`

Estimate API costs from token usage across all agents.

```bash
agents cost               # all time
agents cost --today
agents cost --week
agents cost --month
```

| Option | Description |
|--------|-------------|
| `--today` | Today only |
| `--week` | This week |
| `--month` | This month |
| `--all` | All time (default) |

Shows cost breakdowns by model, project, and time period. Includes cache savings analysis. Custom pricing can be set in `~/.ab0t/.agents/pricing.json`.

Built-in pricing covers Claude (Opus, Sonnet, Haiku) and GPT-5.3-codex.

---

#### `agents diff <session>`

Show what files were changed and commands run during a session.

```bash
agents diff 1                        # session #1 from last show
agents diff abc123 --project /path
```

| Option | Description |
|--------|-------------|
| `--project, -p PATH` | Specify project path |

Extracts Write/Edit operations (Claude) or file_write/file_edit events (Codex). Also extracts git commit messages and unique commands run.

---

### Export & Backup

#### `agents export <session>`

Export a session conversation to markdown, text, or JSON.

```bash
agents export 1                          # markdown to file
agents export 1 --format txt             # plain text
agents export 1 --format json -o -       # JSON to stdout
agents export abc123 -o ~/exports/auth.md
```

| Option | Description |
|--------|-------------|
| `--format, -f` | `md` (default), `txt`, or `json` |
| `--output, -o` | Output file path (`-` for stdout) |

Includes timestamps, model names, and tool usage context. Handles both Claude and Codex session formats.

---

#### `agents backup`

Backup and restore all coding agent session data.

```bash
agents backup                  # create full backup
agents backup --incremental    # only changed files since last backup
agents backup --list           # list existing backups
agents backup --restore <file> # restore from backup
```

| Option | Description |
|--------|-------------|
| `--incremental` | Only back up files modified since last backup |
| `--list` | List existing backups |
| `--restore FILE` | Restore from a backup archive |

**What gets backed up:**
- `~/.claude/projects` — Claude sessions
- `~/.claude/settings.json` — Claude config
- `~/.claude.json` — Claude global settings
- `~/.codex/sessions` — Codex sessions
- `~/.codex/config.json` — Codex config
- `~/.codex/history.jsonl` — Codex history
- `~/.ab0t/.agents` — agents cache and metadata

Backups are stored as tar.gz archives in `~/.ab0t/.agents/backups/`.

**Restore conflict resolution:**
- `keep-newer` — keep existing file if it's newer
- `keep-backup` — overwrite with backup version
- `keep-both` — rename existing to `.pre-restore`

---

### Session Management

#### `agents continue`

Smart session resume — scores candidates and picks the best match for your current context.

```bash
agents continue              # auto-pick best session
agents cont --dry-run        # show what would be resumed
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Show scoring without resuming |

**Scoring factors:**
| Factor | Points |
|--------|--------|
| Exact directory match | 100 |
| Parent/child directory | 100 |
| Basename match | 30 |
| Age < 1 hour | 50 |
| Age < 1 day | 30 |
| Age < 1 week | 10 |
| Git branch match | 40 |
| Session > 1MB | 10 |

Shows the best match with score reasoning, plus up to 3 alternatives.

---

#### `agents fork <session>`

Create a branch point from an existing session without modifying the original.

```bash
agents fork 1                # fork entire session
agents fork 1 --at 15        # fork at message 15
```

| Option | Description |
|--------|-------------|
| `--at N` | Fork at message N (default: all messages) |

Forks are stored in `~/.ab0t/.agents/forks/` with UUID names. An index tracks parent session, fork point, and timestamp. Use this to create branching conversation contexts.

---

#### `agents blend <session1> <session2> ...`

Synthesize context from multiple sessions into a single briefing document.

```bash
agents blend 1 2                        # summary mode
agents blend 1 2 3 --mode full          # full context
agents blend abc123 def456 --mode artifacts
```

| Option | Description |
|--------|-------------|
| `--mode, -m` | `summary` (default), `full`, or `artifacts` |

**Modes:**
- **summary** — first/latest requests, files touched (top 20)
- **artifacts** — files and commands only
- **full** — all messages (truncated to 1000 chars each)

Requires LLM for synthesis (falls back to concatenation). Output stored in `~/.ab0t/.agents/blends/` and includes: active tasks, completed tasks, key files, decisions, blockers, and recommended next steps.

---

### Context & Knowledge

#### `agents learn`

4-stage LLM learning pipeline that extracts patterns, preferences, and insights from your session history.

```bash
agents learn                        # scan all projects
agents learn --project /path        # scan specific project
agents learn --show                 # show learned knowledge
agents learn --apply                # apply knowledge
```

| Option | Description |
|--------|-------------|
| `--show` | Display learned knowledge |
| `--apply` | Apply learned knowledge |
| `--project, -p` | Specific project (default: all) |

**Pipeline stages:**
1. **Digest** (Haiku) — understand each session
2. **Entities** (Haiku) — NER-style extraction of tools, patterns, preferences
3. **Reflect** (Sonnet) — meta-cognitive self-reflection
4. **Judge** (Sonnet) — merge, deduplicate, and validate findings

Knowledge is persisted in `~/.ab0t/.agents/knowledge/knowledge.json`. Tracks which sessions have been scanned to avoid re-processing.

---

#### `agents thread`

Persistent communication channels that span across sessions.

```bash
agents thread create auth-work
agents thread post auth-work "Finished the OAuth flow"
agents thread show auth-work
agents thread list
agents thread close auth-work
```

| Action | Description |
|--------|-------------|
| `create <name>` | Create a new thread |
| `list` | List all threads with message counts |
| `show <name>` | Display thread messages |
| `post <name> <message>` | Add a message |
| `close <name>` | Archive the thread |

Threads are JSONL files stored in `~/.ab0t/.agents/threads/`. Use them to leave notes between sessions, track decisions across days, or coordinate between agents.

---

#### `agents rag <query>`

Retrieval-augmented generation over your entire session history. BM25 keyword retrieval with optional LLM answer synthesis.

```bash
agents rag "how did I set up the database?"
agents rag --build              # rebuild index
agents rag --status             # show index stats
agents rag "auth flow" -n 10   # more results
```

| Option | Description |
|--------|-------------|
| `--build` | Rebuild the search index |
| `--status` | Show index statistics |
| `-n, --max N` | Max results (default: 5) |

Indexes user/assistant exchange pairs as chunks. Uses BM25 (k1=1.5, b=0.75) with stop-word filtering. If an LLM is available, synthesizes a direct answer from the top results.

Index stored in `~/.ab0t/.agents/rag/`.

---

#### `agents topics`

LLM-powered topic modeling and taxonomy detection across sessions.

```bash
agents topics                        # detect topics
agents topics list                   # show taxonomy
agents topics show "authentication"  # drill into a topic
agents topics --project /path
```

| Action | Description |
|--------|-------------|
| `(default)` | Detect topics across sessions |
| `list` | Show topic taxonomy |
| `show <name>` | Show sessions for a topic |
| `--project, -p` | Specific project |

Two-stage pipeline: per-session topic extraction (Haiku), then taxonomy consolidation (Sonnet). Detects technologies, domain areas, and categories. Stored in `~/.ab0t/.agents/topics.json`.

---

#### `agents bridge <session>`

Generate a handoff briefing to transfer context between agents.

```bash
agents bridge 1 --to codex              # Claude → Codex handoff
agents bridge abc123 --to claude        # Codex → Claude handoff
agents bridge 1 --format json -o handoff.json
```

| Option | Description |
|--------|-------------|
| `--to` | Target agent (`claude` or `codex`, default: opposite of source) |
| `--format, -f` | `md` (default) or `json` |
| `--output, -o` | Output file path |

LLM generates a structured handoff including: summary, current state, next steps, important context, files to review, and warnings. Stored in `~/.ab0t/.agents/bridges/`.

---

### Annotations

Tag, star, bookmark, and annotate sessions for organization.

```bash
# Tags
agents tag 1 auth,urgent           # add tags
agents untag 1 urgent              # remove a tag
agents tags                        # list all tags

# Stars
agents star 1                      # star a session
agents unstar 1
agents starred                     # list starred sessions

# Notes
agents note 1 "Fixed the race condition in auth flow"

# Bookmarks
agents bookmarks 1 "Important decision about schema"
agents bm                          # show all bookmarks
```

All annotations are stored in `~/.ab0t/.agents/annotations.json`. Tags are case-insensitive and support both comma and space separation.

---

### Configuration

#### `agents config`

Audit and compare agent configuration across Claude, Codex, and your project.

```bash
agents config                  # full audit
agents config check            # same as above
agents config hooks            # show configured hooks
agents config compare          # project vs global settings
agents config paths            # show config file locations
```

| Action | Description |
|--------|-------------|
| `check` | Audit all config (default) |
| `hooks` | Show hooks from all agents |
| `compare` | Project vs global diff |
| `paths` | List all config file locations |

Audits: `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.codex/config.json`, `~/.codex/instructions.md`, plus project-level equivalents. Flags risky permissions and commands.

---

### Workspaces

Group sessions from different projects and agents into named workspaces.

```bash
agents workspace create sprint-23
agents ws add sprint-23 abc123 --label "auth refactor"
agents ws add sprint-23 def456 --label "test coverage"
agents ws show sprint-23
agents ws list
agents ws remove sprint-23 abc123
agents ws delete sprint-23
```

| Action | Description |
|--------|-------------|
| `create <name>` | Create a workspace |
| `add <ws> <session>` | Add a session with optional label |
| `remove <ws> <session>` | Remove a session |
| `show <name>` | Show workspace contents |
| `list` | List all workspaces |
| `delete <name>` | Delete a workspace |

Workspaces are stored in `~/.ab0t/.agents/workspaces.json`. Each entry tracks session ID, agent, project, file path, timestamp, and custom label.

---

### Context Optimization

#### `agents compact <session>`

LLM-powered context compaction — summarize older messages while keeping recent ones intact.

```bash
agents compact 1                        # compact with defaults
agents compact 1 --keep-last 50         # keep last 50 messages full
agents compact 1 --strategy time        # segment by time gaps
agents uncompact 1                      # restore original
```

| Option | Description |
|--------|-------------|
| `--keep-last, -k N` | Keep last N messages uncompacted (default: 30) |
| `--strategy, -s` | `size` (default) or `time` |

Splits the session into older (compacted) and recent (kept full) messages. Older messages are segmented into ~15-25 message chunks and summarized by Haiku. Each segment summary includes: summary text, decisions made, artifacts mentioned, and commands run.

Original session is preserved — compaction creates an overlay file in `~/.ab0t/.agents/compacted/`. Use `agents uncompact` to restore.

---

### Monitoring

#### `agents watch`

Real-time monitoring of active agent sessions.

```bash
agents watch                          # continuous monitoring
agents watch --interval 10            # check every 10 seconds
agents watch --project /path          # filter to one project
agents watch --status                 # one-time snapshot
```

| Option | Description |
|--------|-------------|
| `--interval N` | Seconds between checks (default: 5) |
| `--project PATH` | Filter to a specific project |
| `--status` | One-time snapshot instead of continuous |

Monitors session files modified in the last 24 hours. Shows last record type (user/assistant/tool_result), byte deltas, and color-coded activity status:

| Status | Meaning | Color |
|--------|---------|-------|
| Active | < 5 minutes ago | Green |
| Idle | 5 min – 1 hour | Yellow |
| Quiet | > 1 hour | Gray |

Prints a summary every ~60 seconds. Ctrl+C to stop.

---

## LLM Requirements

Some commands require an LLM for full functionality. All degrade gracefully if no LLM is configured.

| Requires LLM | LLM Optional | No LLM Needed |
|--------------|-------------|----------------|
| blend | search | log |
| learn | rag | cost |
| topics | | diff |
| bridge | | export |
| compact | | backup |
| | | continue |
| | | fork |
| | | thread |
| | | annotate (all) |
| | | config |
| | | workspace |
| | | watch |

LLM-optional commands work without an LLM but produce better results with one (e.g., search uses semantic reranking, rag synthesizes answers).

---

## Data Storage

All experimental data is isolated to `~/.ab0t/.agents/`:

```
~/.ab0t/.agents/
├── annotations.json       # tags, notes, stars, bookmarks
├── backups/               # backup archives
├── blends/                # blend output documents
├── bridges/               # agent handoff briefings
├── compacted/             # compaction overlays
├── forks/                 # forked sessions
│   └── index.json
├── knowledge/             # learn pipeline output
│   └── knowledge.json
├── rag/                   # search index
│   ├── index.json
│   └── docs.json
├── threads/               # persistent threads
│   └── .archive/
├── topics.json            # topic taxonomy
├── workspaces.json        # workspace definitions
└── pricing.json           # custom model pricing (optional)
```

No experimental command writes to `~/.claude/`, `~/.codex/`, or any agent's native directories.
