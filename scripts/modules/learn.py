#!/usr/bin/env python3
"""
Self-learning: 4-stage LLM pipeline that extracts knowledge from session history.

Stage 1 — Digest:     Understand what happened in each session (Haiku)
Stage 2 — Entities:   NER-style extraction of preferences, tools, patterns (Haiku)
Stage 3 — Reflect:    Meta-cognitive self-reflection on performance (Sonnet)
Stage 4 — Judge:      LLM-as-judge to merge/deduplicate/score knowledge (Sonnet)

Called by: agents learn [--show] [--project PATH] [--apply]
Env vars: ACTION (scan/show/apply), PROJECT (path or "all")
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR, extract_text_from_record)
from llm import get_llm, LLMError, ANTHROPIC_SMALL, ANTHROPIC_LARGE, OPENAI_SMALL, OPENAI_LARGE
from schemas import (DigestOutput, EntityOutput, ReflectionOutput, KnowledgeBase)

KNOWLEDGE_DIR = os.path.join(CACHE_DIR, "knowledge")
KNOWLEDGE_FILE = os.path.join(KNOWLEDGE_DIR, "knowledge.json")

action = os.environ.get("ACTION", "scan")
project_filter = os.environ.get("PROJECT", "all")

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]
available = [a for a in ALL_ADAPTERS if a.is_available()]


# ── Knowledge persistence ─────────────────────────────────

def load_knowledge():
    try:
        with open(KNOWLEDGE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "scanned_sessions": [],
            "last_scan": None,
            "session_findings": {},
            "judged": {},
        }


def save_knowledge(k):
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    with open(KNOWLEDGE_FILE, "w") as f:
        json.dump(k, f, indent=2)


# ── Message extraction ────────────────────────────────────

def extract_messages(fpath, agent_name):
    """Read JSONL session file, return list of {role, text} dicts."""
    messages = []
    try:
        with open(fpath) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    role, text = extract_text_from_record(record, agent_name)
                    if role and text and role in ("user", "assistant"):
                        messages.append({"role": role, "text": text})
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass
    return messages


def batch_messages(messages, batch_size=40, overlap=5):
    """Split messages into overlapping windows for LLM context limits."""
    if len(messages) <= batch_size:
        return [messages]
    batches = []
    start = 0
    while start < len(messages):
        end = min(start + batch_size, len(messages))
        batches.append(messages[start:end])
        start = end - overlap
        if start + overlap >= len(messages):
            break
    return batches


def truncate_messages(messages, max_chars=300):
    """Truncate message text for prompt inclusion."""
    return [{"role": m["role"], "text": m["text"][:max_chars]} for m in messages]


# ── Stage 1: Session Digest ──────────────────────────────

def stage_digest(llm, messages, agent, project):
    """Understand what happened in the session."""
    truncated = truncate_messages(messages)
    raw = llm.render_and_call_json("learn_digest", {
        "agent": agent,
        "project": project,
        "messages": truncated,
    }, model=_small_model(llm), max_tokens=1024, temperature=0.2)
    return DigestOutput.from_dict(raw)


def merge_digests(digests):
    """Merge multiple batch digests into one combined digest dict."""
    if len(digests) == 1:
        return _digest_to_dict(digests[0])

    merged = {
        "goal": digests[0].goal,
        "approach": digests[0].approach,
        "tools_and_libs": [],
        "files_modified": [],
        "problems_encountered": [],
        "outcome": digests[-1].outcome,
        "key_commands": [],
        "languages": [],
    }
    seen_tools = set()
    seen_files = set()
    seen_langs = set()
    for d in digests:
        for t in d.tools_and_libs:
            if t.lower() not in seen_tools:
                seen_tools.add(t.lower())
                merged["tools_and_libs"].append(t)
        for f in d.files_modified:
            if f not in seen_files:
                seen_files.add(f)
                merged["files_modified"].append(f)
        for lang in d.languages:
            if lang.lower() not in seen_langs:
                seen_langs.add(lang.lower())
                merged["languages"].append(lang)
        merged["problems_encountered"].extend(d.problems_encountered)
        merged["key_commands"].extend(d.key_commands)
        # Use the latest non-empty goal/approach
        if d.goal and not merged["goal"]:
            merged["goal"] = d.goal
        if d.approach and not merged["approach"]:
            merged["approach"] = d.approach
    return merged


def _digest_to_dict(d):
    """Convert DigestOutput dataclass to plain dict."""
    return {
        "goal": d.goal,
        "approach": d.approach,
        "tools_and_libs": d.tools_and_libs,
        "files_modified": d.files_modified,
        "problems_encountered": d.problems_encountered,
        "outcome": d.outcome,
        "key_commands": d.key_commands,
        "languages": d.languages,
    }


# ── Stage 2: Entity Extraction ───────────────────────────

def stage_entities(llm, digest, user_messages, agent, project):
    """NER-style extraction of preferences, tools, patterns, instructions."""
    raw = llm.render_and_call_json("learn_entities", {
        "digest": digest,
        "user_messages": user_messages,
        "agent": agent,
        "project": project,
    }, model=_small_model(llm), max_tokens=1024, temperature=0.2)
    return EntityOutput.from_dict(raw)


# ── Stage 3: Reflection ──────────────────────────────────

def stage_reflect(llm, digest, entities, problems, project):
    """Meta-cognitive self-reflection on the session."""
    # Convert entities to dict for template
    entities_dict = {
        "preferences": [{"entity": p.entity, "confidence": p.confidence,
                         "category": p.category} for p in entities.preferences],
        "tools_and_stack": [{"name": t.name, "role": t.role,
                             "sentiment": t.sentiment} for t in entities.tools_and_stack],
        "coding_patterns": [{"pattern": p.pattern} for p in entities.coding_patterns],
        "explicit_instructions": [{"instruction": i.instruction} for i in entities.explicit_instructions],
    }
    raw = llm.render_and_call_json("learn_reflect", {
        "digest": digest,
        "entities": entities_dict,
        "problems": problems,
        "project": project,
    }, model=_large_model(llm), max_tokens=1536, temperature=0.3)
    return ReflectionOutput.from_dict(raw)


# ── Stage 4: Knowledge Judge ─────────────────────────────

def aggregate_findings(all_findings):
    """Aggregate per-session findings into a single new_findings dict for the judge."""
    agg = {
        "preferences": [],
        "tools_and_stack": [],
        "coding_patterns": [],
        "explicit_instructions": [],
        "effective_strategies": [],
        "mistakes_and_corrections": [],
        "user_friction": [],
        "domain_insights": [],
        "workflow_improvements": [],
    }
    for f in all_findings:
        ent = f["entities"]
        ref = f["reflection"]
        proj = f["project"]

        for p in ent.preferences:
            agg["preferences"].append({
                "entity": p.entity, "confidence": p.confidence,
                "category": p.category, "evidence": p.evidence, "project": proj,
            })
        for t in ent.tools_and_stack:
            agg["tools_and_stack"].append({
                "name": t.name, "role": t.role, "sentiment": t.sentiment, "project": proj,
            })
        for p in ent.coding_patterns:
            agg["coding_patterns"].append({
                "pattern": p.pattern, "frequency": p.frequency, "project": proj,
            })
        for i in ent.explicit_instructions:
            agg["explicit_instructions"].append({
                "instruction": i.instruction, "scope": i.scope, "project": proj,
            })
        for s in ref.effective_strategies:
            agg["effective_strategies"].append({
                "strategy": s.strategy, "why": s.why, "reusable": s.reusable,
            })
        for m in ref.mistakes_and_corrections:
            agg["mistakes_and_corrections"].append({
                "mistake": m.mistake, "correction": m.correction, "prevention": m.prevention,
            })
        for uf in ref.user_friction:
            agg["user_friction"].append({
                "friction": uf.friction, "improvement": uf.improvement,
            })
        for di in ref.domain_insights:
            agg["domain_insights"].append({
                "insight": di.insight, "applies_to": di.applies_to,
            })
        for wi in ref.workflow_improvements:
            agg["workflow_improvements"].append({
                "current": wi.current, "suggested": wi.suggested, "impact": wi.impact,
            })
    return agg


def stage_judge(llm, existing, new_findings):
    """LLM-as-judge: merge new findings into existing knowledge."""
    raw = llm.render_and_call_json("learn_judge", {
        "existing": existing,
        "new_findings": new_findings,
    }, model=_large_model(llm), max_tokens=3000, temperature=0.2)
    return KnowledgeBase.from_dict(raw)


def _kb_to_dict(kb):
    """Convert KnowledgeBase dataclass to plain dict for JSON storage."""
    return {
        "preferences": [{"text": p.text, "confidence": p.confidence, "category": p.category,
                         "evidence_count": p.evidence_count, "last_seen": p.last_seen}
                        for p in kb.preferences],
        "tools_and_stack": [{"name": t.name, "role": t.role, "sentiment": t.sentiment,
                             "frequency": t.frequency} for t in kb.tools_and_stack],
        "effective_strategies": [{"strategy": s.strategy, "why": s.why, "times_seen": s.times_seen}
                                for s in kb.effective_strategies],
        "mistakes_to_avoid": [{"mistake": m.mistake, "prevention": m.prevention,
                               "confidence": m.confidence} for m in kb.mistakes_to_avoid],
        "domain_insights": [{"insight": i.insight, "applies_to": i.applies_to,
                             "confidence": i.confidence} for i in kb.domain_insights],
        "workflow_improvements": [{"suggestion": w.suggestion, "impact": w.impact,
                                   "evidence_count": w.evidence_count}
                                  for w in kb.workflow_improvements],
        "explicit_instructions": [{"instruction": i.instruction, "scope": i.scope}
                                  for i in kb.explicit_instructions],
    }


# ── Model selection helpers ───────────────────────────────

def _small_model(llm):
    """Cheap/fast model for digest and entity extraction."""
    return ANTHROPIC_SMALL if llm.provider == "anthropic" else OPENAI_SMALL


def _large_model(llm):
    """Capable model for reflection and judging."""
    return ANTHROPIC_LARGE if llm.provider == "anthropic" else OPENAI_LARGE


# ── Per-session processing ────────────────────────────────

def process_session(llm, fpath, agent_name, project):
    """Run stages 1-3 on a single session. Return raw findings or None."""
    messages = extract_messages(fpath, agent_name)
    if len(messages) < 3:
        return None

    # Stage 1: Digest
    batches = batch_messages(messages)
    digests = []
    for batch in batches:
        try:
            d = stage_digest(llm, batch, agent_name, project)
            digests.append(d)
        except LLMError as e:
            print(f"    {RED}Digest failed: {e}{R}")
            return None

    digest = merge_digests(digests)

    # Stage 2: Entity extraction
    user_messages = [m["text"][:200] for m in messages if m["role"] == "user"][:15]
    try:
        entities = stage_entities(llm, digest, user_messages, agent_name, project)
    except LLMError as e:
        print(f"    {RED}Entity extraction failed: {e}{R}")
        return None

    # Stage 3: Reflection
    try:
        reflection = stage_reflect(llm, digest, entities,
                                   digest.get("problems_encountered", []), project)
    except LLMError as e:
        print(f"    {RED}Reflection failed: {e}{R}")
        return None

    return {
        "digest": digest,
        "entities": entities,
        "reflection": reflection,
        "project": project,
        "agent": agent_name,
    }


# ── Commands ──────────────────────────────────────────────

def cmd_scan():
    """Scan sessions through the 4-stage LLM pipeline."""
    llm = get_llm()
    if not llm.available():
        print(f"{RED}No LLM API key found.{R}")
        print(f"{DIM}Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable self-learning.{R}")
        raise SystemExit(1)

    knowledge = load_knowledge()
    scanned = set(knowledge.get("scanned_sessions", []))

    print(f"{BOLD}{CYAN}Self-Learning Pipeline{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"  {DIM}Provider: {llm.provider}{R}")
    print()

    # Discover new sessions
    all_findings = []
    new_count = 0
    skipped = 0

    for adapter in available:
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue
            if fpath in scanned:
                continue
            if project_filter != "all" and not display_path.startswith(project_filter):
                continue

            new_count += 1
            a_color = CYAN if adapter.name == "claude" else GREEN
            sid = os.path.basename(fpath).replace(".jsonl", "")[:8]
            short_project = os.path.basename(display_path) if display_path else "?"

            print(f"  {a_color}[{adapter.name}]{R} {WHITE}{sid}{R} {DIM}{short_project}{R}")

            # Stages 1-3 per session
            print(f"    {DIM}Digesting...{R}", end="", flush=True)
            findings = process_session(llm, fpath, adapter.name, display_path)

            if findings:
                all_findings.append(findings)
                ent = findings["entities"]
                ref = findings["reflection"]
                n_items = (len(ent.preferences) + len(ent.tools_and_stack) +
                           len(ent.coding_patterns) + len(ent.explicit_instructions) +
                           len(ref.effective_strategies) + len(ref.mistakes_and_corrections) +
                           len(ref.domain_insights))
                print(f"\r    {GREEN}Extracted {n_items} insights{R}              ")
            else:
                print(f"\r    {GRAY}Skipped (too short or error){R}              ")
                skipped += 1

            scanned.add(fpath)

    if new_count == 0:
        print(f"  {GRAY}No new sessions to scan.{R}")
        print(f"  {DIM}{len(scanned)} sessions already scanned.{R}")
        save_knowledge(knowledge)
        return

    # Stage 4: Knowledge Judge (once, merges everything)
    if all_findings:
        print()
        print(f"  {DIM}Judging and consolidating knowledge...{R}", flush=True)

        new_findings = aggregate_findings(all_findings)
        existing = knowledge.get("judged", {})

        try:
            judged = stage_judge(llm, existing, new_findings)
            knowledge["judged"] = _kb_to_dict(judged)
        except LLMError as e:
            print(f"  {RED}Judge stage failed: {e}{R}")
            print(f"  {DIM}Session findings saved, but knowledge not consolidated.{R}")

        # Store per-session findings for reference
        findings_store = knowledge.get("session_findings", {})
        for f in all_findings:
            sid = os.path.basename(f.get("project", "unknown"))
            findings_store[f"{f['agent']}:{sid}"] = {
                "digest": f["digest"],
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        knowledge["session_findings"] = findings_store

    knowledge["scanned_sessions"] = list(scanned)
    knowledge["last_scan"] = datetime.utcnow().isoformat() + "Z"
    save_knowledge(knowledge)

    # Summary
    print()
    print(f"{GREEN}{BOLD}Learning complete.{R}")
    print(f"  {WHITE}Sessions processed:{R} {len(all_findings)}/{new_count}")
    if skipped:
        print(f"  {WHITE}Skipped:{R}            {skipped}")

    judged = knowledge.get("judged", {})
    if judged:
        n_prefs = len(judged.get("preferences", []))
        n_tools = len(judged.get("tools_and_stack", []))
        n_strats = len(judged.get("effective_strategies", []))
        n_mistakes = len(judged.get("mistakes_to_avoid", []))
        n_insights = len(judged.get("domain_insights", []))
        n_instrs = len(judged.get("explicit_instructions", []))
        print(f"  {WHITE}Knowledge base:{R}     {n_prefs} preferences, {n_tools} tools, "
              f"{n_strats} strategies")
        print(f"  {WHITE}                    {n_mistakes} mistakes, {n_insights} insights, "
              f"{n_instrs} instructions{R}")

    print(f"  {WHITE}Total scanned:{R}     {len(scanned)} sessions")
    print()
    llm.print_cost_summary()


def cmd_show():
    """Display the consolidated knowledge base."""
    knowledge = load_knowledge()
    judged = knowledge.get("judged", {})

    print(f"{BOLD}{CYAN}Knowledge Base{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    scanned = knowledge.get("scanned_sessions", [])
    last_scan = knowledge.get("last_scan", "never")
    print(f"  {WHITE}Sessions scanned:{R} {len(scanned)}")
    print(f"  {WHITE}Last scan:{R}        {last_scan}")
    print()

    if not judged:
        print(f"  {GRAY}Knowledge base is empty. Run 'agents learn' to scan sessions.{R}")
        return

    # Explicit instructions (highest priority)
    instructions = judged.get("explicit_instructions", [])
    if instructions:
        print(f"{BOLD}  Explicit Instructions:{R}")
        for i in instructions:
            scope_tag = f" {DIM}({i['scope']}){R}" if i.get("scope") == "project" else ""
            print(f"    {RED}{BOLD}!{R} {WHITE}{i['instruction']}{R}{scope_tag}")
        print()

    # Preferences
    prefs = judged.get("preferences", [])
    if prefs:
        print(f"{BOLD}  Preferences ({len(prefs)}):{R}")
        for p in sorted(prefs, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("confidence", "low"), 2)):
            conf = p.get("confidence", "low")
            conf_color = GREEN if conf == "high" else YELLOW if conf == "medium" else GRAY
            cat = p.get("category", "")
            print(f"    {conf_color}[{conf}]{R} {WHITE}{p['text']}{R} {DIM}({cat}){R}")
        print()

    # Tools & stack
    tools = judged.get("tools_and_stack", [])
    if tools:
        print(f"{BOLD}  Tools & Stack ({len(tools)}):{R}")
        for t in sorted(tools, key=lambda x: -x.get("frequency", 0)):
            sent = t.get("sentiment", "used")
            sent_color = GREEN if sent == "preferred" else GRAY if sent == "mentioned" else RED if sent == "rejected" else WHITE
            freq = t.get("frequency", 0)
            bar = "█" * min(15, freq)
            print(f"    {sent_color}{t['name']:20s}{R} {DIM}{bar}{R} {DIM}×{freq} ({sent}){R}")
        print()

    # Effective strategies
    strats = judged.get("effective_strategies", [])
    if strats:
        print(f"{BOLD}  Effective Strategies ({len(strats)}):{R}")
        for s in strats:
            times = s.get("times_seen", 1)
            print(f"    {GREEN}✓{R} {WHITE}{s['strategy']}{R}")
            print(f"      {DIM}{s['why']}{R}")
        print()

    # Mistakes to avoid
    mistakes = judged.get("mistakes_to_avoid", [])
    if mistakes:
        print(f"{BOLD}  Mistakes to Avoid ({len(mistakes)}):{R}")
        for m in mistakes:
            conf = m.get("confidence", "low")
            conf_color = RED if conf == "high" else YELLOW if conf == "medium" else GRAY
            print(f"    {conf_color}✗{R} {WHITE}{m['mistake']}{R}")
            print(f"      {DIM}Prevention: {m['prevention']}{R}")
        print()

    # Domain insights
    insights = judged.get("domain_insights", [])
    if insights:
        print(f"{BOLD}  Domain Insights ({len(insights)}):{R}")
        for i in insights:
            print(f"    {MAGENTA}›{R} {WHITE}{i['insight']}{R} {DIM}({i.get('applies_to', 'general')}){R}")
        print()

    # Workflow improvements
    improvements = judged.get("workflow_improvements", [])
    if improvements:
        print(f"{BOLD}  Workflow Improvements:{R}")
        for w in improvements:
            impact = w.get("impact", "medium")
            impact_color = RED if impact == "high" else YELLOW if impact == "medium" else GRAY
            print(f"    {impact_color}[{impact}]{R} {WHITE}{w['suggestion']}{R}")
        print()


def cmd_apply():
    """Generate a CLAUDE.md snippet from consolidated knowledge."""
    knowledge = load_knowledge()
    judged = knowledge.get("judged", {})

    if not judged:
        print(f"{GRAY}Knowledge base is empty. Run 'agents learn' first.{R}")
        raise SystemExit(1)

    lines = []
    lines.append("# Learned Preferences")
    lines.append("")
    lines.append("Auto-generated by `agents learn --apply`. Review before using.")
    lines.append("")

    # Explicit instructions first (highest signal)
    instructions = judged.get("explicit_instructions", [])
    if instructions:
        lines.append("## Explicit Instructions")
        for i in instructions:
            lines.append(f"- {i['instruction']}")
        lines.append("")

    # Preferred tools
    tools = judged.get("tools_and_stack", [])
    preferred = [t for t in tools if t.get("sentiment") == "preferred"]
    used = [t for t in tools if t.get("sentiment") == "used" and t.get("frequency", 0) >= 3]
    rejected = [t for t in tools if t.get("sentiment") == "rejected"]
    if preferred or used:
        lines.append("## Preferred Tools & Stack")
        for t in preferred:
            lines.append(f"- **{t['name']}** — {t.get('role', 'preferred')}")
        for t in used:
            lines.append(f"- {t['name']} — {t.get('role', 'frequently used')}")
        lines.append("")
    if rejected:
        lines.append("## Rejected Tools")
        for t in rejected:
            lines.append(f"- ~~{t['name']}~~ — {t.get('role', 'rejected')}")
        lines.append("")

    # High/medium confidence preferences
    prefs = judged.get("preferences", [])
    by_cat = {}
    for p in prefs:
        if p.get("confidence") in ("high", "medium"):
            cat = p.get("category", "general")
            by_cat.setdefault(cat, []).append(p)
    for cat in ("style", "workflow", "testing", "architecture", "tooling"):
        items = by_cat.get(cat, [])
        if items:
            lines.append(f"## {cat.title()}")
            for p in items:
                lines.append(f"- {p['text']}")
            lines.append("")

    # Effective strategies
    strats = judged.get("effective_strategies", [])
    if strats:
        lines.append("## Effective Strategies")
        for s in strats:
            lines.append(f"- {s['strategy']}")
        lines.append("")

    # Mistakes to avoid
    mistakes = judged.get("mistakes_to_avoid", [])
    high_conf = [m for m in mistakes if m.get("confidence") in ("high", "medium")]
    if high_conf:
        lines.append("## Mistakes to Avoid")
        for m in high_conf:
            lines.append(f"- {m['prevention']}")
        lines.append("")

    # Domain insights
    insights = judged.get("domain_insights", [])
    if insights:
        lines.append("## Domain Knowledge")
        for i in insights:
            lines.append(f"- {i['insight']}")
        lines.append("")

    result = "\n".join(lines)
    print(result)
    print()
    print(f"{DIM}Paste the above into your CLAUDE.md or save with:{R}")
    print(f"{DIM}  agents learn --apply > learned-preferences.md{R}")


if __name__ == "__main__":
    if action == "show":
        cmd_show()
    elif action == "apply":
        cmd_apply()
    else:
        cmd_scan()
