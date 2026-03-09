# Power Features

> *"I know I solved this problem before. I just can't find the session."*

Every developer using AI agents hits the same walls. You accumulate hundreds of sessions across weeks of work. Context gets trapped inside conversations that are hard to find, impossible to search, and locked to whichever agent you happened to use. When you switch between Claude and Codex, knowledge doesn't follow. When a teammate asks "how did you set up auth?", the answer is buried in a session you can't locate.

`agents experimental on` unlocks 20+ commands that turn your session history from a pile of JSONL files into a searchable, organizable, cross-agent knowledge base.

```bash
agents experimental on
```

---

## "I know I fixed this before, but I can't find it"

This is the single most common frustration. You spent an hour debugging a database connection issue three weeks ago. The fix is in a session somewhere — but which project? Which agent? You end up re-solving the problem from scratch.

### Search every conversation you've ever had

```bash
agents search "database connection pool"
agents search "fix.*timeout" -n 20
```

Full-text regex search across every Claude, Codex, and Gemini session on your machine. Results show the agent, project, session age, and highlighted matching snippets with surrounding context.

With an LLM configured, results are semantically reranked — "auth bug" surfaces conversations about "authentication error" and "login failure" too. Without an LLM, you still get fast keyword matching.

### Ask questions about your own history

```bash
agents rag "how did I set up the database connection pool?"
agents rag "what was the decision on JWT vs session tokens?"
```

Retrieval-augmented generation over your entire session history. It indexes every user/assistant exchange, retrieves the most relevant fragments with BM25, and (with an LLM) synthesizes a direct answer.

It's like having documentation for every decision you've made — except you never had to write it.

```bash
agents rag --build     # rebuild the index after new sessions
agents rag --status    # see how many chunks are indexed
```

---

## "I have no idea what my agents are actually costing me"

You're running Opus for complex architecture work, Sonnet for quick fixes, Codex for prototyping. The bills come in monthly, but you can't connect the cost to the work. Which project burned through the most tokens? Is your cache hit rate good? Could you save money by switching models for certain tasks?

```bash
agents cost
agents cost --today
agents cost --week
```

Breakdowns by model, by project, by time period. Cache savings analysis shows you exactly how much caching is reducing your spend. Bring your own rates with `~/.ab0t/.agents/pricing.json` when pricing changes.

```
Token Cost Estimate
────────────────────────────────────────
  Total: $142.38

  By Model:
  opus-4-6         ████████████████░░░░ $104.20 (73%)
  gpt-5.3-codex    ████░░░░░░░░░░░░░░░░  $28.47 (20%)
  sonnet-4-6       █░░░░░░░░░░░░░░░░░░░   $7.11 (5%)

  Cache savings: $891.20 (86% of requests served from cache)
```

---

## "I started this in Claude but now I need Codex"

You're 40 messages deep in a Claude session. The architecture is decided, the interfaces are defined, and now you need Codex's strength for a specific implementation phase. Normally, you'd spend 10 minutes re-explaining everything. The new agent starts cold with zero context.

### Hand off context between agents in one command

```bash
agents bridge 1 --to codex        # Claude → Codex handoff
agents bridge abc123 --to claude   # Codex → Claude handoff
```

Generates a structured handoff briefing: summary of what's been done, current state, next steps, files to review, important decisions, and warnings. Give it to the target agent as a first message and it's up to speed immediately.

### Blend multiple sessions into one briefing

You worked on auth across three sessions over two days. Monday's session set up the database schema. Tuesday morning's session wrote the API routes. Tuesday afternoon's session fixed the tests. Now you need to resume and you can't remember the full picture.

```bash
agents blend 1 2 3
```

The LLM reads all three sessions and produces one coherent document: what's done, what's in progress, what's blocked, key decisions, and recommended next steps. Feed it into your next session as context, or read it yourself to get oriented.

```bash
agents blend 1 2 --mode artifacts   # just files and commands
agents blend 1 2 --mode full        # everything, truncated
```

---

## "Which sessions actually matter? I have 117 of them"

After a month of active development, you have more sessions than you can track. Most are throwaway — quick questions, one-off fixes. But some contain important architectural decisions, hard-won debugging insights, or context you'll need again. Right now they all look the same.

### Star what matters

```bash
agents star 1
agents starred                    # see all starred sessions
```

### Tag for fast retrieval

```bash
agents tag 1 auth,critical
agents tag 3 refactor,backend
agents tags                       # see all tags in use
```

Tags are case-insensitive, comma or space-separated. Use them however makes sense — by feature, priority, sprint, or team.

### Annotate with context

```bash
agents note 1 "This session has the final auth schema decision"
agents note 1 "Revisit this — the token rotation approach may not scale"
```

Timestamped notes attached to sessions. When you come back in a month, you'll know not just what you discussed, but why it mattered.

### Bookmark key moments

```bash
agents bookmarks 1 "The migration strategy discussion starts here"
agents bm                          # see all bookmarks
```

### Group sessions into workspaces

A sprint touches five projects, three agents, and twenty sessions. A workspace collects them into one named view.

```bash
agents workspace create sprint-23
agents ws add sprint-23 abc123 --label "auth refactor"
agents ws add sprint-23 def456 --label "API contract"
agents ws add sprint-23 ghi789 --label "load testing"
agents ws show sprint-23
```

Workspaces span projects, agents, and weeks. Use them for sprints, incidents, epics, onboarding — any unit of work that doesn't fit inside a single project directory.

---

## "I keep making the same mistakes across sessions"

Every session starts from zero. Your agent doesn't know that you prefer snake_case, that you always use pytest over unittest, that the last three times you tried approach X it failed. Patterns exist across your sessions, but they're invisible.

### Let agents learn from your history

```bash
agents learn                     # scan sessions and extract patterns
agents learn --show              # see what's been learned
```

A 4-stage LLM pipeline:

1. **Digest** — read each session and understand it
2. **Extract** — pull out tools, patterns, preferences, and recurring decisions
3. **Reflect** — meta-cognitive self-reflection: what do these patterns mean?
4. **Judge** — merge, deduplicate, and validate across all findings

The output: your coding preferences, your tool choices, your recurring patterns, and your performance insights — all extracted automatically from how you actually work.

Knowledge persists in `~/.ab0t/.agents/knowledge/` and gets richer with every session you scan.

### Discover topics you didn't know you had

```bash
agents topics                    # detect topics across all sessions
agents topics list               # see the taxonomy
agents topics show "auth"        # every session about authentication
```

LLM-powered topic modeling finds themes across your work. You might discover you've touched authentication in 14 sessions across 6 projects. Or that "database" work clusters into migration sessions and optimization sessions with very different patterns.

---

## "What did my agent actually change in that session?"

You ran a long session yesterday. Files were created, edited, commands were executed, commits were made. But the conversation is 200 messages long and you just need to know: what changed?

```bash
agents diff 1
```

Extracts every file write, every file edit, every command run, and every git commit from the session. The answer to "what happened?" in 5 seconds instead of 20 minutes of scrolling.

---

## "I need to share what happened in this session"

A teammate needs to understand the architectural decisions from your session. Or you need a post-mortem of what went wrong. Or you just want a clean record outside the JSONL format.

```bash
agents export 1                          # clean markdown
agents export 1 --format json -o -       # structured JSON to stdout
agents export 1 --format txt -o notes/   # plain text to a file
```

Timestamps, model names, tool usage — all preserved in a readable format you can share, archive, or feed into other tools.

---

## "What if I lose my session data?"

Your sessions are your working memory. Losing them means losing context, decisions, and history that took days or weeks to build.

```bash
agents backup                     # full backup of everything
agents backup --incremental       # just what changed since last time
agents backup --list              # see existing backups
agents backup --restore <file>    # restore with conflict resolution
```

Backs up Claude sessions, Codex sessions, configs, command history, and all agents metadata into a timestamped tar.gz. Incremental mode is fast — it only captures files modified since the last backup.

Restore handles conflicts intelligently:
- **keep-newer** — keep whichever version is more recent
- **keep-backup** — overwrite with the backup version
- **keep-both** — rename the existing file and keep both

---

## "I want to pick up where I left off without thinking about it"

You `cd` into a project. You want to resume working. But which session? You have 8 of them. The most recent one might have been a quick question — the real work session was from yesterday on a specific branch.

```bash
agents continue
```

Scores every candidate on directory match, git branch, recency, and session depth. Picks the best one and drops you in. Use `--dry-run` to see the scoring:

```bash
agents cont --dry-run
# Best match: session abc123 (score: 190)
#   directory: exact match (+100)
#   branch: main matches (+40)
#   age: 2 hours (+50)
#   Alternatives: def456 (140), ghi789 (90)
```

---

## "I want to try a different approach without losing my progress"

You're deep into a session and it's going sideways. You want to back up to message 25 and try a different direction — but you don't want to lose the current thread in case you need it.

```bash
agents fork 1 --at 25     # fork at message 25
agents fork 1              # fork the whole session
```

Creates a snapshot. The original stays exactly as it is. You get a new copy to take in a different direction. Forks are tracked with an index so you can find them later.

---

## "I need a channel that persists across sessions"

Sessions end. But sometimes you need a running thread that outlasts any individual conversation — a place to track decisions, leave notes for tomorrow, or coordinate across multiple sessions working on the same problem.

```bash
agents thread create auth-project
agents thread post auth-project "Decided: JWT with refresh tokens, 15m expiry"
agents thread post auth-project "TODO: rate limiting on token refresh endpoint"
agents thread show auth-project
agents thread list
agents thread close auth-project    # archive when done
```

Threads are persistent JSONL files. They survive session restarts, project switches, and agent changes. Use them as a decision log, a running TODO, or a coordination channel between sessions.

---

## "This session is enormous and my agent is getting slow"

Sessions that run for hours accumulate massive context. Response quality degrades. Costs increase. But you don't want to start fresh because you'd lose all the context.

```bash
agents compact 1                       # compact older messages
agents compact 1 --keep-last 50       # keep recent 50 messages full
agents compact 1 --strategy time       # segment by time gaps
```

Older messages get summarized into concise segments by Haiku — preserving decisions, artifacts, and commands while dramatically reducing token count. Recent messages stay untouched.

The original session is never modified. Compaction creates an overlay. Restore anytime:

```bash
agents uncompact 1
```

---

## "What are my agents doing right now?"

You have multiple terminal windows open. Claude is working in one project, Codex in another. You want a single view of what's happening across all of them.

```bash
agents watch                         # continuous live monitoring
agents watch --status                # one-time snapshot
agents watch --project /path         # filter to one project
```

Real-time view of active sessions with color-coded status:

- **Green** — active in the last 5 minutes (agent is responding or user is typing)
- **Yellow** — idle (5 minutes to 1 hour)
- **Gray** — quiet (over 1 hour)

Shows the last record type (user message, assistant response, tool execution), byte deltas, and project names. Summary prints every 60 seconds.

---

## "How do I know my agent configs aren't conflicting?"

You've got global Claude settings, project-level CLAUDE.md files, Codex configs, hooks — and sometimes they interact in ways you don't expect.

```bash
agents config                   # full audit across all agents
agents config hooks             # see every configured hook
agents config compare           # project vs global settings
agents config paths             # where all config files live
```

Flags risky permissions, shows hook configurations, and surfaces conflicts between project-level and global settings. The first thing to run when something isn't working the way you expect.

---

## "I need a timeline of what I actually did"

Not just "which sessions exist" — but a chronological view of your AI-assisted work. What did you work on Monday? How much active time did you spend this week? What was the shape of your week?

```bash
agents log                   # this week
agents log --today
agents log --month -n 100
```

Grouped by day with session previews and active duration (gaps over 1 hour are excluded — this is real working time, not calendar time).

---

## What Needs an LLM

Most commands work without any LLM. Some are enhanced by one. A few require one.

| Works without LLM | Enhanced by LLM | Requires LLM |
|--------------------|-----------------|---------------|
| search, log, cost, diff | search (semantic reranking) | blend (session synthesis) |
| export, backup, fork | rag (answer synthesis) | learn (4-stage pipeline) |
| continue, thread | | topics (taxonomy detection) |
| all annotations | | bridge (handoff generation) |
| config, workspace | | compact (summarization) |
| watch | | |

Everything degrades gracefully. If a command needs an LLM and can't find one, it tells you what to configure and (where possible) falls back to a non-LLM approach.

---

## Safe By Design

Every experimental command stores data in `~/.ab0t/.agents/` — completely isolated from your agents' native directories. Nothing touches `~/.claude/`, `~/.codex/`, or your session files.

```
~/.ab0t/.agents/
├── annotations.json         # tags, notes, stars, bookmarks
├── backups/                 # backup archives
├── blends/                  # session synthesis documents
├── bridges/                 # agent handoff briefings
├── compacted/               # compaction overlays (originals untouched)
├── forks/                   # forked session snapshots
├── knowledge/               # learned patterns and preferences
├── rag/                     # search index
├── threads/                 # persistent cross-session channels
├── topics.json              # topic taxonomy
├── workspaces.json          # workspace definitions
└── pricing.json             # custom model pricing (optional)
```

Delete any file and the corresponding feature resets cleanly. Delete the whole directory and you're back to fresh — with zero impact on your actual agent sessions. Compaction creates overlays, not modifications. Backups are additive. Nothing is destructive.
