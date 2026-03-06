#!/usr/bin/env python3
"""
Full-text search across all coding agent sessions.
Regex retrieval + LLM semantic reranking.
Called by: agents search <query>
Env vars: QUERY, CASE_SENSITIVE (true/false), MAX_RESULTS (int)
"""

import os
import sys
import re
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, GRAY, RED, BOLD, DIM, R,
                   time_ago, extract_text_from_record)
from llm import get_llm, LLMError, ANTHROPIC_SMALL, OPENAI_SMALL
from schemas import SearchRerankOutput

query = os.environ.get("QUERY", "")
case_sensitive = os.environ.get("CASE_SENSITIVE", "false") == "true"
max_results = int(os.environ.get("MAX_RESULTS", "20"))

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]
now = time.time()


def highlight(text, pattern, flags):
    """Highlight matching portions of text."""
    def replacer(m):
        return f"{RED}{BOLD}{m.group()}{R}"
    return re.sub(pattern, replacer, text, flags=flags)


def collect_results():
    """Run regex search across all sessions and collect results."""
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query, flags)
    except re.error:
        pattern = re.compile(re.escape(query), flags)

    results = []  # (mtime, display_path, agent_name, session_id, matches, first_snippet)

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue

        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue

            session_matches = []
            try:
                with open(fpath) as f:
                    for i, line in enumerate(f):
                        if len(session_matches) >= 3:
                            break
                        try:
                            d = json.loads(line)
                            role, text = extract_text_from_record(d, adapter.name)
                            if role and text and pattern.search(text):
                                clean = " ".join(text.split())
                                m = pattern.search(clean)
                                if m:
                                    start = max(0, m.start() - 40)
                                    end = min(len(clean), m.end() + 40)
                                    snippet = clean[start:end]
                                    if start > 0:
                                        snippet = "..." + snippet
                                    if end < len(clean):
                                        snippet = snippet + "..."
                                    session_matches.append(snippet)
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass
            except OSError:
                continue

            if session_matches:
                sid = os.path.basename(fpath).replace(".jsonl", "")
                if adapter.name == "codex":
                    try:
                        with open(fpath) as f:
                            first = json.loads(f.readline())
                            if first.get("type") == "session_meta":
                                sid = first.get("payload", {}).get("id", sid)
                    except (OSError, json.JSONDecodeError):
                        pass
                results.append((mtime, display_path, adapter.name, sid, session_matches))

    results.sort(key=lambda x: -x[0])
    return results, pattern, flags


def llm_rerank(llm, results):
    """Use LLM to semantically rerank search results."""
    # Build result list for the prompt
    rerank_results = []
    for mtime, display_path, aname, sid, matches in results:
        rerank_results.append({
            "agent": aname,
            "project": display_path,
            "score": 1.0,  # regex match is binary
            "preview": matches[0] if matches else "",
        })

    raw = llm.render_and_call_json("search_rerank", {
        "query": query,
        "results": rerank_results,
    }, model=ANTHROPIC_SMALL if llm.provider == "anthropic" else OPENAI_SMALL,
       max_tokens=512, temperature=0.2)
    return SearchRerankOutput.from_dict(raw)


def cmd_search():
    if not query:
        print("Usage: agents search <query>")
        raise SystemExit(1)

    results, pattern, flags = collect_results()

    print(f"{BOLD}{CYAN}Search: {WHITE}{query}{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    if not results:
        print(f"{GRAY}No matches found.{R}")
        raise SystemExit(0)

    # Try LLM semantic reranking on top results
    llm = get_llm()
    reranked = None
    if llm.available() and len(results) > 1:
        # Only rerank top candidates (limit to 15 for cost)
        candidates = results[:15]
        try:
            reranked = llm_rerank(llm, candidates)
        except LLMError:
            pass  # Fall back to keyword ordering

    # Apply reranked ordering if available
    display_order = list(range(len(results)))
    if reranked and reranked.ranked:
        # Reranked indices are 1-based from the prompt
        new_order = []
        seen = set()
        for idx in reranked.ranked:
            i = idx - 1  # Convert to 0-based
            if 0 <= i < len(results) and i not in seen:
                new_order.append(i)
                seen.add(i)
        # Append any remaining results not in the reranked list
        for i in range(len(results)):
            if i not in seen:
                new_order.append(i)
        display_order = new_order

    if reranked and reranked.reasoning:
        print(f"  {DIM}Reranked: {reranked.reasoning}{R}")
        print()

    shown = 0
    for i in display_order:
        if shown >= max_results:
            break
        mtime, display_path, aname, sid, matches = results[i]
        shown += 1

        a_color = CYAN if aname == "claude" else GREEN
        age_str = time_ago(mtime)
        age_color = GREEN if (now - mtime) < 3600 else (YELLOW if (now - mtime) < 86400 else GRAY)

        print(f"  {a_color}[{aname}]{R} {YELLOW}{display_path}{R}  {age_color}{age_str}{R}")
        print(f"  {DIM}session {MAGENTA}{sid[:8]}{R}")
        for snippet in matches[:2]:
            highlighted = highlight(snippet, pattern, flags)
            print(f"    {GRAY}\"{R}{highlighted}{GRAY}\"{R}")
        print()

    remaining = len(results) - shown
    print(f"{DIM}{'─' * 52}{R}")
    print(f"{BOLD}{shown}{R} match{'es' if shown != 1 else ''} across {len(set(r[1] for r in results))} project{'s' if len(set(r[1] for r in results)) != 1 else ''}", end="")
    if remaining > 0:
        print(f" {DIM}({remaining} more, use --max N){R}")
    else:
        print()

    if llm.available() and llm.total_calls > 0:
        llm.print_cost_summary()


if __name__ == "__main__":
    cmd_search()
