# Rewrite learn.py: Regex → Multi-Stage LLM Pipeline

## Problem
learn.py uses fake regex patterns to extract preferences/solutions from session history. This produces low-quality, shallow extractions. The user wants all reasoning done by targeted LLM prompts with structured output, framed as autonomous self-learning and meta-cognition.

## Architecture: 4-Stage LLM Pipeline

```
Session JSONL files (read-only)
        │
        ▼
┌─────────────────────────────┐
│ Stage 1: SESSION DIGEST     │  Haiku — understand what happened
│ (per session, batched msgs) │  "Summarize this coding session"
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ Stage 2: ENTITY EXTRACTION  │  Haiku — NER-style extraction
│ (per session digest)        │  "Extract tools, preferences, patterns"
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ Stage 3: REFLECTION         │  Sonnet — meta-cognition
│ (per session digest)        │  "What should I learn from this?"
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│ Stage 4: KNOWLEDGE JUDGE    │  Sonnet — LLM-as-judge
│ (all new findings + existing│  "Merge, deduplicate, score"
│  knowledge base)            │
└────────────┬────────────────┘
             │
             ▼
   knowledge.json (updated)
   ~/.ab0t/.agents/knowledge/
```

---

## Stage 1: Session Digest (`learn_digest.j2`)

**Purpose:** Understand what happened before extracting knowledge. Raw messages are too noisy — digest first.

**Model:** Haiku (cheap, fast — runs per session)

**Batching:** Sessions > 50 messages get chunked into ~40-message windows with 5-message overlap. Each chunk gets a digest. Multiple digests per session get concatenated.

**Prompt framing:**
```
You are an autonomous coding agent reviewing your own past work session.
Your goal is self-improvement through understanding what happened.

Summarize this session between a user and a coding agent.
Focus on: what was the goal, what approach was taken, what tools/libraries
were used, what files were changed, what problems came up, and what the
outcome was.

Agent: {{ agent }}
Project: {{ project }}

## Messages
{% for msg in messages %}
[{{ msg.role }}]: {{ msg.text }}
{% endfor %}

Respond with ONLY valid JSON:
{
  "goal": "what the user was trying to accomplish",
  "approach": "how the agent tackled it",
  "tools_and_libs": ["list", "of", "tools", "libraries", "frameworks"],
  "files_modified": ["list of file paths"],
  "problems_encountered": ["list of problems/errors"],
  "outcome": "completed|partial|failed|exploratory",
  "key_commands": ["significant shell commands run"],
  "languages": ["python", "javascript", ...]
}
```

**Schema:**
```python
@dataclass
class DigestOutput:
    goal: str
    approach: str
    tools_and_libs: List[str]
    files_modified: List[str]
    problems_encountered: List[str]
    outcome: str  # completed|partial|failed|exploratory
    key_commands: List[str]
    languages: List[str]
```

---

## Stage 2: Entity Extraction (`learn_entities.j2`)

**Purpose:** NER-style extraction of concrete, actionable entities from the digest + raw messages.

**Model:** Haiku

**Prompt framing:**
```
You are an autonomous coding agent performing named entity extraction
on your own session history for self-learning.

Given a session digest and key user messages, extract:

1. **Preferences** — things the user explicitly or implicitly prefers
   (coding style, tools, workflows, testing approaches, architecture choices)
2. **Tools & Stack** — specific technologies, libraries, frameworks,
   package managers, test runners, linters, formatters used or mentioned
3. **Coding Patterns** — recurring approaches (e.g. "writes tests first",
   "uses dataclasses over dicts", "prefers functional style")
4. **Explicit Instructions** — direct commands from the user about how
   to work (e.g. "never auto-commit", "always use type hints")

## Session Digest
{{ digest | tojson }}

## Key User Messages
{% for msg in user_messages %}
- {{ msg }}
{% endfor %}

## Project Context
Agent: {{ agent }}
Project: {{ project }}

Respond with ONLY valid JSON:
{
  "preferences": [
    {"entity": "description", "confidence": "high|medium|low",
     "category": "style|tooling|workflow|testing|architecture",
     "evidence": "quote or paraphrase from session"}
  ],
  "tools_and_stack": [
    {"name": "tool name", "role": "what it's used for",
     "sentiment": "preferred|used|mentioned|rejected"}
  ],
  "coding_patterns": [
    {"pattern": "description", "frequency": "once|recurring"}
  ],
  "explicit_instructions": [
    {"instruction": "what the user said", "scope": "global|project"}
  ]
}
```

**Schema:**
```python
@dataclass
class ExtractedPreference:
    entity: str
    confidence: str  # high|medium|low
    category: str    # style|tooling|workflow|testing|architecture
    evidence: str

@dataclass
class ExtractedTool:
    name: str
    role: str
    sentiment: str  # preferred|used|mentioned|rejected

@dataclass
class ExtractedPattern:
    pattern: str
    frequency: str  # once|recurring

@dataclass
class ExtractedInstruction:
    instruction: str
    scope: str  # global|project

@dataclass
class EntityOutput:
    preferences: List[ExtractedPreference]
    tools_and_stack: List[ExtractedTool]
    coding_patterns: List[ExtractedPattern]
    explicit_instructions: List[ExtractedInstruction]
```

---

## Stage 3: Reflection (`learn_reflect.j2`)

**Purpose:** Meta-cognitive self-reflection. This is the unique part — the agent reflects on what it can learn and improve.

**Model:** Sonnet (needs deeper reasoning)

**Prompt framing:**
```
You are an autonomous coding agent capable of meta-cognition and
self-improvement. You are reviewing a completed work session to learn
from it.

This is NOT generic pattern extraction. You are reflecting on your own
performance to become a better agent. Think about:

- What strategies worked well and should be repeated?
- What went wrong and how could it be avoided next time?
- What did the user have to correct or repeat? (signals for improvement)
- Were there moments of wasted effort? Why?
- What domain knowledge was gained that applies beyond this session?
- What workflow optimizations emerged?

## Session Digest
{{ digest | tojson }}

## Entities Extracted
{{ entities | tojson }}

## Problems Encountered
{% for p in problems %}
- {{ p }}
{% endfor %}

## Project: {{ project }}

Respond with ONLY valid JSON:
{
  "effective_strategies": [
    {"strategy": "what worked", "why": "why it worked",
     "reusable": true|false}
  ],
  "mistakes_and_corrections": [
    {"mistake": "what went wrong",
     "correction": "how it was fixed",
     "prevention": "how to avoid it next time"}
  ],
  "user_friction": [
    {"friction": "where the user had to intervene or repeat",
     "improvement": "what the agent should do differently"}
  ],
  "domain_insights": [
    {"insight": "knowledge gained",
     "applies_to": "scope — project, language, or general"}
  ],
  "workflow_improvements": [
    {"current": "what was done",
     "suggested": "what would be better",
     "impact": "high|medium|low"}
  ]
}
```

**Schema:**
```python
@dataclass
class EffectiveStrategy:
    strategy: str
    why: str
    reusable: bool

@dataclass
class MistakeCorrection:
    mistake: str
    correction: str
    prevention: str

@dataclass
class UserFriction:
    friction: str
    improvement: str

@dataclass
class DomainInsight:
    insight: str
    applies_to: str

@dataclass
class WorkflowImprovement:
    current: str
    suggested: str
    impact: str  # high|medium|low

@dataclass
class ReflectionOutput:
    effective_strategies: List[EffectiveStrategy]
    mistakes_and_corrections: List[MistakeCorrection]
    user_friction: List[UserFriction]
    domain_insights: List[DomainInsight]
    workflow_improvements: List[WorkflowImprovement]
```

---

## Stage 4: Knowledge Judge (`learn_judge.j2`)

**Purpose:** LLM-as-judge pattern. Merges new session findings into existing knowledge base. Deduplicates, resolves conflicts, adjusts confidence scores.

**Model:** Sonnet (needs judgment, runs once per scan, not per session)

**Runs:** Once after all sessions are processed. Takes accumulated new findings + existing knowledge.json.

**Prompt framing:**
```
You are a knowledge curator for an autonomous coding agent's self-learning
system. Your role is to judge and consolidate knowledge.

You have two inputs:
1. EXISTING knowledge base (what we already know)
2. NEW findings from recently scanned sessions

Your job:
- Merge new findings into existing knowledge
- Deduplicate: if a new finding matches an existing one, increase confidence
- Resolve conflicts: if new evidence contradicts existing knowledge, keep the
  more recent/confident one and note the change
- Promote confidence: items seen across multiple sessions should be "high"
- Demote stale items: preferences contradicted by recent behavior drop to "low"
- Remove noise: drop items with "low" confidence that have no corroborating evidence

## Existing Knowledge
{{ existing | tojson }}

## New Findings
{{ new_findings | tojson }}

Respond with ONLY valid JSON — the complete updated knowledge base:
{
  "preferences": [
    {"text": "...", "confidence": "high|medium|low",
     "category": "style|tooling|workflow|testing|architecture",
     "evidence_count": 3, "last_seen": "project name"}
  ],
  "tools_and_stack": [
    {"name": "...", "role": "...", "sentiment": "preferred|used|rejected",
     "frequency": 5}
  ],
  "effective_strategies": [
    {"strategy": "...", "why": "...", "times_seen": 2}
  ],
  "mistakes_to_avoid": [
    {"mistake": "...", "prevention": "...", "confidence": "high|medium|low"}
  ],
  "domain_insights": [
    {"insight": "...", "applies_to": "...", "confidence": "high|medium|low"}
  ],
  "workflow_improvements": [
    {"suggestion": "...", "impact": "high|medium|low", "evidence_count": 1}
  ],
  "explicit_instructions": [
    {"instruction": "...", "scope": "global|project"}
  ]
}
```

**Schema:**
```python
@dataclass
class JudgedPreference:
    text: str
    confidence: str
    category: str
    evidence_count: int
    last_seen: str

@dataclass
class JudgedTool:
    name: str
    role: str
    sentiment: str
    frequency: int

@dataclass
class JudgedStrategy:
    strategy: str
    why: str
    times_seen: int

@dataclass
class JudgedMistake:
    mistake: str
    prevention: str
    confidence: str

@dataclass
class JudgedInsight:
    insight: str
    applies_to: str
    confidence: str

@dataclass
class JudgedImprovement:
    suggestion: str
    impact: str
    evidence_count: int

@dataclass
class JudgedInstruction:
    instruction: str
    scope: str

@dataclass
class KnowledgeBase:
    preferences: List[JudgedPreference]
    tools_and_stack: List[JudgedTool]
    effective_strategies: List[JudgedStrategy]
    mistakes_to_avoid: List[JudgedMistake]
    domain_insights: List[JudgedInsight]
    workflow_improvements: List[JudgedImprovement]
    explicit_instructions: List[JudgedInstruction]
```

---

## Files to Create/Modify

### New prompt templates
- `scripts/prompts/learn_digest.j2` — Stage 1
- `scripts/prompts/learn_entities.j2` — Stage 2
- `scripts/prompts/learn_reflect.j2` — Stage 3
- `scripts/prompts/learn_judge.j2` — Stage 4

### Delete
- `scripts/prompts/learn_extract.j2` — replaced by the 4 new templates

### Modify
- `scripts/schemas.py` — replace Learn* schemas with the new ones above
- `scripts/modules/learn.py` — complete rewrite

---

## learn.py Rewrite Structure

```python
# Core flow
def extract_messages(fpath, agent_name):
    """Read JSONL, return list of {role, text} dicts."""
    # Use extract_text_from_record from utils.py

def batch_messages(messages, batch_size=40, overlap=5):
    """Split messages into overlapping windows for context limits."""

def stage_digest(llm, messages_batch, agent, project):
    """Stage 1: Get session digest via LLM."""
    return llm.render_and_call_json("learn_digest", {...})

def stage_entities(llm, digest, user_messages, agent, project):
    """Stage 2: NER-style entity extraction."""
    return llm.render_and_call_json("learn_entities", {...})

def stage_reflect(llm, digest, entities, problems, project):
    """Stage 3: Meta-cognitive reflection."""
    return llm.render_and_call_json("learn_reflect", {...})

def stage_judge(llm, existing_knowledge, new_findings):
    """Stage 4: LLM-as-judge knowledge consolidation."""
    return llm.render_and_call_json("learn_judge", {...})

def process_session(llm, fpath, agent_name, project):
    """Run stages 1-3 on a single session. Return raw findings."""
    messages = extract_messages(fpath, agent_name)
    if len(messages) < 3:
        return None

    # Stage 1: Digest (per batch)
    batches = batch_messages(messages)
    digests = [stage_digest(llm, batch, agent_name, project) for batch in batches]
    digest = merge_digests(digests)  # combine if multiple batches

    # Stage 2: Entity extraction
    user_messages = [m["text"][:200] for m in messages if m["role"] == "user"][:15]
    entities = stage_entities(llm, digest, user_messages, agent_name, project)

    # Stage 3: Reflection
    reflection = stage_reflect(llm, digest, entities, digest.get("problems_encountered", []), project)

    return {
        "digest": digest,
        "entities": entities,
        "reflection": reflection,
        "project": project,
        "agent": agent_name,
    }

def cmd_scan():
    """Main scan command."""
    llm = get_llm()
    knowledge = load_knowledge()
    scanned = set(knowledge.get("scanned_sessions", []))

    all_findings = []
    for adapter in available:
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent or fpath in scanned:
                continue
            findings = process_session(llm, fpath, adapter.name, display_path)
            if findings:
                all_findings.append(findings)
            scanned.add(fpath)

    if all_findings:
        # Stage 4: Judge (once, merges everything)
        new_findings = aggregate_findings(all_findings)
        existing = knowledge.get("judged", {})
        judged = stage_judge(llm, existing, new_findings)
        knowledge["judged"] = judged

    knowledge["scanned_sessions"] = list(scanned)
    knowledge["last_scan"] = datetime.utcnow().isoformat() + "Z"
    save_knowledge(knowledge)

def cmd_show():
    """Display knowledge — reads from knowledge["judged"]."""

def cmd_apply():
    """Generate CLAUDE.md — uses judged preferences + instructions."""
```

---

## Model Selection & Cost

| Stage | Model | Runs | Est. tokens/call | Why |
|-------|-------|------|-------------------|-----|
| Digest | Haiku | per session batch | ~800 in, ~300 out | Fast summarization |
| Entities | Haiku | per session | ~600 in, ~400 out | Structured extraction |
| Reflect | Sonnet | per session | ~800 in, ~500 out | Needs reasoning depth |
| Judge | Sonnet | once per scan | ~2000 in, ~1500 out | Judgment + merging |

**Cost estimate for 20 sessions:**
- Haiku calls: ~40 × $0.001 = ~$0.04
- Sonnet calls: ~21 × $0.01 = ~$0.21
- Total: ~$0.25 per full scan

---

## knowledge.json New Structure

```json
{
  "scanned_sessions": ["path1", "path2"],
  "last_scan": "2026-02-12T...",
  "session_findings": {
    "session_id": {
      "digest": {...},
      "entities": {...},
      "reflection": {...}
    }
  },
  "judged": {
    "preferences": [...],
    "tools_and_stack": [...],
    "effective_strategies": [...],
    "mistakes_to_avoid": [...],
    "domain_insights": [...],
    "workflow_improvements": [...],
    "explicit_instructions": [...]
  }
}
```

---

## cmd_apply Output (CLAUDE.md snippet)

The `--apply` command generates a markdown file from the judged knowledge:

```markdown
# Learned Preferences (auto-generated by agents learn)

## Explicit Instructions
- Never auto-commit without asking
- Always use type hints in Python

## Preferred Tools & Stack
- **pytest** — test runner (preferred)
- **ruff** — linter (preferred)
- **pnpm** — package manager (preferred)

## Coding Style
- Prefers dataclasses over plain dicts
- Writes tests alongside implementation
- Uses functional style where possible

## Effective Strategies
- Start with failing test, then implement
- Read existing code before suggesting changes

## Mistakes to Avoid
- Don't suggest changes to files you haven't read
- Don't add unnecessary error handling

## Domain Knowledge
- Project uses FastAPI + SQLAlchemy pattern
- CI runs on GitHub Actions with pytest
```

---

## Verification

1. `python3 -m py_compile scripts/modules/learn.py` — syntax check
2. `python3 -m py_compile scripts/schemas.py` — syntax check
3. `ANTHROPIC_API_KEY=test python3 -c "from scripts.llm import LLM; l = LLM(); print(l.available())"` — LLM detection works
4. Run `agents learn` against real sessions and verify knowledge.json output
5. Run `agents learn --show` to verify display
6. Run `agents learn --apply` to verify CLAUDE.md generation
