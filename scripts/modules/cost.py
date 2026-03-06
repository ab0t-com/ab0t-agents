#!/usr/bin/env python3
"""
Estimate API costs from token usage data.
Called by: agents cost
Env vars: PERIOD (today/week/month/all)

Pricing is approximate and based on publicly available rates.
"""

import os
import sys
import json
import time
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter

from utils import (WHITE, CYAN, GREEN, YELLOW, MAGENTA, GRAY, RED, BOLD, DIM, R,
                   CACHE_DIR)

period = os.environ.get("PERIOD", "all")

STATS_CACHE = os.path.join(CACHE_DIR, "stats_cache.json")

# Pricing per million tokens (approximate, USD)
# Users can override with ~/.ab0t/.agents/pricing.json
PRICING = {
    # Claude models
    "claude-opus-4-5": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.75},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
    # Codex / OpenAI models (estimated)
    "gpt-5.3-codex": {"input": 2.0, "output": 8.0, "cache_read": 0.0, "cache_create": 0.0},
}

# Default fallback pricing
DEFAULT_PRICING = {"input": 10.0, "output": 50.0, "cache_read": 1.0, "cache_create": 12.5}


def load_custom_pricing():
    """Load user-customizable pricing overrides."""
    pfile = os.path.join(CACHE_DIR, "pricing.json")
    try:
        with open(pfile) as f:
            custom = json.load(f)
            PRICING.update(custom)
    except (OSError, json.JSONDecodeError):
        pass


def get_pricing(model):
    """Get pricing for a model, matching by substring."""
    for key, p in PRICING.items():
        if key in model or model in key:
            return p
    # Try partial match on short name
    short = model.replace("claude-", "").split("-202")[0]
    for key, p in PRICING.items():
        if short in key:
            return p
    return DEFAULT_PRICING


def load_stats_cache():
    try:
        with open(STATS_CACHE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def fmt_cost(c):
    if c >= 100:
        return f"${c:,.0f}"
    if c >= 1:
        return f"${c:.2f}"
    if c >= 0.01:
        return f"${c:.2f}"
    return f"${c:.4f}"


def cmd_cost():
    load_custom_pricing()

    ALL_ADAPTERS = [ClaudeAdapter(), CodexAdapter(), GeminiAdapter()]
    now = time.time()

    cutoff = {
        "today": now - 86400,
        "week": now - 604800,
        "month": now - 2592000,
        "all": 0,
    }.get(period, 0)

    cache = load_stats_cache()

    total_cost = 0.0
    cost_by_model = defaultdict(float)
    cost_by_project = defaultdict(float)
    cost_today = 0.0
    cost_week = 0.0
    cost_month = 0.0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    cache_savings = 0.0

    day_ago = now - 86400
    week_ago = now - 604800
    month_ago = now - 2592000

    for adapter in ALL_ADAPTERS:
        if not adapter.is_available():
            continue

        for display_path, fpath, mtime, is_agent in adapter.iter_all_sessions():
            if is_agent:
                continue

            cached = cache.get(fpath)
            if cached and cached.get("mtime") == mtime:
                stats = cached
            else:
                stats = adapter.parse_session_stats(fpath)
                stats["mtime"] = mtime

            inp = stats.get("input", 0)
            out = stats.get("output", 0)
            cr = stats.get("cache_read", 0)
            cc = stats.get("cache_create", 0)
            models = stats.get("models", {})

            if inp == 0 and out == 0 and cr == 0:
                continue

            primary_model = ""
            if models:
                primary_model = max(models, key=models.get)

            pricing = get_pricing(primary_model) if primary_model else DEFAULT_PRICING

            session_cost = (
                (inp / 1_000_000) * pricing["input"]
                + (out / 1_000_000) * pricing["output"]
                + (cr / 1_000_000) * pricing["cache_read"]
                + (cc / 1_000_000) * pricing["cache_create"]
            )

            uncached_cost = ((inp + cr + cc) / 1_000_000) * pricing["input"]
            cached_cost = (
                (inp / 1_000_000) * pricing["input"]
                + (cr / 1_000_000) * pricing["cache_read"]
                + (cc / 1_000_000) * pricing["cache_create"]
            )
            cache_savings += uncached_cost - cached_cost

            total_cost += session_cost
            total_input += inp
            total_output += out
            total_cache_read += cr
            total_cache_create += cc

            if primary_model:
                cost_by_model[primary_model] += session_cost
            cost_by_project[display_path] += session_cost

            if mtime > day_ago:
                cost_today += session_cost
            if mtime > week_ago:
                cost_week += session_cost
            if mtime > month_ago:
                cost_month += session_cost

    print(f"{BOLD}{CYAN}Estimated API Cost{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print(f"{DIM}Based on approximate public pricing. Actual costs may vary.{R}")

    if total_cost == 0:
        print(f"\n{GRAY}No token usage data found.{R}")
        print(f"{DIM}(Codex sessions don't include token counts){R}")
        raise SystemExit(0)

    print(f"\n  {WHITE}Total:{R}     {BOLD}{GREEN}{fmt_cost(total_cost)}{R}")
    print(f"  {GREEN}Today:{R}     {fmt_cost(cost_today):<12} "
          f"{YELLOW}This week:{R} {fmt_cost(cost_week):<12} "
          f"{GRAY}This month:{R} {fmt_cost(cost_month)}")

    if cache_savings > 0:
        print(f"\n  {WHITE}Cache savings:{R} {GREEN}~{fmt_cost(cache_savings)}{R} "
              f"{DIM}(what it would have cost without caching){R}")

    if cost_by_model:
        print(f"\n{BOLD} By Model{R}")
        for model, cost in sorted(cost_by_model.items(), key=lambda x: -x[1]):
            short = model.replace("claude-", "").replace("-20251101", "").replace("-20250929", "").replace("-20251001", "")
            pct = cost / total_cost * 100 if total_cost > 0 else 0
            bar_len = int(pct / 5)
            bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
            print(f"  {MAGENTA}{short:20s}{R} {DIM}{bar}{R} {GREEN}{fmt_cost(cost):>8}{R} {DIM}({pct:.0f}%){R}")

    if cost_by_project:
        print(f"\n{BOLD} Top Projects{R}")
        for path, cost in sorted(cost_by_project.items(), key=lambda x: -x[1])[:8]:
            display = path
            if len(display) > 35:
                display = "..." + display[-32:]
            print(f"  {YELLOW}{display:38s}{R} {GREEN}{fmt_cost(cost):>8}{R}")

    print()
    print(f"{DIM}Customize pricing: ~/.ab0t/.agents/pricing.json{R}")


if __name__ == "__main__":
    cmd_cost()
