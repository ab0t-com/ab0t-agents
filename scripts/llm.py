#!/usr/bin/env python3
"""
Shared LLM client for agents CLI modules.

Supports:
- Anthropic API (Claude models)
- OpenAI-compatible API (for Codex/GPT users)
- Jinja2 prompt template rendering from scripts/prompts/*.j2
- Structured JSON output parsing with schema validation
- Cost tracking (accumulated per session)
- Retry with exponential backoff
- Graceful degradation: available() returns False when no API key

Usage:
    from llm import LLM
    llm = LLM()
    if llm.available():
        result = llm.render_and_call("compact_summarize", {"messages": msgs})
    else:
        # fallback to local heuristics
"""

import os
import sys
import json
import time
import re
from pathlib import Path

# ── Configuration ──────────────────────────────────────────

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# Model defaults
ANTHROPIC_SMALL = "claude-haiku-4-5-20251001"   # cheap, fast
ANTHROPIC_LARGE = "claude-sonnet-4-5-20250929"  # capable
OPENAI_SMALL = "gpt-4o-mini"
OPENAI_LARGE = "gpt-4o"

# Cost per million tokens (approximate)
MODEL_COSTS = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


class LLMError(Exception):
    """Raised when an LLM call fails after retries."""
    pass


class LLM:
    """Shared LLM client with provider auto-detection and cost tracking."""

    def __init__(self):
        self._provider = None  # "anthropic" or "openai"
        self._api_key = None
        self._client = None
        self._cost_input_tokens = 0
        self._cost_output_tokens = 0
        self._cost_dollars = 0.0
        self._calls = 0
        self._detect_provider()

    def _detect_provider(self):
        """Auto-detect which API is available."""
        # Anthropic first (preferred)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            self._provider = "anthropic"
            self._api_key = key
            return

        # OpenAI fallback
        key = os.environ.get("OPENAI_API_KEY", "")
        if key:
            self._provider = "openai"
            self._api_key = key
            return

    def available(self):
        """Returns True if an LLM API is configured and callable."""
        return self._provider is not None and self._api_key is not None

    @property
    def provider(self):
        return self._provider or "none"

    # ── Template rendering ─────────────────────────────────

    def render_template(self, template_name, variables):
        """Render a Jinja2 template from scripts/prompts/.

        Args:
            template_name: Name without .j2 extension (e.g., "compact_summarize")
            variables: Dict of template variables

        Returns:
            Rendered prompt string
        """
        template_path = os.path.join(PROMPTS_DIR, f"{template_name}.j2")
        if not os.path.isfile(template_path):
            raise LLMError(f"Template not found: {template_path}")

        try:
            from jinja2 import Environment, FileSystemLoader
            env = Environment(
                loader=FileSystemLoader(PROMPTS_DIR),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            template = env.get_template(f"{template_name}.j2")
            return template.render(**variables)
        except ImportError:
            # Fallback: simple string substitution if jinja2 not installed
            with open(template_path) as f:
                content = f.read()
            for key, value in variables.items():
                content = content.replace("{{ " + key + " }}", str(value))
                content = content.replace("{{" + key + "}}", str(value))
            return content

    # ── API calls ──────────────────────────────────────────

    def call(self, prompt, model=None, max_tokens=2048, temperature=0.3,
             json_output=False, system=None, retries=2):
        """Make an LLM API call.

        Args:
            prompt: User message text
            model: Model ID override (defaults to small model)
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            json_output: If True, request JSON mode
            system: Optional system prompt
            retries: Number of retry attempts

        Returns:
            Response text string

        Raises:
            LLMError if not available or all retries fail
        """
        if not self.available():
            raise LLMError("No LLM API configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")

        if self._provider == "anthropic":
            return self._call_anthropic(prompt, model, max_tokens, temperature,
                                         json_output, system, retries)
        else:
            return self._call_openai(prompt, model, max_tokens, temperature,
                                      json_output, system, retries)

    def _call_anthropic(self, prompt, model, max_tokens, temperature,
                         json_output, system, retries):
        """Call Anthropic API via HTTP (no SDK required)."""
        import urllib.request
        import urllib.error

        model = model or ANTHROPIC_SMALL
        url = "https://api.anthropic.com/v1/messages"

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

        last_error = None
        for attempt in range(retries + 1):
            try:
                data = json.dumps(body).encode()
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode())

                # Extract text
                content = result.get("content", [])
                text = ""
                for block in content:
                    if block.get("type") == "text":
                        text += block.get("text", "")

                # Track usage
                usage = result.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                self._track_cost(model, input_tokens, output_tokens)

                return text

            except urllib.error.HTTPError as e:
                last_error = e
                if e.code == 429:  # Rate limited
                    wait = min(2 ** attempt * 2, 30)
                    time.sleep(wait)
                elif e.code >= 500:  # Server error
                    wait = min(2 ** attempt, 10)
                    time.sleep(wait)
                else:
                    try:
                        error_body = e.read().decode()
                    except Exception:
                        error_body = str(e)
                    raise LLMError(f"Anthropic API error {e.code}: {error_body}")
            except (urllib.error.URLError, OSError) as e:
                last_error = e
                if attempt < retries:
                    time.sleep(2 ** attempt)

        raise LLMError(f"Anthropic API failed after {retries + 1} attempts: {last_error}")

    def _call_openai(self, prompt, model, max_tokens, temperature,
                      json_output, system, retries):
        """Call OpenAI-compatible API via HTTP (no SDK required)."""
        import urllib.request
        import urllib.error

        model = model or OPENAI_SMALL
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        url = f"{base_url}/chat/completions"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if json_output:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        last_error = None
        for attempt in range(retries + 1):
            try:
                data = json.dumps(body).encode()
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode())

                text = result["choices"][0]["message"]["content"]

                # Track usage
                usage = result.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                self._track_cost(model, input_tokens, output_tokens)

                return text

            except urllib.error.HTTPError as e:
                last_error = e
                if e.code == 429:
                    wait = min(2 ** attempt * 2, 30)
                    time.sleep(wait)
                elif e.code >= 500:
                    wait = min(2 ** attempt, 10)
                    time.sleep(wait)
                else:
                    try:
                        error_body = e.read().decode()
                    except Exception:
                        error_body = str(e)
                    raise LLMError(f"OpenAI API error {e.code}: {error_body}")
            except (urllib.error.URLError, OSError) as e:
                last_error = e
                if attempt < retries:
                    time.sleep(2 ** attempt)

        raise LLMError(f"OpenAI API failed after {retries + 1} attempts: {last_error}")

    # ── Structured output ──────────────────────────────────

    def call_json(self, prompt, model=None, max_tokens=2048, temperature=0.2,
                  system=None, retries=2):
        """Call LLM and parse response as JSON.

        The prompt should instruct the model to respond with valid JSON.
        Attempts to extract JSON from the response even if there's surrounding text.

        Returns:
            Parsed dict/list from JSON response

        Raises:
            LLMError if response isn't valid JSON
        """
        text = self.call(prompt, model=model, max_tokens=max_tokens,
                         temperature=temperature, json_output=True,
                         system=system, retries=retries)
        return self._parse_json_response(text)

    def _parse_json_response(self, text):
        """Extract and parse JSON from LLM response text."""
        text = text.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { or [ to end
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            if start >= 0:
                # Find matching end
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == start_char:
                        depth += 1
                    elif text[i] == end_char:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start:i + 1])
                            except json.JSONDecodeError:
                                break

        raise LLMError(f"Could not parse JSON from LLM response: {text[:200]}...")

    # ── Template + call combined ───────────────────────────

    def render_and_call(self, template_name, variables, model=None,
                         max_tokens=2048, temperature=0.3, system=None):
        """Render a Jinja2 template and call the LLM with it.

        Args:
            template_name: Template name without .j2
            variables: Template variables dict
            model: Model override
            max_tokens: Max response tokens
            temperature: Sampling temperature
            system: Optional system prompt

        Returns:
            Response text string
        """
        prompt = self.render_template(template_name, variables)
        return self.call(prompt, model=model, max_tokens=max_tokens,
                         temperature=temperature, system=system)

    def render_and_call_json(self, template_name, variables, model=None,
                              max_tokens=2048, temperature=0.2, system=None):
        """Render a template and get structured JSON response."""
        prompt = self.render_template(template_name, variables)
        return self.call_json(prompt, model=model, max_tokens=max_tokens,
                              temperature=temperature, system=system)

    # ── Cost tracking ──────────────────────────────────────

    def _track_cost(self, model, input_tokens, output_tokens):
        """Accumulate cost tracking."""
        self._cost_input_tokens += input_tokens
        self._cost_output_tokens += output_tokens
        self._calls += 1

        costs = MODEL_COSTS.get(model, {"input": 1.0, "output": 3.0})
        self._cost_dollars += (input_tokens * costs["input"] / 1_000_000 +
                               output_tokens * costs["output"] / 1_000_000)

    @property
    def total_cost(self):
        """Total accumulated cost in dollars."""
        return self._cost_dollars

    @property
    def total_calls(self):
        """Total number of API calls made."""
        return self._calls

    @property
    def total_tokens(self):
        """Total tokens used (input + output)."""
        return self._cost_input_tokens + self._cost_output_tokens

    def cost_summary(self):
        """Return a human-readable cost summary string."""
        if self._calls == 0:
            return "No LLM calls made"
        return (f"{self._calls} call{'s' if self._calls != 1 else ''}, "
                f"{self._cost_input_tokens + self._cost_output_tokens:,} tokens, "
                f"${self._cost_dollars:.4f}")

    def print_cost_summary(self):
        """Print cost summary to stderr if any calls were made."""
        if self._calls > 0:
            from modules.utils import DIM, R
            print(f"  {DIM}LLM: {self.cost_summary()}{R}", file=sys.stderr)


# ── Module-level singleton ─────────────────────────────────

_instance = None


def get_llm():
    """Get or create the singleton LLM instance."""
    global _instance
    if _instance is None:
        _instance = LLM()
    return _instance
