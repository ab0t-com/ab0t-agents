#!/usr/bin/env python3
"""
Input/output schemas for LLM-powered features.
Dataclasses define what goes into prompts and what comes out.
Used for validation and type safety across modules.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ── Compact ────────────────────────────────────────────────

@dataclass
class CompactInput:
    """Input for compact_summarize prompt."""
    messages: List[Dict[str, str]]  # [{"role": "user"|"assistant", "text": "..."}]
    segment_index: int = 0
    total_segments: int = 1


@dataclass
class CompactOutput:
    """Output from compact_summarize prompt."""
    summary: str = ""
    decisions: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    errors_resolved: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    status: str = "in_progress"  # in_progress, completed, blocked, exploring

    @classmethod
    def from_dict(cls, d):
        return cls(
            summary=d.get("summary", ""),
            decisions=d.get("decisions", []),
            artifacts=d.get("artifacts", []),
            commands=d.get("commands", []),
            errors_resolved=d.get("errors_resolved", []),
            constraints=d.get("constraints", []),
            status=d.get("status", "in_progress"),
        )


# ── Blend ──────────────────────────────────────────────────

@dataclass
class BlendSessionInfo:
    """Info about one session being blended."""
    agent: str = ""
    time_ago: str = ""
    first_message: str = ""
    summary: str = ""
    files: List[str] = field(default_factory=list)


@dataclass
class BlendInput:
    """Input for blend_synthesize prompt."""
    project: str = ""
    sessions: List[BlendSessionInfo] = field(default_factory=list)


@dataclass
class BlendOutput:
    """Output from blend_synthesize prompt."""
    synthesized_context: str = ""
    active_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    recommended_next_steps: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            synthesized_context=d.get("synthesized_context", ""),
            active_tasks=d.get("active_tasks", []),
            completed_tasks=d.get("completed_tasks", []),
            key_files=d.get("key_files", []),
            decisions=d.get("decisions", []),
            blockers=d.get("blockers", []),
            recommended_next_steps=d.get("recommended_next_steps", []),
        )


# ── Learn: Stage 1 — Session Digest ───────────────────────

@dataclass
class DigestOutput:
    """Output from learn_digest prompt."""
    goal: str = ""
    approach: str = ""
    tools_and_libs: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    problems_encountered: List[str] = field(default_factory=list)
    outcome: str = "exploratory"  # completed|partial|failed|exploratory
    key_commands: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            goal=d.get("goal", ""),
            approach=d.get("approach", ""),
            tools_and_libs=d.get("tools_and_libs", []),
            files_modified=d.get("files_modified", []),
            problems_encountered=d.get("problems_encountered", []),
            outcome=d.get("outcome", "exploratory"),
            key_commands=d.get("key_commands", []),
            languages=d.get("languages", []),
        )


# ── Learn: Stage 2 — Entity Extraction ───────────────────

@dataclass
class ExtractedPreference:
    entity: str = ""
    confidence: str = "low"  # high|medium|low
    category: str = "workflow"  # style|tooling|workflow|testing|architecture
    evidence: str = ""


@dataclass
class ExtractedTool:
    name: str = ""
    role: str = ""
    sentiment: str = "used"  # preferred|used|mentioned|rejected


@dataclass
class ExtractedPattern:
    pattern: str = ""
    frequency: str = "once"  # once|recurring


@dataclass
class ExtractedInstruction:
    instruction: str = ""
    scope: str = "project"  # global|project


@dataclass
class EntityOutput:
    """Output from learn_entities prompt."""
    preferences: List[ExtractedPreference] = field(default_factory=list)
    tools_and_stack: List[ExtractedTool] = field(default_factory=list)
    coding_patterns: List[ExtractedPattern] = field(default_factory=list)
    explicit_instructions: List[ExtractedInstruction] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            preferences=[ExtractedPreference(**p) for p in d.get("preferences", [])],
            tools_and_stack=[ExtractedTool(**t) for t in d.get("tools_and_stack", [])],
            coding_patterns=[ExtractedPattern(**p) for p in d.get("coding_patterns", [])],
            explicit_instructions=[ExtractedInstruction(**i) for i in d.get("explicit_instructions", [])],
        )


# ── Learn: Stage 3 — Meta-Cognitive Reflection ───────────

@dataclass
class EffectiveStrategy:
    strategy: str = ""
    why: str = ""
    reusable: bool = True


@dataclass
class MistakeCorrection:
    mistake: str = ""
    correction: str = ""
    prevention: str = ""


@dataclass
class UserFriction:
    friction: str = ""
    improvement: str = ""


@dataclass
class DomainInsight:
    insight: str = ""
    applies_to: str = "general"


@dataclass
class WorkflowImprovement:
    current: str = ""
    suggested: str = ""
    impact: str = "medium"  # high|medium|low


@dataclass
class ReflectionOutput:
    """Output from learn_reflect prompt."""
    effective_strategies: List[EffectiveStrategy] = field(default_factory=list)
    mistakes_and_corrections: List[MistakeCorrection] = field(default_factory=list)
    user_friction: List[UserFriction] = field(default_factory=list)
    domain_insights: List[DomainInsight] = field(default_factory=list)
    workflow_improvements: List[WorkflowImprovement] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            effective_strategies=[EffectiveStrategy(**s) for s in d.get("effective_strategies", [])],
            mistakes_and_corrections=[MistakeCorrection(**m) for m in d.get("mistakes_and_corrections", [])],
            user_friction=[UserFriction(**f) for f in d.get("user_friction", [])],
            domain_insights=[DomainInsight(**i) for i in d.get("domain_insights", [])],
            workflow_improvements=[WorkflowImprovement(**w) for w in d.get("workflow_improvements", [])],
        )


# ── Learn: Stage 4 — Knowledge Judge ─────────────────────

@dataclass
class JudgedPreference:
    text: str = ""
    confidence: str = "low"
    category: str = "workflow"
    evidence_count: int = 1
    last_seen: str = ""


@dataclass
class JudgedTool:
    name: str = ""
    role: str = ""
    sentiment: str = "used"
    frequency: int = 1


@dataclass
class JudgedStrategy:
    strategy: str = ""
    why: str = ""
    times_seen: int = 1


@dataclass
class JudgedMistake:
    mistake: str = ""
    prevention: str = ""
    confidence: str = "low"


@dataclass
class JudgedInsight:
    insight: str = ""
    applies_to: str = "general"
    confidence: str = "low"


@dataclass
class JudgedImprovement:
    suggestion: str = ""
    impact: str = "medium"
    evidence_count: int = 1


@dataclass
class JudgedInstruction:
    instruction: str = ""
    scope: str = "project"


@dataclass
class KnowledgeBase:
    """Output from learn_judge prompt — the consolidated knowledge."""
    preferences: List[JudgedPreference] = field(default_factory=list)
    tools_and_stack: List[JudgedTool] = field(default_factory=list)
    effective_strategies: List[JudgedStrategy] = field(default_factory=list)
    mistakes_to_avoid: List[JudgedMistake] = field(default_factory=list)
    domain_insights: List[JudgedInsight] = field(default_factory=list)
    workflow_improvements: List[JudgedImprovement] = field(default_factory=list)
    explicit_instructions: List[JudgedInstruction] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            preferences=[JudgedPreference(**p) for p in d.get("preferences", [])],
            tools_and_stack=[JudgedTool(**t) for t in d.get("tools_and_stack", [])],
            effective_strategies=[JudgedStrategy(**s) for s in d.get("effective_strategies", [])],
            mistakes_to_avoid=[JudgedMistake(**m) for m in d.get("mistakes_to_avoid", [])],
            domain_insights=[JudgedInsight(**i) for i in d.get("domain_insights", [])],
            workflow_improvements=[JudgedImprovement(**w) for w in d.get("workflow_improvements", [])],
            explicit_instructions=[JudgedInstruction(**i) for i in d.get("explicit_instructions", [])],
        )


# ── Bridge ─────────────────────────────────────────────────

@dataclass
class BridgeInput:
    """Input for bridge_handoff prompt."""
    source_agent: str = ""
    target_agent: str = ""
    project: str = ""
    current_task: str = ""
    git_branch: str = ""
    decisions: List[str] = field(default_factory=list)
    files_modified: Dict[str, int] = field(default_factory=dict)
    errors_resolved: List[Dict[str, str]] = field(default_factory=list)
    key_messages: List[str] = field(default_factory=list)


@dataclass
class BridgeOutput:
    """Output from bridge_handoff prompt."""
    handoff_summary: str = ""
    current_state: str = ""
    next_steps: List[str] = field(default_factory=list)
    important_context: List[str] = field(default_factory=list)
    files_to_review: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            handoff_summary=d.get("handoff_summary", ""),
            current_state=d.get("current_state", ""),
            next_steps=d.get("next_steps", []),
            important_context=d.get("important_context", []),
            files_to_review=d.get("files_to_review", []),
            warnings=d.get("warnings", []),
        )


# ── Topics ─────────────────────────────────────────────────

@dataclass
class TopicItem:
    label: str = ""
    category: str = "feature"  # feature|bugfix|refactor|infrastructure|docs|testing|exploration|devops


@dataclass
class TopicExtractOutput:
    """Output from topics_extract prompt (per-session)."""
    topics: List[TopicItem] = field(default_factory=list)
    technologies: List[str] = field(default_factory=list)
    domain: str = "general"

    @classmethod
    def from_dict(cls, d):
        return cls(
            topics=[TopicItem(**t) for t in d.get("topics", [])],
            technologies=d.get("technologies", []),
            domain=d.get("domain", "general"),
        )


@dataclass
class ConsolidatedTopic:
    label: str = ""
    description: str = ""
    category: str = "feature"
    session_count: int = 1
    technologies: List[str] = field(default_factory=list)


@dataclass
class TopicConsolidateOutput:
    """Output from topics_label prompt (consolidation)."""
    topics: List[ConsolidatedTopic] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            topics=[ConsolidatedTopic(**t) for t in d.get("topics", [])],
        )


# ── RAG ────────────────────────────────────────────────────

@dataclass
class RAGChunk:
    agent: str = ""
    project: str = ""
    score: float = 0.0
    preview_user: str = ""
    preview_asst: str = ""


@dataclass
class RAGInput:
    """Input for rag_answer prompt."""
    query: str = ""
    chunks: List[RAGChunk] = field(default_factory=list)


@dataclass
class RAGOutput:
    """Output from rag_answer prompt."""
    answer: str = ""
    confidence: str = "low"
    sources: List[int] = field(default_factory=list)
    related_queries: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        return cls(
            answer=d.get("answer", ""),
            confidence=d.get("confidence", "low"),
            sources=d.get("sources", []),
            related_queries=d.get("related_queries", []),
        )


# ── Search Rerank ──────────────────────────────────────────

@dataclass
class SearchResult:
    agent: str = ""
    project: str = ""
    score: float = 0.0
    preview: str = ""


@dataclass
class SearchRerankInput:
    """Input for search_rerank prompt."""
    query: str = ""
    results: List[SearchResult] = field(default_factory=list)


@dataclass
class SearchRerankOutput:
    """Output from search_rerank prompt."""
    ranked: List[int] = field(default_factory=list)
    reasoning: str = ""

    @classmethod
    def from_dict(cls, d):
        return cls(
            ranked=d.get("ranked", []),
            reasoning=d.get("reasoning", ""),
        )
