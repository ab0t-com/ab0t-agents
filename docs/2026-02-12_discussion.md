# agents CLI - Feature Discussion & Roadmap

**Date:** 2026-02-12
**Context:** We have a working multi-agent session browser (Claude Code, Codex) with stats, stable IDs, and an adapter system. Every conversation is stored as JSONL with full message history, token usage, timestamps, file snapshots, tool calls, and model metadata. This is a rich dataset sitting on disk. What can we build on top of it?

---

## 1. Session Search (`agents search <query>`)

**What:** Full-text search across all session files from all agents. Find any conversation by what was discussed, which files were touched, what errors occurred, or what decisions were made.

**Why:** You know you solved a similar problem three weeks ago but can't remember which project or session. Right now you'd have to manually browse sessions one by one. Search makes the entire history instantly accessible.

**Implementation:**
- Walk all session files via adapters (reuse `iter_all_sessions()`)
- For each file, scan JSONL lines for user/assistant text content
- Match against query (substring, regex, or fuzzy)
- Return ranked results: session ID, project, agent, timestamp, matching line with context
- Cache an inverted index in `~/.ab0t/.agents/search_index.json` keyed by session mtime for incremental rebuilds

**Output example:**
```
$ agents search "auth middleware"

[claude] /home/user/webapp  (3d ago)
  session a1b2c3d4: "...the auth middleware needs to check the JWT expiry..."

[codex] /home/user/api  (1w ago)
  session 019c4a11: "...refactored auth middleware to use the new token format..."

2 matches across 2 projects (searched 101 sessions in 0.3s)
```

**Levels of sophistication:**
1. Basic: grep through JSONL text fields
2. Medium: build a per-session keyword index, search the index
3. Advanced: embed session summaries with a local model, do semantic search

---

## 2. Session Diff (`agents diff <session>`)

**What:** Show what files were created, modified, or deleted during a session. Reconstruct the tangible output of a conversation.

**Why:** Sessions are conversations, but the real value is what changed on disk. "What did that 3-hour session actually produce?" This bridges the gap between conversation history and code history.

**Implementation:**
- Claude sessions have `file-history-snapshot` records with file contents at various points
- Parse tool_use blocks for file writes, edits, bash commands that modify files
- Codex sessions have `event_msg` records with tool execution details
- Diff the snapshots to show what changed
- Cross-reference with git: if the session's timestamps overlap with commits, show which commits came from which session

**Output example:**
```
$ agents diff a1b2c3d4

Session a1b2c3d4 [claude] 2026-02-10 14:30 (2h 15m)
  /home/user/webapp

  Modified:
    src/auth/middleware.ts    +47 -12
    src/auth/jwt.ts          +23 -5
    tests/auth.test.ts       +89 (new file)

  Commands run:
    npm test                 (exit 0)
    npm run build            (exit 0)

  Git commits during session:
    f4a2b1c  "Add JWT expiry checking to auth middleware"
    e3d5a7f  "Add auth middleware tests"
```

---

## 3. Cost Estimation (`agents cost`)

**What:** Calculate estimated API costs from token usage data, broken down by model, project, time period.

**Why:** Token counts are abstract. Dollars are concrete. "This project cost me $47 this week" is immediately actionable. Helps optimize usage patterns - maybe that project with 95% cache hit rate is efficient, but the one with 20% is burning money on uncached context.

**Implementation:**
- We already have per-session token breakdowns: input, output, cache_read, cache_create
- We have model names per API call
- Maintain a pricing table (can be a simple JSON file, user-updatable)
- Calculate: `cost = (input * input_price) + (output * output_price) + (cache_read * cache_price)`
- Aggregate by: session, project, day/week/month, model

**Output example:**
```
$ agents cost

Estimated API Cost (since 2026-01-21)
────────────────────────────────────────────────────

  Total:     $142.30
  Today:     $8.50       This week: $47.20      This month: $142.30

  By model:
    opus-4-5             $98.40  (69%)
    opus-4-6             $38.20  (27%)
    gpt-5.3-codex        $5.70   (4%)

  Top projects:
    /home/user/webapp     $34.50  (28 sessions)
    /home/user/api        $28.10  (14 sessions)

  Cache savings:  ~$890 saved by 95% cache hit rate
```

**Notes:**
- Codex doesn't expose token usage in session files, so cost would be Claude-only unless Codex adds this
- Pricing changes frequently - keep the price table as a separate config file
- Could add a `--budget` flag: "warn me when I've spent $X today"

---

## 4. Activity Log (`agents log`)

**What:** Chronological feed of all coding agent activity across projects. Like `git log --all` but for agent sessions.

**Why:** "What did I work on this week?" Currently requires mentally reconstructing from memory. A log gives you a timeline of your AI-assisted work.

**Implementation:**
- Collect all sessions with timestamps from all adapters
- Extract: start time, end time (from first/last record timestamps), project, agent, first message, files touched
- Sort chronologically
- Support date filtering: `agents log --today`, `agents log --week`, `agents log --since 2026-02-01`

**Output example:**
```
$ agents log --today

2026-02-12 Activity Log
────────────────────────────────────────────────────

  23:30  [claude] /home/ubuntu/tmp
         "check the install.sh and audit your work..."
         2.3M session, 45m active

  23:05  [codex]  /home/ubuntu/infra/.../tickets
         "Use tree depth 5 to look around..."
         15.2M session, 1h 20m active

  20:20  [claude] /home/ubuntu/infra/.../tickets
         "find the module file with a zanbar file..."
         2K session, 3m active

3 sessions today, ~2h 8m active time
```

---

## 5. Session Export (`agents export <session> --format md`)

**What:** Export a session as clean, readable markdown. Strip JSONL structure, format as a conversation with code blocks, tool outputs, and file changes.

**Why:** Sharing context with teammates, creating documentation from exploratory sessions, archiving important conversations in a human-readable format, or feeding session context into another tool.

**Formats:**
- `md` - clean markdown conversation
- `txt` - plain text
- `json` - structured JSON (normalized across agents)
- `html` - rendered HTML with syntax highlighting

**Implementation:**
- Parse session JSONL, extract user/assistant messages
- Format code blocks, tool calls, file edits
- Strip internal metadata (UUIDs, system records, etc.)
- For assistant messages: extract text content, skip internal tool_use XML
- Add headers with session metadata (project, date, agent, duration)

---

## 6. Smart Continue (`agents continue`)

**What:** Intelligently resume the most relevant session based on current context. No manual browsing needed.

**Why:** The common workflow is: you're in a project directory, you want to pick up where you left off. Currently: `agents show . → agents resume 1`. This collapses it to one command with smart heuristics.

**Heuristics (in priority order):**
1. Current directory + current git branch → find session that matches both
2. Current directory → most recent session
3. Current directory → session with most overlap in recently modified files
4. If no sessions for current dir, suggest nearest parent directory that has sessions

**Implementation:**
- Read cwd, git branch, recently modified files
- Query adapters for sessions matching cwd
- Score sessions by: recency, branch match, file overlap
- Present top match with confirmation, or auto-launch if confidence is high

```
$ agents continue

Found: [claude] session a1b2c3d4 (45m ago, branch: feature/auth)
  "refactoring the auth middleware..."

Resume? [Y/n]
```

---

## 7. Context Compaction (Reversible Summarization)

**What:** Intelligently compress long session threads by summarizing older portions while keeping the full original data intact. The compacted version becomes the active context, but the original is always recoverable.

**Why:** Long sessions degrade in quality as context windows fill up. The agent starts forgetting early decisions, repeating work, or losing track of constraints. Compaction preserves the important information while freeing context space. But unlike destructive summarization, this is reversible - you can "uncompact" to recover full detail on any section.

**Architecture:**
```
Original session (immutable):
  ~/.claude/projects/xxx/session.jsonl     <- never modified

Compacted overlay:
  ~/.ab0t/.agents/compacted/session.jsonl  <- summarized version

Compaction manifest:
  ~/.ab0t/.agents/compacted/session.manifest.json
  {
    "original": "/path/to/session.jsonl",
    "original_hash": "sha256:...",
    "compacted_at": "2026-02-12T...",
    "sections": [
      {
        "original_lines": [0, 450],
        "summary": "User asked to refactor auth module. Key decisions: ...",
        "topic": "auth-refactor",
        "preserved_artifacts": ["file edits to middleware.ts", "test results"],
        "reversible": true
      },
      {
        "original_lines": [451, null],
        "status": "uncompacted"
      }
    ]
  }
```

**How it works:**
1. **Topic segmentation** - Use topic modeling (LDA, or simpler: detect topic shifts by message clustering) to identify coherent segments of conversation
2. **Per-segment summarization** - For each segment, generate a summary that preserves:
   - Key decisions made
   - Artifacts produced (files created/modified, commands run)
   - Constraints and requirements stated
   - Errors encountered and how they were resolved
3. **Overlay creation** - Write a new JSONL that replaces older segments with their summaries while keeping recent segments intact
4. **Resume with compacted context** - When resuming, use the compacted version as context. The agent gets summaries of old work + full detail of recent work
5. **Uncompact on demand** - If the agent or user needs detail from a summarized section, transparently expand it back from the original

**Compaction strategies:**
- **Time-based:** Compact everything older than N hours
- **Size-based:** Keep total context under N tokens, compact oldest first
- **Topic-based:** Compact completed topics, keep active topic in full
- **Hybrid:** Compact by topic, but preserve the last N messages in full regardless

**Reversibility guarantee:**
- Original files are NEVER modified
- Compacted versions are separate overlay files
- Manifest tracks exactly which lines map to which summaries
- `agents uncompact <session>` restores full context
- `agents uncompact <session> --section 3` expands just one section

**Integration with resume:**
```
$ agents resume 1 --compact
# Resumes with compacted context (older parts summarized)

$ agents resume 1 --compact --keep-last 50
# Keep last 50 messages in full, compact the rest

$ agents resume 1
# Normal resume with full context (default, no change)
```

---

## 8. Session Forking

**What:** Create a new session that starts with the context of an existing session at a specific point. Like `git branch` but for conversations.

**Why:** You're deep into a session and realize you want to try a different approach. Or you want to hand off a session's context to a different agent. Or you want to resume from a point before things went wrong, without losing the original path.

**Implementation:**
- Copy session JSONL up to a specified message (by number or timestamp)
- Create a new session file with the truncated content
- Add a metadata record linking back to the parent session and fork point
- Register with the appropriate agent for resume

**Usage:**
```
$ agents fork a1b2c3d4 --at 25
# Fork session at message 25, creating new session

Forked: a1b2c3d4 -> new session e5f6g7h8
  Copied 25 of 142 messages
  Ready to resume: agents resume e5f6g7h8

$ agents fork a1b2c3d4 --at 25 --to codex
# Fork a claude session into a codex session
# Translates context format between agents
```

**Fork tree visualization:**
```
$ agents forks a1b2c3d4

a1b2c3d4 (main, 142 messages)
  ├── e5f6g7h8 (forked at msg 25, 67 messages)  "tried approach B"
  └── f8g9h0i1 (forked at msg 80, 12 messages)  "quick test"
```

---

## 9. Session Blending

**What:** Merge context from multiple sessions into a new session. Combine knowledge from different conversations into a single coherent context.

**Why:** You discussed the database schema in session A, the API design in session B, and now need to implement the integration layer with knowledge of both. Currently you'd have to re-explain everything. Blending carries forward the relevant context from both.

**Implementation:**
- Extract key artifacts from each source session:
  - Decisions made
  - Files created/modified (final state)
  - Constraints and requirements
  - Technical context (architecture, patterns used)
- Generate a "blended context" document that synthesizes these
- Create a new session with this blended context as the opening system/developer message
- Track provenance: which facts came from which session

**Usage:**
```
$ agents blend a1b2c3d4 x9y8z7w6 --output new-session
# Blend two sessions into a new one

Blending:
  [claude] a1b2c3d4: "database schema design" (45 messages)
  [claude] x9y8z7w6: "API endpoint design" (32 messages)

Extracted:
  - 3 key decisions
  - 5 file artifacts
  - 2 architectural constraints

Created blended session: m4n5o6p7
Resume: agents resume m4n5o6p7
```

**Blend modes:**
- **Full merge:** Include all context from all sessions
- **Summary merge:** Include summaries of each session
- **Artifact merge:** Only carry forward files and decisions, not conversation
- **Selective:** User picks which parts of each session to include

---

## 10. Self-Learning (`agents learn`)

**What:** Read session history and extract durable knowledge - patterns, preferences, workflows, mistakes, and solutions. Build a persistent knowledge base that improves future sessions.

**Why:** Every session contains implicit knowledge: the user's coding style, preferred libraries, common mistakes, project-specific conventions, debugging strategies. This knowledge is trapped in individual sessions. `agents learn` extracts it into a reusable form that can be injected into future sessions.

### 10a. Knowledge Extraction

Scan sessions and extract structured artifacts:

**Preferences:**
- "User always uses pytest, never unittest"
- "User prefers functional style over class-based"
- "User wants type annotations on all public functions"
- "User uses pnpm, not npm or yarn"

**Patterns:**
- "In this project, API routes follow the pattern: /api/v1/{resource}/{id}"
- "Error handling always uses custom AppError class"
- "Tests are co-located with source files as *.test.ts"

**Workflows:**
- "User typically: writes code -> runs tests -> fixes failures -> commits"
- "User always asks for tree view before making changes"
- "User prefers small incremental commits over large ones"

**Solutions (problem -> resolution pairs):**
- "When pytest fails with import error -> check sys.path and __init__.py"
- "When docker build fails on M1 -> add --platform linux/amd64"
- "When git push fails -> check if branch protection requires PR"

**Anti-patterns (things that went wrong):**
- "Inline Python in bash caused edit failures -> always use separate .py files"
- "Using truncated session IDs broke resume -> always use full UUID"
- "Wall-clock session time was misleading -> exclude gaps > 1 hour"

### 10b. Knowledge Storage

```
~/.ab0t/.agents/knowledge/
  ├── global.md              # Cross-project preferences and patterns
  ├── projects/
  │   ├── home-user-webapp.md    # Project-specific knowledge
  │   └── home-user-api.md
  ├── solutions.jsonl         # Problem-solution pairs (searchable)
  ├── workflows.jsonl         # Extracted workflow patterns
  └── manifest.json           # What was learned from which sessions
```

### 10c. Knowledge Application

When starting or resuming a session, the agents CLI could:
1. Look up project-specific knowledge for the current directory
2. Look up global preferences
3. Inject relevant knowledge as a context preamble or CLAUDE.md-like file
4. Surface relevant solutions when similar problems are detected

```
$ agents learn
# Scans all sessions, extracts knowledge

Scanned 101 sessions across 29 projects.

Extracted:
  12 preferences
   8 project patterns
   5 workflow patterns
  23 problem-solution pairs
   4 anti-patterns

Saved to ~/.ab0t/.agents/knowledge/

$ agents learn --project .
# Extract knowledge for current project only

$ agents learn --show
# Display all extracted knowledge

$ agents learn --apply
# Generate CLAUDE.md from learned preferences for current project
```

### 10d. Continuous Learning

Instead of a one-time scan, hook into session completion:
- After each session ends, extract new knowledge
- Diff against existing knowledge base
- Add new insights, update confidence scores
- Flag contradictions (user changed preference)

### 10e. Knowledge Confidence

Not all extracted knowledge is equally reliable:
- Seen once: low confidence (might be situational)
- Seen 3+ times: medium confidence (likely a pattern)
- Seen across projects: high confidence (strong preference)
- Explicitly stated by user: highest confidence

```json
{
  "pattern": "User prefers pytest over unittest",
  "confidence": 0.95,
  "evidence": [
    {"session": "a1b2c3d4", "type": "explicit", "text": "always use pytest"},
    {"session": "x9y8z7w6", "type": "observed", "text": "installed pytest, wrote pytest tests"},
    {"session": "m4n5o6p7", "type": "observed", "text": "rejected unittest suggestion"}
  ],
  "first_seen": "2026-01-25",
  "last_seen": "2026-02-12"
}
```

---

## 11. RAG on Sessions (Retrieval-Augmented Generation)

**What:** Build a retrieval layer over all session data so agents can query past conversations as a knowledge source during active sessions.

**Why:** The agent working on your auth module doesn't know that three weeks ago, in a different project, you solved the exact same JWT validation problem. RAG bridges this gap - the agent can search your history for relevant prior work.

### 11a. Indexing Pipeline

```
Session JSONL files
    ↓
Parse & chunk (by message, by topic segment, by file-edit block)
    ↓
Generate embeddings (local model or API)
    ↓
Store in vector index (~/.ab0t/.agents/rag/vectors.bin)
    ↓
Maintain metadata index (session, project, agent, timestamp, topic)
```

**Chunking strategies:**
- **Message-level:** Each user/assistant exchange is a chunk
- **Topic-level:** Group messages by detected topic (see compaction)
- **Artifact-level:** Each file edit, command output, or decision is a chunk
- **Hybrid:** Multiple chunk sizes for different retrieval granularity

### 11b. Query Interface

**CLI usage:**
```
$ agents rag "how did we handle JWT token refresh?"

Top results:
  1. [claude] webapp/a1b2c3d4 (score: 0.92)
     "We implemented token refresh using a middleware that checks
      expiry 5 minutes before deadline and silently refreshes..."

  2. [codex] api/019c4a11 (score: 0.78)
     "Added refresh token rotation - each refresh invalidates
      the old token and issues a new pair..."

  3. [claude] auth-lib/m4n5o6p7 (score: 0.65)
     "The token refresh endpoint accepts the refresh token in
      the Authorization header..."
```

**In-session usage (the real power):**
When an agent is working on a problem, it could automatically query RAG:
- "I'm about to implement JWT refresh. Let me check if we've done this before."
- Surface relevant past solutions before generating new code
- Avoid contradicting past decisions without explicit acknowledgment

### 11c. Index Maintenance

- Incremental: only re-index sessions whose mtime changed
- Background: `agents rag --build` runs indexing as a background job
- Pruning: remove entries for deleted sessions
- Size management: limit index size, prioritize recent and frequently-matched entries

### 11d. Embedding Options

For local-first operation (no API calls needed):
- `sentence-transformers/all-MiniLM-L6-v2` - small, fast, good enough
- `nomic-embed-text` - excellent quality, runs locally
- Or skip embeddings entirely: use BM25/TF-IDF for keyword-based retrieval (simpler, no model needed)

For maximum quality:
- Use the Anthropic or OpenAI embedding APIs
- Cache aggressively (embeddings don't change for immutable session data)

---

## 12. Topic Modeling & Session Intelligence

**What:** Automatically detect topics within and across sessions. Classify what each session is about, track topic evolution over time, and surface patterns.

**Why:** With 100+ sessions, you lose track of what's where. Topic modeling gives you a higher-level view: "I spent 40% of my time on auth, 25% on testing, 15% on infrastructure."

### 12a. Topic Detection

**Per-session topics:**
- Extract key terms from user messages and assistant responses
- Cluster by semantic similarity
- Assign topic labels (can use LLM for labeling, or simple keyword-based)
- Store as metadata alongside session cache

**Cross-session topic tracking:**
- Same topic across multiple sessions = a "thread" of work
- Detect when a topic is abandoned vs completed
- Surface topics that were started but never finished

### 12b. Topic-Based Views

```
$ agents topics

Recent Topics (last 7 days)
────────────────────────────────────────────────────

  auth-middleware     6 sessions, 3 projects    [claude] [codex]
    Last: 1d ago     Total time: 4h 30m
    Projects: webapp, api-server, auth-lib

  test-coverage       3 sessions, 2 projects    [claude]
    Last: 2d ago     Total time: 2h 15m
    Projects: webapp, api-server

  database-migration  2 sessions, 1 project     [codex]
    Last: 5d ago     Total time: 1h 45m
    Projects: api-server

$ agents topic auth-middleware
# Show all sessions related to this topic
```

### 12c. Topic-Aware Compaction

When compacting sessions (see section 7), topic boundaries make natural segmentation points. Instead of arbitrary message-count splits, compact by completed topics:
- Topic A (completed) → summarize to 1 paragraph
- Topic B (completed) → summarize to 1 paragraph
- Topic C (active) → keep in full

---

## 13. Cross-Agent Context Bridge

**What:** Transfer context between different coding agents. Start in Claude, continue in Codex (or vice versa) without losing the thread.

**Why:** Different agents have different strengths. Claude might be better for architecture decisions, Codex for rapid iteration. Or you might hit a context limit in one and want to continue in another. Currently switching agents means starting from scratch.

**Implementation:**
- Extract a portable context snapshot from the source session:
  - Current file states (from file-history-snapshots or tool outputs)
  - Key decisions and constraints (from conversation)
  - Current task description
  - Recent errors and their resolutions
- Format as a "context handoff" document
- Initialize a new session in the target agent with this document as the opening context

```
$ agents bridge a1b2c3d4 --to codex

Extracting context from claude session a1b2c3d4...
  Project: /home/user/webapp
  Topic: auth middleware refactor
  Files in context: 4
  Key decisions: 3

Creating codex session with bridged context...
  New session: 019c5a22
  Context size: 4.2K tokens

Resume: cd /home/user/webapp && codex resume 019c5a22
```

---

## 14. Session Annotations & Bookmarks

**What:** Add human notes, tags, and bookmarks to sessions without modifying the original session files.

**Why:** Session previews show the first user message, but that's often "look at this code" or "help me fix this." You want to tag sessions with meaningful labels: "the one where we designed the payment flow" or "IMPORTANT: has the database migration plan."

**Implementation:**
- Sidecar file: `~/.ab0t/.agents/annotations.json`
- Maps session_id → { tags: [], notes: "", bookmarks: [{msg: N, note: ""}], starred: bool }
- Show annotations in `agents show` and `agents list`
- Filter by tag: `agents list --tag payment`

```
$ agents tag a1b2c3d4 "payment-flow" "architecture"
$ agents note a1b2c3d4 "Final payment flow design - approved by team"
$ agents star a1b2c3d4

$ agents list --tag architecture
# Only show sessions tagged with "architecture"

$ agents starred
# Show all starred sessions across projects
```

---

## 15. Watchdog & Notifications

**What:** Monitor session activity in real-time. Get notifications when long-running agent tasks complete.

**Why:** You kick off a codex session, switch to another terminal, and forget about it. Or you have multiple agents running across projects. A watchdog monitors session files for changes and notifies you.

**Implementation:**
- Use `inotifywait` (Linux) or `fswatch` (macOS) to watch session directories
- Detect new messages written to session files
- Parse the latest record to determine if a turn completed
- Send notification via: terminal bell, desktop notification (notify-send/osascript), or webhook

```
$ agents watch
# Monitor all active sessions

Watching 3 active sessions...
  [claude] webapp/a1b2c3d4   last activity: 2s ago (active)
  [codex]  api/019c4a11      last activity: 30s ago (active)
  [claude] infra/x9y8z7w6    last activity: 5m ago (idle)

  14:32:15  [claude] webapp: Turn completed (45s, 1.2K tokens)
  14:33:02  [codex] api: Turn completed (47s)
  14:35:00  [claude] infra: Session idle > 5m
```

---

## Implementation Priority

### Phase 1 - Quick Wins (days)
These use data we already parse, need minimal new infrastructure:
- `agents search` - text grep across sessions
- `agents log` - chronological activity feed
- `agents cost` - token cost estimation
- Session annotations/bookmarks

### Phase 2 - Medium Effort (weeks)
Require new parsing logic but no external dependencies:
- `agents diff` - file change reconstruction
- `agents export` - session format conversion
- `agents continue` - smart resume
- `agents fork` - session branching
- Topic detection (keyword-based)

### Phase 3 - Ambitious (months)
Require deeper architecture or external models:
- Context compaction (reversible summarization)
- Session blending
- RAG with embeddings
- Self-learning knowledge extraction
- Cross-agent context bridge
- Topic modeling (ML-based)

### Phase 4 - Ecosystem
- Watchdog & notifications
- Web UI for browsing sessions
- Team features (shared knowledge bases)
- Plugin API for custom adapters and extractors

---

## 16. Settings & Configuration Manager (`agents config`)

**What:** A central place to view, edit, audit, and sync the configuration primitives that coding agents support - hooks, skills, commands, permissions, MCP servers, model preferences, and project-level settings. Works across agents via adapters.

**Why:** Every coding agent has its own config format scattered across different locations. Claude has `.claude/settings.json` (project), `~/.claude/settings.json` (global), `CLAUDE.md` files, and `~/.claude/keybindings.json`. Codex has `~/.codex/config.json` and `codex.md`. Managing these by hand is error-prone. You forget what hooks are active, which projects have custom settings, whether your global config overrides your project config. This gives you one place to see and manage it all.

### 16a. Config Audit (`agents config check`)

Scan all config files across all agents and report:
- What's configured at each level (global, project, session)
- Conflicts between levels (project overrides global, etc.)
- Invalid or deprecated settings
- Security review: which commands are allowed, which directories are writable
- Missing recommended settings

```
$ agents config check

Claude Code Configuration Audit
────────────────────────────────────────────────────

Global (~/.claude/settings.json):
  Hooks:
    pre-tool-use:  lint-check.sh (on Edit)
    post-tool-use: auto-format.sh (on Write)
  Permissions:
    allow: Edit, Write, Bash(npm test), Bash(git *)
    deny:  Bash(rm -rf)
  MCP servers: 2 configured (github, linear)

Project: /home/user/webapp (.claude/settings.json)
  Hooks:
    pre-tool-use:  typecheck.sh (on Edit)     <- overrides global lint-check
  Permissions:
    allow: Bash(docker compose *)             <- project-specific
  CLAUDE.md: present (42 lines)

Project: /home/user/api (no .claude/settings.json)
  Using global defaults only
  CLAUDE.md: missing                          <- recommendation: add one

Codex Configuration
  Global (~/.codex/config.json):
    model: gpt-5.3-codex
    approval_policy: auto-edit
  codex.md: not found in any project

Warnings:
  [!] webapp: pre-tool-use hook overrides global without inheriting
  [!] 3 projects have no CLAUDE.md (consider adding guidelines)
  [!] Global allows Bash(git *) - includes destructive operations
```

### 16b. Config Edit (`agents config set`)

Add or modify settings from the command line without hand-editing JSON:

```
$ agents config set hook pre-tool-use "npm run lint" --on Edit --project .
# Add a pre-tool-use hook for the current project

$ agents config set hook post-tool-use "auto-format.sh" --on Write --global
# Add a global post-tool-use hook

$ agents config set permission allow "Bash(docker compose *)" --project .
# Allow docker compose commands in current project

$ agents config set mcp github --url "http://localhost:3000" --global
# Configure an MCP server

$ agents config set model claude-opus-4-6 --project .
# Set preferred model for current project
```

### 16c. Config Sync & Templates

```
$ agents config export > my-config.json
# Export current config (global + project) as portable JSON

$ agents config import my-config.json --project .
# Apply a config to a project

$ agents config template python
# Apply a sensible default config for Python projects:
#   - pytest hook, black formatter, mypy type checker
#   - CLAUDE.md with Python conventions

$ agents config template node
# Node.js defaults:
#   - eslint hook, prettier formatter
#   - CLAUDE.md with Node conventions

$ agents config diff /home/user/webapp /home/user/api
# Compare configs between two projects
```

### 16d. Hooks Management

Hooks are particularly tricky because they're shell commands that run automatically. This deserves special attention:

```
$ agents config hooks

Active Hooks
────────────────────────────────────────────────────

  pre-tool-use:
    [global]  lint-check.sh         on: Edit
    [webapp]  typecheck.sh          on: Edit      (overrides global)
    [webapp]  security-scan.sh      on: Bash

  post-tool-use:
    [global]  auto-format.sh        on: Write

  pre-session:
    (none configured)

$ agents config hooks test
# Dry-run all hooks to verify they work

Testing pre-tool-use hooks:
  lint-check.sh     OK (exit 0, 0.3s)
  typecheck.sh      OK (exit 0, 1.2s)
  security-scan.sh  OK (exit 0, 0.1s)

Testing post-tool-use hooks:
  auto-format.sh    OK (exit 0, 0.5s)

$ agents config hooks add pre-tool-use "pytest --quick" --on Bash --project .
$ agents config hooks rm pre-tool-use lint-check.sh --global
$ agents config hooks enable/disable <name>
```

### 16e. Skills Management

```
$ agents config skills

Installed Skills
────────────────────────────────────────────────────

  /commit          Built-in    Create git commits
  /review-pr       Built-in    Review pull requests
  /pdf             MCP         Process PDF files (via github MCP)
  /linear          MCP         Create Linear issues (via linear MCP)

$ agents config skills add /deploy "scripts/deploy-skill.md" --project .
# Register a custom skill for this project

$ agents config skills list --available
# Show skills available from configured MCP servers
```

### 16f. Cross-Agent Config

The adapter system means we can normalize configs across agents:

```
$ agents config compare
# Show how each agent is configured

                    Claude          Codex
  Model:            opus-4-6        gpt-5.3-codex
  Auto-approve:     no              auto-edit
  Hooks:            3 active        0
  MCP servers:      2               0
  Project docs:     CLAUDE.md       codex.md

$ agents config sync --from claude --to codex
# Sync relevant settings (permissions, project docs) from Claude to Codex
# Translates CLAUDE.md -> codex.md format
```

---

## 17. Backup & Restore (`agents backup`)

**What:** Create complete, restorable backups of all coding agent data - sessions, configs, caches, knowledge bases, and metadata.

**Why:** Session data is irreplaceable. If `~/.claude/` gets wiped (which happens - the user mentioned this in the stats discussion), you lose all conversation history. There's no cloud sync for this data. A backup command makes it trivial to protect.

### 17a. Full Backup

```
$ agents backup

Creating backup...
────────────────────────────────────────────────────

  Claude sessions:   ~/.claude/projects/        487M (99 sessions)
  Claude config:     ~/.claude/settings.json    2K
  Claude metadata:   ~/.claude.json             4K
  Codex sessions:    ~/.codex/sessions/         31M (2 sessions)
  Codex config:      ~/.codex/config.json       1K
  Codex history:     ~/.codex/history.jsonl      8K
  Agents cache:      ~/.ab0t/.agents/           12K
  Agents knowledge:  ~/.ab0t/.agents/knowledge/ 0 (not yet generated)

  Total: 518M

Compressing...
  ~/.ab0t/backups/agents-backup-2026-02-12.tar.zst  (142M)

Backup complete.
  Location: ~/.ab0t/backups/agents-backup-2026-02-12.tar.zst
  Sessions: 101 across 29 projects
  Size:     142M compressed (518M uncompressed)
```

### 17b. Incremental Backup

Full backups are big. Incremental backups only capture what changed since the last backup:

```
$ agents backup --incremental

Incremental backup (since 2026-02-10)
────────────────────────────────────────────────────

  New/modified sessions: 7
  New/modified configs:  1
  Total delta: 18M

  ~/.ab0t/backups/agents-incr-2026-02-12.tar.zst  (4.8M)
```

### 17c. Selective Backup

```
$ agents backup --project /home/user/webapp
# Backup only one project's sessions and config

$ agents backup --agent claude
# Backup only Claude data

$ agents backup --sessions-only
# Skip configs, just backup session files

$ agents backup --since 2026-02-01
# Only sessions modified after a date
```

### 17d. Restore

```
$ agents backup restore agents-backup-2026-02-12.tar.zst

Restore Preview
────────────────────────────────────────────────────

  Sessions:  101 (29 projects)
  Configs:   3 files
  Metadata:  2 files

  Conflicts: 5 sessions exist locally with different content
    Resolution: keep-newer (default) | keep-backup | keep-both

Proceed? [y/N]

$ agents backup restore --dry-run agents-backup-2026-02-12.tar.zst
# Preview what would be restored without writing anything

$ agents backup restore --merge agents-backup-2026-02-12.tar.zst
# Merge: keep both local and backup versions of conflicting sessions
```

### 17e. Backup Scheduling

```
$ agents backup --schedule daily
# Creates a cron job / systemd timer for daily backups

$ agents backup --schedule weekly --keep 4
# Weekly backups, keep last 4

$ agents backup list
# Show existing backups

Backups in ~/.ab0t/backups/
  2026-02-12  142M  full     101 sessions
  2026-02-11  4.8M  incr     7 sessions
  2026-02-10  139M  full     98 sessions

  Total: 286M (3 backups)

$ agents backup prune --keep 5
# Remove old backups, keep last 5
```

### 17f. Remote Backup

```
$ agents backup --to s3://my-bucket/agents/
$ agents backup --to /mnt/nas/backups/agents/
$ agents backup --to gdrive://agents-backup/
# Push backup to remote storage
```

---

## 18. Session Threading (`agents thread`)

**What:** Create a shared communication channel between two or more active sessions. Sessions can post messages to the thread and watch for updates from other sessions. The thread is a simple file (plain text or JSONL) that acts as a shared bulletin board.

**Why:** You're running Claude in one terminal working on the backend API, and Codex in another terminal working on the frontend. They need to coordinate - the frontend needs to know the API contract, the backend needs to know what data the frontend expects. Currently you're the message relay, copy-pasting between terminals. Threading lets the sessions communicate directly.

### 18a. How It Works

A thread is just a file on disk. Sessions are told about it (injected into their context) and can read from it and append to it. The agents CLI manages the lifecycle.

```
Thread file: ~/.ab0t/.agents/threads/api-frontend-sync.thread

Format (JSONL, append-only):
{"ts": "2026-02-12T14:30:00Z", "from": "claude:a1b2c3d4", "msg": "API endpoint POST /users expects {name, email, role}. Returns {id, name, email, role, created_at}. Auth via Bearer token."}
{"ts": "2026-02-12T14:32:00Z", "from": "codex:019c4a11", "msg": "Frontend form will send {name, email, role}. Need to know: is role an enum? What values?"}
{"ts": "2026-02-12T14:33:00Z", "from": "claude:a1b2c3d4", "msg": "Role is enum: 'admin' | 'user' | 'viewer'. Default: 'user'."}
```

### 18b. Creating & Joining Threads

```
$ agents thread create api-frontend-sync
# Creates a new thread

Thread created: api-frontend-sync
  File: ~/.ab0t/.agents/threads/api-frontend-sync.thread

  To join from a session, tell the agent:
    "Watch the thread file at ~/.ab0t/.agents/threads/api-frontend-sync.thread
     Post updates there and check it periodically for messages from other sessions."

$ agents thread list

Active Threads
────────────────────────────────────────────────────

  api-frontend-sync    2 participants    last message: 2m ago
    claude:a1b2c3d4  (webapp backend)
    codex:019c4a11   (webapp frontend)

  db-migration-coord   1 participant     last message: 1h ago
    claude:x9y8z7w6  (database migration)

$ agents thread show api-frontend-sync

Thread: api-frontend-sync
────────────────────────────────────────────────────

  14:30  [claude] a1b2c3d4:
    API endpoint POST /users expects {name, email, role}.
    Returns {id, name, email, role, created_at}. Auth via Bearer token.

  14:32  [codex] 019c4a11:
    Frontend form will send {name, email, role}.
    Need to know: is role an enum? What values?

  14:33  [claude] a1b2c3d4:
    Role is enum: 'admin' | 'user' | 'viewer'. Default: 'user'.
```

### 18c. Session Integration

The magic is in how sessions interact with the thread. There are several approaches, from simple to sophisticated:

**Approach 1: File pointer (simplest)**
Tell the agent about the thread file path. The agent can read it with its file tools and append to it. No special tooling needed - it's just a file.

```
In your session, tell the agent:
"There's a coordination thread at ~/.ab0t/.agents/threads/api-frontend-sync.thread
Check it before making API contract decisions, and post your decisions there."
```

The agent naturally reads and writes to it using its existing file tools. Other sessions see the updates when they read the file.

**Approach 2: CLAUDE.md / codex.md injection**
Automatically add thread awareness to project docs:

```
$ agents thread join api-frontend-sync --project .

# Appends to CLAUDE.md:
# ## Active Thread: api-frontend-sync
# Check ~/.ab0t/.agents/threads/api-frontend-sync.thread periodically.
# Post updates about API contracts and data models there.
# Other sessions working on related code are watching this thread.
```

**Approach 3: Hook-based (automated)**
Use pre/post hooks to automatically inject thread content:

```
$ agents thread watch api-frontend-sync --hook

# Creates a pre-tool-use hook that:
# 1. Reads the thread file
# 2. If new messages since last check, injects them as a system message
# 3. The agent sees: "[Thread update] codex:019c4a11: Role is enum..."
```

### 18d. Thread Patterns

**Coordinator pattern:**
One session is the "coordinator" that manages the thread:
```
$ agents thread create sprint-plan --coordinator claude:a1b2c3d4
# Coordinator session defines tasks, other sessions report progress
```

**Broadcast pattern:**
One session posts updates, others consume:
```
$ agents thread create api-changes --mode broadcast --from claude:a1b2c3d4
# Only the source session can write, others read-only
```

**Chat pattern:**
All participants can read and write freely (default):
```
$ agents thread create debug-collab
# Open discussion between sessions
```

**Shared scratchpad:**
A thread that holds shared state (like a shared document) rather than a message stream:
```
$ agents thread create api-contract --mode scratchpad

# Instead of appending messages, sessions update sections:
# ## Endpoints
# POST /users -> {id, name, email, role, created_at}
# GET /users/:id -> {id, name, email, role, created_at}
#
# ## Auth
# Bearer token in Authorization header
# Tokens expire after 24h
```

### 18e. Thread Lifecycle

```
$ agents thread create <name>           # Create
$ agents thread list                    # List active threads
$ agents thread show <name>             # Show messages
$ agents thread post <name> "message"   # Post from CLI (not from a session)
$ agents thread close <name>            # Archive thread
$ agents thread archive                 # List closed threads
$ agents thread reopen <name>           # Reopen archived thread
```

### 18f. Cross-Agent Threading

Threads work across agents because they're just files. A Claude session and a Codex session can both read and write to the same thread file. The thread format is agent-agnostic - it's the agents CLI that manages it, not the individual agents.

```
Terminal 1 (Claude - backend):
  "I've updated the thread with the new API contract for the /orders endpoint"

Terminal 2 (Codex - frontend):
  *reads thread*
  "Got it - the /orders endpoint returns paginated results with cursor.
   Updating the frontend fetch logic."
  *writes to thread*
  "Frontend expects the cursor in the response body as 'next_cursor',
   not in headers. Can you confirm?"

Terminal 1 (Claude - backend):
  *reads thread*
  "Confirmed - cursor will be in response body as 'next_cursor'."
```

---

## 19. Session Pinning & Workspace

**What:** Pin important sessions to a workspace view. Group related sessions (even across projects and agents) into named workspaces for quick access.

**Why:** You're working on a feature that spans 3 projects and 5 sessions. `agents list` shows everything by recency, but you want a focused view of just the sessions relevant to your current work.

```
$ agents workspace create auth-overhaul

$ agents workspace add auth-overhaul a1b2c3d4  # claude session
$ agents workspace add auth-overhaul 019c4a11  # codex session
$ agents workspace add auth-overhaul x9y8z7w6  # another project

$ agents workspace auth-overhaul

Workspace: auth-overhaul (3 sessions)
────────────────────────────────────────────────────

  [claude] a1b2c3d4  /home/user/webapp        5m ago
    "refactoring auth middleware..."
  [codex]  019c4a11  /home/user/api            1h ago
    "implementing token refresh..."
  [claude] x9y8z7w6  /home/user/auth-lib       2d ago
    "updating JWT validation logic..."

  Resume: agents resume <num>
  Thread: agents thread create auth-overhaul-sync

$ agents workspace list
# Show all workspaces
```

---

## Implementation Priority (Updated)

### Phase 1 - Quick Wins (days)
These use data we already parse, need minimal new infrastructure:
- `agents search` - text grep across sessions
- `agents log` - chronological activity feed
- `agents cost` - token cost estimation
- Session annotations/bookmarks
- `agents backup` (full backup, basic)
- `agents config check` (audit existing configs)

### Phase 2 - Medium Effort (weeks)
Require new parsing logic but no external dependencies:
- `agents diff` - file change reconstruction
- `agents export` - session format conversion
- `agents continue` - smart resume
- `agents fork` - session branching
- `agents thread` (basic: file-based coordination)
- `agents config set` (edit configs from CLI)
- `agents workspace` - session grouping
- Topic detection (keyword-based)
- Backup incremental + scheduling

### Phase 3 - Ambitious (months)
Require deeper architecture or external models:
- Context compaction (reversible summarization)
- Session blending
- RAG with embeddings
- Self-learning knowledge extraction
- Cross-agent context bridge
- Topic modeling (ML-based)
- Thread hooks (automated injection)
- Config sync across agents
- Config templates

### Phase 4 - Ecosystem
- Watchdog & notifications
- Web UI for browsing sessions
- Team features (shared knowledge bases, shared threads)
- Plugin API for custom adapters and extractors
- Remote backup (S3, NAS)

---

## Design Principles

1. **Never modify original session files.** All overlays, annotations, compactions, and indexes are separate files. The source of truth is always the raw JSONL.

2. **Adapter-agnostic.** Every feature works across all agents. If a feature can't extract data from one agent's format, it degrades gracefully (shows what it can, skips what it can't).

3. **Local-first.** No cloud services required. All processing happens on-device. API calls (for embeddings, summarization) are optional enhancements with local fallbacks.

4. **Incremental.** Indexes, caches, and knowledge bases are built incrementally. A full rebuild is never required, only catch-up on new/modified sessions.

5. **Reversible.** Compaction, learning, and any transformation that synthesizes data is always reversible. The user can delete any derived data and regenerate it.

6. **Fast by default.** The common path (list, show, resume) stays fast. Heavy features (search indexing, RAG, learning) run on demand or in the background.
