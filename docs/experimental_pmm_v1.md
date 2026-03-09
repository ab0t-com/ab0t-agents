# Power Features

You're already using `agents` to see where your AI sessions live. These commands take it further — find that conversation from last week, see what your agents actually cost you, hand off context between Claude and Codex, and build organizational memory across hundreds of sessions.

Enable them with:

```bash
agents experimental on
```

---

## Find Anything You've Ever Worked On

You had a conversation about database migrations three days ago. Which project? Which agent? You don't remember. You shouldn't have to.

### Search across everything

```bash
agents search "database migration"
agents search "fix.*payment" -n 20
```

Searches every session across Claude, Codex, and Gemini. With an LLM configured, results are semantically reranked — so "auth bug" finds conversations about "authentication error" too.

### See what happened when

```bash
agents log                # this week
agents log --today        # just today
agents log --month        # this month
```

A chronological view of your AI-assisted work. Grouped by day, with previews of what each session was about and how long you were actively working.

### Know what a session actually did

```bash
agents diff 1
```

Shows every file that was created or modified, every command that was run, and every git commit made during a session. The answer to "what did my agent change?" without reading the whole conversation.

---

## Understand What Your Agents Cost

You're running Opus, Sonnet, Codex — sometimes all in the same week. How much is it actually costing?

```bash
agents cost
agents cost --this-week
agents cost --today
```

Breakdowns by model, by project, by time period. See your cache hit rate and how much caching is saving you. Bring your own pricing with `~/.ab0t/.agents/pricing.json` if the built-in rates are out of date.

---

## Pick Up Exactly Where You Left Off

### Smart resume

You `cd` into a project directory. You want the right session — not just the most recent one, but the one that matches this directory, this git branch, this context.

```bash
agents continue           # auto-picks the best session
agents cont --dry-run     # see the scoring without launching
```

Scores every candidate session on directory match, recency, git branch, and session depth. Shows you why it picked what it picked.

### Fork a conversation

You're 50 messages deep and want to try a different approach without losing your current thread.

```bash
agents fork 1              # copy the whole session
agents fork 1 --at 25      # fork at message 25
```

Creates a snapshot you can take in a different direction. The original stays untouched.

### Blend sessions together

You worked on auth in three separate sessions across two days. Now you need one coherent picture.

```bash
agents blend 1 2 3
agents blend 1 2 --mode full
```

The LLM reads all sessions and produces a single briefing: active tasks, completed work, key files, decisions made, blockers, and recommended next steps. Stored as a markdown doc you can feed into your next session.

---

## Move Context Between Agents

You started a task in Claude but need to switch to Codex (or vice versa). Normally you'd re-explain everything. Bridge does it for you.

```bash
agents bridge 1 --to codex       # Claude → Codex handoff
agents bridge abc123 --to claude  # Codex → Claude handoff
```

Generates a structured handoff briefing — summary, current state, next steps, files to review, warnings. Give it to the target agent and you're up to speed in one message.

---

## Organize Your Sessions

Sessions pile up fast. After a few weeks you have hundreds. Tags, stars, and workspaces let you impose structure without changing how you work.

### Tag and star

```bash
agents tag 1 auth,urgent
agents star 1
agents starred               # see all starred sessions
agents tags                  # see all tags in use
```

### Add notes

```bash
agents note 1 "This session has the final auth schema decision"
```

Timestamped notes attached to any session. When you come back in a month, you'll know why it mattered.

### Bookmarks

```bash
agents bookmarks 1 "The migration strategy discussion"
agents bm                    # see all bookmarks
```

### Workspaces

Group sessions from different projects and agents into a single named collection.

```bash
agents workspace create sprint-23
agents ws add sprint-23 abc123 --label "auth refactor"
agents ws add sprint-23 def456 --label "API tests"
agents ws show sprint-23
```

A workspace can span multiple projects, multiple agents, and multiple weeks. Use them for sprints, epics, incidents, or however you organize work.

---

## Build Organizational Memory

Your agent sessions contain patterns — how you like your code structured, which tools you reach for, what mistakes keep coming up. Most of that knowledge disappears when the session ends.

### Learn from your history

```bash
agents learn                    # scan sessions and extract patterns
agents learn --show             # see what's been learned
agents learn --project /path    # focus on one project
```

A 4-stage LLM pipeline: digest each session, extract entities and patterns, reflect on what they mean, then judge and deduplicate. Outputs preferences, tools, recurring patterns, and performance insights.

Knowledge persists in `~/.ab0t/.agents/knowledge/` and gets smarter as you use more sessions.

### Ask questions about past work

```bash
agents rag "how did I set up the database connection pool?"
agents rag --build     # rebuild the index
```

Retrieval-augmented generation over your entire session history. BM25 retrieval finds relevant conversation fragments, then an LLM synthesizes a direct answer. Like searching your own documentation, except it's documentation you never had to write.

### Discover topics automatically

```bash
agents topics              # detect topics across all sessions
agents topics list         # see the taxonomy
agents topics show "auth"  # sessions about authentication
```

LLM-powered topic modeling that detects technologies, domain areas, and categories across your session history. Useful when you need to find "everything related to authentication" without knowing exact search terms.

### Persistent threads

```bash
agents thread create auth-project
agents thread post auth-project "Decided on JWT with refresh tokens"
agents thread show auth-project
```

Cross-session communication channels. Leave notes for yourself (or your future agents) that persist across sessions. Track decisions, open questions, and status across days or weeks.

---

## Export and Protect Your Work

### Export conversations

```bash
agents export 1                      # markdown
agents export 1 --format json -o -   # JSON to stdout
agents export 1 --format txt         # plain text
```

Clean exports with timestamps, model names, and tool usage context. Use them for documentation, post-mortems, or feeding context into other tools.

### Backup everything

```bash
agents backup                  # full backup
agents backup --incremental    # only changes since last backup
agents backup --list           # see existing backups
agents backup --restore <file> # restore
```

Backs up Claude sessions, Codex sessions, configs, history, and all agents metadata. Incremental mode only captures what changed. Restore with conflict resolution (keep newer, keep backup, or keep both).

---

## Audit Your Agent Configuration

```bash
agents config               # full audit
agents config hooks          # see what hooks are configured
agents config compare        # project vs global settings
agents config paths          # where all config files live
```

See your Claude and Codex configuration side by side. Flags risky permissions, shows hooks, and compares project-level overrides against global settings. Useful when something isn't working and you need to see the full picture.

---

## Optimize Large Sessions

Sessions that run for hours accumulate massive context. Compaction summarizes older messages while keeping recent ones intact.

```bash
agents compact 1                    # compact with defaults
agents compact 1 --keep-last 50    # keep last 50 messages full
agents uncompact 1                  # restore original
```

Older messages are segmented and summarized by Haiku. Each summary preserves decisions, artifacts, and commands. The original is never modified — compaction creates an overlay that can be removed at any time.

---

## Monitor Active Sessions

```bash
agents watch                    # continuous live monitoring
agents watch --status           # one-time snapshot
agents watch --project /path    # filter to one project
```

Real-time view of which agent sessions are active right now. Shows the last record type (user typing, agent responding, tool running), byte changes, and color-coded activity status:

- **Green** — active in the last 5 minutes
- **Yellow** — idle (5 min to 1 hour)
- **Gray** — quiet (over 1 hour)

---

## What Needs an LLM

Most commands work without any LLM configured. A few need one for their core function, and a few are better with one.

| Works great without LLM | Better with LLM | Needs LLM |
|--------------------------|-----------------|-----------|
| log, cost, diff | search (semantic reranking) | blend (session synthesis) |
| export, backup | rag (answer synthesis) | learn (4-stage pipeline) |
| continue, fork | | topics (taxonomy detection) |
| thread, all annotations | | bridge (handoff generation) |
| config, workspace, watch | | compact (summarization) |

Commands that need an LLM will tell you if one isn't available and suggest how to configure it.

---

## Your Data Stays Yours

Every experimental command stores its data in `~/.ab0t/.agents/` — a namespace isolated from your agents' own directories. Nothing writes to `~/.claude/`, `~/.codex/`, or any agent's native session files.

```
~/.ab0t/.agents/
├── annotations.json        # tags, notes, stars, bookmarks
├── backups/                # backup archives
├── blends/                 # session synthesis documents
├── bridges/                # agent handoff briefings
├── compacted/              # compaction overlays (originals preserved)
├── forks/                  # forked session snapshots
├── knowledge/              # learned patterns and preferences
├── rag/                    # search index
├── threads/                # persistent cross-session channels
├── topics.json             # topic taxonomy
├── workspaces.json         # workspace definitions
└── pricing.json            # custom model pricing (optional)
```

Delete any of these and the corresponding feature resets cleanly. Delete the whole directory and you're back to a fresh install with no data loss in your actual agent sessions.
