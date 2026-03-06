# agents CLI - Task List

## Architecture: LLM Integration Layer

All modules that do summarization, extraction, classification, or synthesis should use LLM calls with:
- **Jinja2 prompt templates** in `scripts/prompts/` (one `.j2` file per prompt)
- **Input schemas** (Python dataclasses or typed dicts defining what goes into the prompt)
- **Output schemas** (structured JSON parsed from LLM response, validated)
- **A shared LLM client** in `scripts/llm.py` that handles: model selection, API calls, retries, cost tracking, and fallback to local heuristics when no API key is available
- **Graceful degradation**: every LLM-powered feature must still work (with cruder results) when offline or without an API key

### Modules that need LLM integration:
- **compact.py** - generate real summaries per topic segment (decisions, constraints, errors resolved)
- **blend.py** - synthesize context from multiple sessions intelligently, not just concatenate
- **learn.py** - extract structured preferences, patterns, solutions with confidence scoring
- **bridge.py** - generate concise, actionable handoff documents
- **topics.py** - generate human-readable topic labels, detect topic relationships
- **rag.py** - optional: rerank results with LLM, generate answer from retrieved chunks
- **search.py** - optional: query expansion, semantic reranking

---

## P0: Bugs (fix immediately)

- [x] **workspace.py env var mismatch** - Python now reads `WS_NAME` first, falls back to `WORKSPACE_NAME`.
- [x] **backup.py restore is a no-op** - Implemented actual restore with `--confirm` flag and conflict resolution (keep-newer / keep-backup / keep-both).
- [x] **annotate.py tag parsing mismatch** - Now accepts both comma-separated and space-separated via `re.split(r'[,\s]+', ...)`.
- [x] **cont.py CONTINUE_CMD not evaluated** - Now uses `os.chdir()` + `os.execvp()` to directly launch the agent.

---

## P1: Shared Infrastructure

- [x] **Create `scripts/modules/utils.py`** - Extract all duplicated code:
  - ANSI color constants (WHITE, CYAN, GREEN, YELLOW, MAGENTA, BLUE, GRAY, RED, BOLD, DIM, R)
  - `time_ago(ts)` - human-friendly time delta
  - `fmt_duration(seconds)` - format seconds as Xh Ym
  - `human_size(bytes)` - format bytes as K/M/G
  - `resolve_session(session_key)` - resolve numeric key or ID to (fpath, agent_name, project, session_id)
  - `get_first_message(fpath, agent_name)` - extract first user message preview
  - `extract_text_from_record(record, agent_name)` - extract text content from JSONL record
  - `load_json(path)` / `save_json(path, data)` - safe JSON I/O
  - Auto-build sessions cache if missing (so modules don't silently fail)

- [x] **Create `scripts/llm.py`** - Shared LLM client:
  - Support Anthropic API (claude) and OpenAI API (for codex users)
  - API key from env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) or config
  - Model selection (default to haiku/small for cheap operations, sonnet for complex)
  - Jinja2 template rendering from `scripts/prompts/*.j2`
  - Structured output parsing (JSON mode or extraction)
  - Cost tracking (accumulate and report at end)
  - Retry with backoff
  - `available()` check - returns False if no API key, so modules can fall back
  - Rate limiting / concurrency control

- [x] **Create `scripts/prompts/` directory** with Jinja2 templates:
  - `compact_summarize.j2` - summarize a conversation segment
  - `blend_synthesize.j2` - synthesize context from multiple sessions
  - `learn_extract.j2` - extract preferences, patterns, solutions from messages
  - `bridge_handoff.j2` - generate a concise handoff document
  - `topics_label.j2` - generate human-readable topic labels
  - `rag_answer.j2` - generate answer from retrieved chunks
  - `search_rerank.j2` - rerank search results for relevance

- [x] **Create `scripts/schemas.py`** - Input/output dataclasses:
  - `CompactInput` / `CompactOutput` - segment messages in, summary + decisions + artifacts out
  - `BlendInput` / `BlendOutput` - multiple session contexts in, synthesized context out
  - `LearnInput` / `LearnOutput` - session messages in, preferences + patterns + solutions out
  - `BridgeInput` / `BridgeOutput` - session context in, handoff document out
  - `TopicInput` / `TopicOutput` - term frequencies in, labeled topics out

- [x] **Add `__main__` guards to all modules** - Wrap dispatch code in `if __name__ == "__main__":` so modules can be imported for testing.

- [ ] **Refactor all 19 modules to use `utils.py`** - Replace duplicated code with imports. This is mechanical but touches every file.

---

## P2: Module Improvements

### search.py
- [ ] Add incremental inverted index (`~/.ab0t/.agents/search_index.json`) keyed by session mtime
- [ ] Add `--project` filter to scope search to one project
- [ ] Unify codex session ID extraction into shared resolver
- [ ] Optional: LLM query expansion (turn "auth bug" into "authentication authorization JWT token middleware error")
- [ ] Optional: LLM reranking of top-N results

### log.py
- [ ] Add `--since DATE` filter (ISO date or relative like "3d", "2w")
- [ ] Cache first-message previews in sessions cache to avoid re-reading files
- [ ] Remove `OrderedDict` import (regular dict maintains order in Python 3.7+)
- [ ] Add session count per day in day headers

### cost.py
- [ ] Add `--budget N` threshold (warn when daily/weekly spend exceeds $N)
- [ ] Add `--sessions` mode showing per-session cost breakdown
- [ ] Add pricing freshness note (print when pricing table was last updated)
- [ ] Consider auto-fetching current pricing from API docs

### diff.py
- [ ] Parse `file-history-snapshot` records for actual content diffs between snapshots
- [ ] Cross-reference with `git log` by timestamp range (show which commits overlap the session)
- [ ] Estimate line count changes from Write/Edit tool inputs (count newlines in content)
- [ ] Categorize commands (test, build, git, install, other)
- [ ] Add `--git` flag to show git-integrated view

### export.py
- [ ] Add `html` format with syntax highlighting (use pygments or simple CSS)
- [ ] Include tool results/outputs (command stdout, not just `[Write: path]`)
- [ ] Add session duration and file size in metadata header
- [ ] Add `--no-system` flag to strip system/tool records
- [ ] Add `--messages N` to export last N messages only

### cont.py
- [ ] Fix bash integration: Python should exec directly (use `os.execvp`) or bash should `eval` output
- [ ] Add file overlap scoring (check recently modified files in cwd against session file operations)
- [ ] Add parent directory fallback (if no sessions for cwd, check parent dirs)
- [ ] Add `--agent` filter (prefer claude or codex)
- [ ] Show session first message in candidate display

### fork.py
- [ ] Make forks resumable: write fork file into `~/.claude/projects/` with correct project dir name so Claude can resume it
- [ ] Add fork tree visualization (`agents forks <session>` showing parent/child relationships)
- [ ] Add `--to codex` cross-agent forking with format translation
- [ ] Count "turns" (user+assistant pairs) not raw messages for fork point display
- [ ] Add `--list` to show all forks

### blend.py (major rework)
- [ ] **LLM-powered synthesis**: Use prompt template to generate intelligent merged context, not concatenation
- [ ] Extract decisions, constraints, technical patterns from each session (reuse bridge.py logic)
- [ ] Add provenance tracking (which facts came from which session)
- [ ] "Summary" mode should produce an actual LLM-generated summary
- [ ] "Artifacts" mode should show final file states, not just file paths
- [ ] Add `--output-format` (md, json, session) - "session" creates a resumable session file
- [ ] Fallback: when no LLM available, use current concatenation approach with a warning

### learn.py (major rework)
- [ ] **LLM-powered extraction**: Use prompt template to extract structured knowledge from session messages
- [ ] Implement confidence scoring: seen 1x (low), 3x+ (medium), cross-project (high), explicitly stated (highest)
- [ ] Deduplicate preferences before storing (merge similar entries)
- [ ] Per-project knowledge files (`~/.ab0t/.agents/knowledge/projects/`)
- [ ] Cap knowledge file size, prune low-confidence items
- [ ] Extract workflow patterns (sequence of actions user commonly takes)
- [ ] Extract real problem-solution pairs (user describes error, assistant provides fix that works)
- [ ] Add `--review` interactive mode to approve/reject extracted knowledge
- [ ] Fallback: when no LLM, use current regex approach with a note about limited accuracy

### backup.py
- [ ] Implement actual restore with `--confirm` flag
- [ ] Add conflict detection and resolution modes (keep-newer, keep-backup, keep-both)
- [ ] Add `--prune --keep N` to clean old backups
- [ ] Add `--dry-run` for restore preview (rename current preview behavior)
- [ ] Add restore verification (check file integrity after extract)

### thread.py
- [ ] Add `reopen` action to unarchive threads
- [ ] Add `join` action: append thread awareness to CLAUDE.md / codex.md for a project
- [ ] Add participant tracking (which sessions have posted to a thread)
- [ ] Add thread modes: `--mode broadcast` (one writer, many readers), `--mode scratchpad` (shared document, not append-only)
- [ ] Add `--watch` flag to tail thread in real-time (like `tail -f`)

### annotate.py
- [ ] Fix tag parsing: accept both comma-separated and space-separated in Python
- [ ] Integrate with main `agents show` / `agents list` display (show stars, tags inline)
- [ ] Add `--tag` filter support for `agents list`
- [ ] Add guidance for bookmark message numbers (show message count for a session)
- [ ] Add `agents annotate show --all` to list all annotated sessions

### config.py
- [ ] Add `config set` to edit configs from CLI (hooks, permissions, model, MCP servers)
- [ ] Add `config hooks test` to dry-run all configured hooks
- [ ] Add `config export` / `config import` for portable config bundles
- [ ] Add `config template python|node|rust` with sensible defaults per stack
- [ ] Add `config sync --from claude --to codex` (translate CLAUDE.md to codex.md)

### workspace.py
- [ ] Fix env var: rename `WORKSPACE_NAME` to `WS_NAME` (or vice versa) and fix both sides
- [ ] Add resume integration (allow `agents workspace resume <workspace> <num>`)
- [ ] Show thread suggestions for multi-project workspaces
- [ ] Add `--active` filter to show only workspaces with recently-active sessions

### topics.py
- [ ] **LLM-powered labeling**: Use prompt template to generate human-readable topic labels from top terms
- [ ] Improve clustering (cosine similarity on term vectors instead of substring matching)
- [ ] Show total session time per topic
- [ ] Detect abandoned topics (last activity > 14d, no completion signals)
- [ ] Add `--since` date filter
- [ ] Fallback: when no LLM, use current keyword approach for labels

### compact.py (major rework)
- [ ] **LLM-powered summarization**: Use prompt template to generate real summaries per segment preserving:
  - Key decisions made
  - Artifacts produced (files, commands)
  - Constraints and requirements stated
  - Errors encountered and resolutions
- [ ] Add `--section N` selective uncompact (expand one section while keeping others compact)
- [ ] Implement time-based strategy (compact everything older than N hours)
- [ ] Implement topic-based strategy (compact completed topics, keep active in full)
- [ ] Add integration with resume: `agents resume 1 --compact` / `agents resume 1 --compact --keep-last 50`
- [ ] Fallback: when no LLM, use current heuristic extraction with a note

### bridge.py
- [ ] **LLM-powered handoff**: Use prompt template to generate concise, actionable handoff document
- [ ] Add `--clipboard` flag to copy handoff to clipboard
- [ ] Add format translation hints for target agent (e.g., note Claude-specific vs Codex-specific conventions)
- [ ] Add `--brief` mode for a one-paragraph summary vs full handoff
- [ ] Fallback: when no LLM, use current regex extraction

### rag.py
- [ ] Add incremental indexing (track session mtimes, only re-index changed files)
- [ ] Add artifact-level chunks (file edits, command outputs as separate searchable units)
- [ ] Add index staleness warning (print age of index, suggest rebuild if stale)
- [ ] Add `--reindex` flag for force rebuild of specific sessions
- [ ] Optional: LLM reranking of top results
- [ ] Optional: LLM-generated answer from retrieved chunks ("RAG answer" mode)
- [ ] Optional: embedding-based retrieval when sentence-transformers is available

### watch.py
- [ ] Add optional `inotifywait` (Linux) / `fswatch` (macOS) support for event-driven watching
- [ ] Add `--notify` flag for desktop notifications (`notify-send` on Linux, `osascript` on macOS)
- [ ] Parse completed turns and show duration + token count
- [ ] Add `--project` filter to watch only one project's sessions
- [ ] Add `--quiet` mode (only show notifications, no status updates)

---

## P3: Integration Points

These connect modules together for compound value:

- [ ] **Annotations in listings**: `agents show` and `agents list` display stars, tags, notes inline
- [ ] **Topics inform compaction**: compact.py uses topic boundaries from topics.py for segmentation
- [ ] **RAG in resume**: when resuming a session, optionally query RAG for relevant prior context
- [ ] **Learn feeds resume**: inject project-specific knowledge when starting/resuming sessions
- [ ] **Watch triggers notifications**: watch.py detects turn completion and fires desktop notification
- [ ] **Workspace + thread**: creating a workspace suggests creating a coordination thread
- [ ] **Bridge + fork**: bridge creates a fork in the target agent's format
- [ ] **Cost in watch**: live cost tracking during active session monitoring

---

## P4: Testing

- [ ] Create `tests/` directory with pytest structure
- [ ] Unit tests for `utils.py` (time_ago, fmt_duration, human_size, resolve_session)
- [ ] Unit tests for `llm.py` (template rendering, schema validation, fallback behavior)
- [ ] Create test fixtures: sample Claude JSONL, sample Codex JSONL
- [ ] Integration tests for each module's happy path (mock adapters)
- [ ] Test LLM fallback behavior (verify all modules work without API key)
