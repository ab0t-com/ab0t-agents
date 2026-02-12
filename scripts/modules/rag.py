#!/usr/bin/env python3
"""
RAG - Retrieval-Augmented Generation over session history.
BM25-based keyword retrieval with no external dependencies.
Called by: agents rag <query> | agents rag --build
Env vars: ACTION (query/build/status), QUERY, MAX_RESULTS (int)
"""

import os
import sys
import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter

WHITE = "\033[1;37m"
CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
MAGENTA = "\033[0;35m"
BLUE = "\033[0;34m"
GRAY = "\033[0;90m"
RED = "\033[0;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
R = "\033[0m"

CACHE_DIR = os.path.expanduser("~/.ab0t/.agents")
INDEX_DIR = os.path.join(CACHE_DIR, "rag")
INDEX_FILE = os.path.join(INDEX_DIR, "index.json")
DOCS_FILE = os.path.join(INDEX_DIR, "docs.json")

action = os.environ.get("ACTION", "query")
query = os.environ.get("QUERY", "")
max_results = int(os.environ.get("MAX_RESULTS", "5"))

ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter()]

# BM25 parameters
K1 = 1.5
B = 0.75

# Stop words
STOP_WORDS = set("""
a an the is was were be been being have has had do does did will would shall
should may might can could am are it its this that these those i me my mine
we our us you your he him his she her they them their what which who whom
how when where why all each every both few many some any no not only very
just also than too so if or and but for with from by at in on to of as
""".split())


def tokenize(text):
    """Tokenize text into searchable terms."""
    tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{1,}', text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def extract_chunks(fpath, agent_name):
    """Extract text chunks from a session file.
    Each chunk is a user/assistant message exchange."""
    chunks = []
    current_exchange = {"user": "", "assistant": "", "line": 0}

    try:
        with open(fpath) as f:
            for line_num, line in enumerate(f):
                try:
                    d = json.loads(line)
                    text = ""
                    role = ""

                    if agent_name == "claude":
                        if d.get("type") == "user":
                            content = d.get("message", {}).get("content", "")
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                text = " ".join(
                                    item.get("text", "")
                                    for item in content
                                    if isinstance(item, dict) and item.get("type") == "text"
                                )
                            role = "user"
                        elif d.get("type") == "assistant":
                            content = d.get("message", {}).get("content", [])
                            if isinstance(content, list):
                                parts = []
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        parts.append(item.get("text", ""))
                                text = " ".join(parts)
                            role = "assistant"

                    elif agent_name == "codex":
                        if d.get("type") == "response_item":
                            p = d.get("payload", d.get("item", {}))
                            role = p.get("role", "")
                            content = p.get("content", [])
                            if isinstance(content, list):
                                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))

                    if text and role == "user":
                        # Start new exchange
                        if current_exchange["user"] or current_exchange["assistant"]:
                            combined = current_exchange["user"] + " " + current_exchange["assistant"]
                            if combined.strip():
                                chunks.append({
                                    "text": combined.strip(),
                                    "preview_user": " ".join(current_exchange["user"].split())[:120],
                                    "preview_asst": " ".join(current_exchange["assistant"].split())[:120],
                                    "line": current_exchange["line"],
                                })
                        current_exchange = {"user": text, "assistant": "", "line": line_num}
                    elif text and role == "assistant":
                        current_exchange["assistant"] += " " + text

                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except OSError:
        pass

    # Don't forget the last exchange
    if current_exchange["user"] or current_exchange["assistant"]:
        combined = current_exchange["user"] + " " + current_exchange["assistant"]
        if combined.strip():
            chunks.append({
                "text": combined.strip(),
                "preview_user": " ".join(current_exchange["user"].split())[:120],
                "preview_asst": " ".join(current_exchange["assistant"].split())[:120],
                "line": current_exchange["line"],
            })

    return chunks


def cmd_build():
    """Build or rebuild the RAG index."""
    print(f"{BOLD}{CYAN}Building RAG Index...{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    # Collect all documents
    docs = []  # [{id, session_id, agent, project, fpath, mtime, preview_user, preview_asst}]
    inverted_index = defaultdict(list)  # term -> [doc_id, ...]
    doc_lengths = {}  # doc_id -> term_count
    total_docs = 0
    total_sessions = 0

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue
        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue

            session_id = os.path.basename(fpath).replace(".jsonl", "")
            chunks = extract_chunks(fpath, adapter.name)
            total_sessions += 1

            for chunk in chunks:
                doc_id = total_docs
                total_docs += 1

                tokens = tokenize(chunk["text"])
                term_freq = Counter(tokens)
                doc_lengths[doc_id] = len(tokens)

                for term, freq in term_freq.items():
                    inverted_index[term].append((doc_id, freq))

                docs.append({
                    "id": doc_id,
                    "session_id": session_id,
                    "agent": adapter.name,
                    "project": display_path,
                    "fpath": fpath,
                    "mtime": mtime,
                    "preview_user": chunk["preview_user"],
                    "preview_asst": chunk["preview_asst"],
                    "line": chunk["line"],
                })

    if total_docs == 0:
        print(f"  {GRAY}No content found to index.{R}")
        return

    # Compute average document length
    avg_dl = sum(doc_lengths.values()) / len(doc_lengths) if doc_lengths else 1

    # Save index
    os.makedirs(INDEX_DIR, exist_ok=True)

    index_data = {
        "inverted_index": {term: postings for term, postings in inverted_index.items()},
        "doc_lengths": {str(k): v for k, v in doc_lengths.items()},
        "avg_dl": avg_dl,
        "total_docs": total_docs,
        "built_at": datetime.utcnow().isoformat() + "Z",
        "total_sessions": total_sessions,
        "vocab_size": len(inverted_index),
    }

    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f)

    with open(DOCS_FILE, "w") as f:
        json.dump(docs, f)

    index_size = os.path.getsize(INDEX_FILE) + os.path.getsize(DOCS_FILE)
    if index_size > 1_000_000:
        size_str = f"{index_size / 1_000_000:.1f}M"
    else:
        size_str = f"{index_size / 1_000:.0f}K"

    print(f"  {WHITE}Sessions:{R}   {total_sessions}")
    print(f"  {WHITE}Documents:{R}  {total_docs} chunks")
    print(f"  {WHITE}Vocabulary:{R} {len(inverted_index):,} terms")
    print(f"  {WHITE}Index size:{R} {size_str}")
    print()
    print(f"{GREEN}Index built.{R} Query with: {CYAN}agents rag \"your question\"{R}")


def cmd_query():
    """Search the RAG index using BM25 scoring."""
    if not query:
        print(f"{RED}Usage: agents rag \"your query\"{R}")
        print(f"{DIM}Build index first: agents rag --build{R}")
        raise SystemExit(1)

    # Load index
    try:
        with open(INDEX_FILE) as f:
            index_data = json.load(f)
        with open(DOCS_FILE) as f:
            docs = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"{RED}No index found. Build it first: agents rag --build{R}")
        raise SystemExit(1)

    inverted_index = index_data["inverted_index"]
    doc_lengths = {int(k): v for k, v in index_data["doc_lengths"].items()}
    avg_dl = index_data["avg_dl"]
    total_docs = index_data["total_docs"]

    # Tokenize query
    query_terms = tokenize(query)
    if not query_terms:
        print(f"{GRAY}No searchable terms in query.{R}")
        return

    # BM25 scoring
    scores = defaultdict(float)
    now = time.time()

    for term in query_terms:
        postings = inverted_index.get(term, [])
        if not postings:
            continue

        # IDF: log((N - n + 0.5) / (n + 0.5) + 1)
        n = len(postings)
        idf = math.log((total_docs - n + 0.5) / (n + 0.5) + 1)

        for doc_id, tf in postings:
            dl = doc_lengths.get(doc_id, avg_dl)
            # BM25 TF component
            tf_score = (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avg_dl))
            scores[doc_id] += idf * tf_score

    if not scores:
        print(f"{GRAY}No matches for: {query}{R}")
        return

    # Apply recency boost (slight preference for recent sessions)
    for doc_id in scores:
        doc = docs[doc_id]
        age_days = (now - doc.get("mtime", now)) / 86400
        recency_boost = 1.0 + max(0, (30 - age_days) / 100)  # Up to 30% boost for recent
        scores[doc_id] *= recency_boost

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: -x[1])

    print(f"{BOLD}{CYAN}RAG Search: {WHITE}{query}{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    shown = 0
    seen_sessions = set()

    for doc_id, score in ranked:
        if shown >= max_results:
            break
        doc = docs[doc_id]

        # Deduplicate by session (show best chunk per session)
        sid = doc["session_id"]
        if sid in seen_sessions:
            continue
        seen_sessions.add(sid)
        shown += 1

        agent = doc["agent"]
        project = doc["project"]
        mtime = doc.get("mtime", 0)

        a_color = CYAN if agent == "claude" else GREEN

        # Time ago
        age = int(now - mtime)
        if age < 3600:
            age_str = f"{age // 60}m ago"
        elif age < 86400:
            age_str = f"{age // 3600}h ago"
        elif age < 604800:
            age_str = f"{age // 86400}d ago"
        else:
            age_str = f"{age // 604800}w ago"

        short_project = project
        if len(short_project) > 35:
            short_project = "..." + short_project[-32:]

        print(f"  {YELLOW}{shown}.{R} {a_color}[{agent}]{R} {BLUE}{short_project}{R}  "
              f"{GRAY}{age_str}{R}  {DIM}(score: {score:.2f}){R}")
        print(f"     {DIM}session {MAGENTA}{sid[:8]}{R}")

        # Show previews with query term highlighting
        user_preview = doc.get("preview_user", "")
        asst_preview = doc.get("preview_asst", "")

        if user_preview:
            # Highlight query terms
            highlighted = user_preview
            for term in query_terms:
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                highlighted = pattern.sub(f"{RED}{BOLD}\\g<0>{R}", highlighted)
            print(f"     {GRAY}\"{R}{highlighted}{GRAY}\"{R}")

        if asst_preview:
            highlighted = asst_preview
            for term in query_terms:
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                highlighted = pattern.sub(f"{RED}{BOLD}\\g<0>{R}", highlighted)
            print(f"     {DIM}→ \"{R}{highlighted}{DIM}\"{R}")

        print()

    remaining = len(seen_sessions.union(set())) - shown
    total_matches = len(set(docs[d]["session_id"] for d in scores))
    print(f"{DIM}{'─' * 52}{R}")
    print(f"{BOLD}{shown}{R} results from {total_matches} matching sessions "
          f"{DIM}(index: {total_docs} chunks from {index_data.get('total_sessions', '?')} sessions){R}")


def cmd_status():
    """Show RAG index status."""
    print(f"{BOLD}{CYAN}RAG Index Status{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    if not os.path.isfile(INDEX_FILE):
        print(f"  {GRAY}No index built. Run: agents rag --build{R}")
        return

    try:
        with open(INDEX_FILE) as f:
            index_data = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"  {RED}Index file corrupted. Rebuild: agents rag --build{R}")
        return

    built_at = index_data.get("built_at", "?")
    total_docs = index_data.get("total_docs", 0)
    total_sessions = index_data.get("total_sessions", 0)
    vocab_size = index_data.get("vocab_size", 0)

    index_size = os.path.getsize(INDEX_FILE)
    docs_size = os.path.getsize(DOCS_FILE) if os.path.isfile(DOCS_FILE) else 0
    total_size = index_size + docs_size

    if total_size > 1_000_000:
        size_str = f"{total_size / 1_000_000:.1f}M"
    else:
        size_str = f"{total_size / 1_000:.0f}K"

    print(f"  {WHITE}Built:{R}       {built_at}")
    print(f"  {WHITE}Sessions:{R}    {total_sessions}")
    print(f"  {WHITE}Chunks:{R}      {total_docs:,}")
    print(f"  {WHITE}Vocabulary:{R}  {vocab_size:,} terms")
    print(f"  {WHITE}Index size:{R}  {size_str}")
    print()
    print(f"{DIM}Rebuild: agents rag --build{R}")


# Dispatch
actions = {
    "query": cmd_query,
    "build": cmd_build,
    "status": cmd_status,
}

handler = actions.get(action)
if handler:
    handler()
else:
    print(f"{RED}Unknown action: {action}{R}")
    raise SystemExit(1)
