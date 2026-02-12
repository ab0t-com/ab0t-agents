#!/usr/bin/env python3
"""
Settings & Configuration Manager - audit and manage agent configs.
Called by: agents config <action> [args]
Env vars: ACTION (check/hooks/compare/paths), PROJECT (path)
"""

import os
import sys
import json
import glob

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

action = os.environ.get("ACTION", "check")
project_path = os.environ.get("PROJECT", os.getcwd())

# Known config locations
CLAUDE_GLOBAL = os.path.expanduser("~/.claude/settings.json")
CLAUDE_GLOBAL_MD = os.path.expanduser("~/.claude/CLAUDE.md")
CODEX_GLOBAL = os.path.expanduser("~/.codex/config.json")
CODEX_GLOBAL_MD = os.path.expanduser("~/.codex/instructions.md")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def file_lines(path):
    try:
        with open(path) as f:
            return len(f.readlines())
    except OSError:
        return 0


def find_project_configs(project):
    """Find all config files for a project directory."""
    configs = {}
    # Claude project settings
    claude_proj = os.path.join(project, ".claude", "settings.json")
    if os.path.isfile(claude_proj):
        configs["claude_project_settings"] = claude_proj
    # CLAUDE.md
    claude_md = os.path.join(project, "CLAUDE.md")
    if os.path.isfile(claude_md):
        configs["claude_md"] = claude_md
    # .claude/CLAUDE.md
    claude_md2 = os.path.join(project, ".claude", "CLAUDE.md")
    if os.path.isfile(claude_md2):
        configs["claude_md_dot"] = claude_md2
    # codex.md
    codex_md = os.path.join(project, "codex.md")
    if os.path.isfile(codex_md):
        configs["codex_md"] = codex_md
    # .codex/instructions.md
    codex_inst = os.path.join(project, ".codex", "instructions.md")
    if os.path.isfile(codex_inst):
        configs["codex_instructions"] = codex_inst
    return configs


def print_section(title):
    print(f"\n{BOLD}{WHITE}{title}{R}")


def print_hooks(settings, prefix=""):
    hooks = settings.get("hooks", {})
    if not hooks:
        print(f"{prefix}  {GRAY}(none configured){R}")
        return
    for event_type, hook_list in hooks.items():
        if not isinstance(hook_list, list):
            hook_list = [hook_list]
        for hook in hook_list:
            if isinstance(hook, dict):
                matcher = hook.get("matcher", "")
                cmd = hook.get("command", "")
                print(f"{prefix}  {YELLOW}{event_type}{R}: {cmd}", end="")
                if matcher:
                    print(f" {DIM}(on: {matcher}){R}", end="")
                print()
            else:
                print(f"{prefix}  {YELLOW}{event_type}{R}: {hook}")


def print_permissions(settings, prefix=""):
    allow = settings.get("permissions", {}).get("allow", [])
    deny = settings.get("permissions", {}).get("deny", [])
    if allow:
        for p in allow[:10]:
            print(f"{prefix}  {GREEN}allow{R}: {p}")
        if len(allow) > 10:
            print(f"{prefix}  {DIM}... and {len(allow) - 10} more{R}")
    if deny:
        for p in deny[:5]:
            print(f"{prefix}  {RED}deny{R}:  {p}")
    if not allow and not deny:
        print(f"{prefix}  {GRAY}(using defaults){R}")


def cmd_check():
    """Audit all configuration across agents."""
    print(f"{BOLD}{CYAN}Configuration Audit{R}")
    print(f"{DIM}{'─' * 52}{R}")

    warnings = []

    # Claude Global
    print_section("Claude Code - Global")
    claude_global = load_json(CLAUDE_GLOBAL)
    if claude_global:
        print(f"  {DIM}File: {CLAUDE_GLOBAL}{R}")
        print(f"\n  {BOLD}Hooks:{R}")
        print_hooks(claude_global, "  ")
        print(f"\n  {BOLD}Permissions:{R}")
        print_permissions(claude_global, "  ")

        # Check for risky permissions
        allow = claude_global.get("permissions", {}).get("allow", [])
        for p in allow:
            if isinstance(p, str) and ("rm " in p or "rm -" in p):
                warnings.append(f"Global allows destructive command: {p}")
            if isinstance(p, str) and "git *" in p:
                warnings.append("Global allows all git commands (includes destructive ops)")
    else:
        print(f"  {GRAY}Not found: {CLAUDE_GLOBAL}{R}")

    # Claude Global MD
    if os.path.isfile(CLAUDE_GLOBAL_MD):
        lines = file_lines(CLAUDE_GLOBAL_MD)
        print(f"\n  {BOLD}CLAUDE.md (global):{R} {GREEN}present{R} ({lines} lines)")
    else:
        print(f"\n  {BOLD}CLAUDE.md (global):{R} {GRAY}not found{R}")

    # Claude project
    print_section(f"Claude Code - Project ({project_path})")
    proj_configs = find_project_configs(project_path)
    if "claude_project_settings" in proj_configs:
        proj_settings = load_json(proj_configs["claude_project_settings"])
        if proj_settings:
            print(f"  {DIM}File: {proj_configs['claude_project_settings']}{R}")
            print(f"\n  {BOLD}Hooks:{R}")
            print_hooks(proj_settings, "  ")
            print(f"\n  {BOLD}Permissions:{R}")
            print_permissions(proj_settings, "  ")

            # Check if project hooks override global
            if claude_global and claude_global.get("hooks") and proj_settings.get("hooks"):
                for event in proj_settings.get("hooks", {}):
                    if event in claude_global.get("hooks", {}):
                        warnings.append(f"Project hooks override global for: {event}")
    else:
        print(f"  {GRAY}No .claude/settings.json{R}")

    if "claude_md" in proj_configs:
        lines = file_lines(proj_configs["claude_md"])
        print(f"\n  {BOLD}CLAUDE.md:{R} {GREEN}present{R} ({lines} lines)")
    elif "claude_md_dot" in proj_configs:
        lines = file_lines(proj_configs["claude_md_dot"])
        print(f"\n  {BOLD}.claude/CLAUDE.md:{R} {GREEN}present{R} ({lines} lines)")
    else:
        print(f"\n  {BOLD}CLAUDE.md:{R} {YELLOW}missing{R} {DIM}(consider adding project guidelines){R}")
        warnings.append("No CLAUDE.md in project (consider adding one)")

    # Codex
    print_section("Codex")
    codex_global = load_json(CODEX_GLOBAL)
    if codex_global:
        print(f"  {DIM}File: {CODEX_GLOBAL}{R}")
        model = codex_global.get("model", "")
        policy = codex_global.get("approval_policy", "")
        if model:
            print(f"  {BOLD}Model:{R} {model}")
        if policy:
            print(f"  {BOLD}Approval policy:{R} {policy}")
    else:
        codex_dir = os.path.expanduser("~/.codex")
        if os.path.isdir(codex_dir):
            print(f"  {GRAY}No config.json found{R}")
        else:
            print(f"  {GRAY}Codex not installed{R}")

    if "codex_md" in proj_configs:
        lines = file_lines(proj_configs["codex_md"])
        print(f"  {BOLD}codex.md:{R} {GREEN}present{R} ({lines} lines)")
    elif "codex_instructions" in proj_configs:
        lines = file_lines(proj_configs["codex_instructions"])
        print(f"  {BOLD}instructions.md:{R} {GREEN}present{R} ({lines} lines)")
    else:
        if os.path.isdir(os.path.expanduser("~/.codex")):
            print(f"  {BOLD}codex.md:{R} {GRAY}not found in project{R}")

    # MCP servers
    print_section("MCP Servers")
    mcp_found = False
    if claude_global:
        mcp = claude_global.get("mcpServers", {})
        if mcp:
            mcp_found = True
            for name, config in mcp.items():
                cmd = config.get("command", "")
                print(f"  {GREEN}{name}{R}: {DIM}{cmd}{R}")
    if not mcp_found:
        print(f"  {GRAY}(none configured){R}")

    # Warnings
    if warnings:
        print_section("Warnings")
        for w in warnings:
            print(f"  {YELLOW}[!]{R} {w}")

    print()


def cmd_hooks():
    """List all active hooks across agents."""
    print(f"{BOLD}{CYAN}Active Hooks{R}")
    print(f"{DIM}{'─' * 52}{R}")

    found_any = False

    # Claude global hooks
    claude_global = load_json(CLAUDE_GLOBAL)
    if claude_global and claude_global.get("hooks"):
        print(f"\n{BOLD}  Claude Global:{R}")
        print_hooks(claude_global, "  ")
        found_any = True

    # Claude project hooks
    proj_settings_path = os.path.join(project_path, ".claude", "settings.json")
    proj_settings = load_json(proj_settings_path)
    if proj_settings and proj_settings.get("hooks"):
        short_path = project_path
        if len(short_path) > 30:
            short_path = "..." + short_path[-27:]
        print(f"\n{BOLD}  Claude Project ({short_path}):{R}")
        print_hooks(proj_settings, "  ")
        found_any = True

    if not found_any:
        print(f"\n  {GRAY}No hooks configured.{R}")
        print(f"\n{DIM}  Add hooks in ~/.claude/settings.json or .claude/settings.json{R}")

    print()


def cmd_compare():
    """Compare configuration between agents."""
    print(f"{BOLD}{CYAN}Agent Configuration Comparison{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    claude_global = load_json(CLAUDE_GLOBAL)
    codex_global = load_json(CODEX_GLOBAL)

    has_claude = claude_global is not None or os.path.isdir(os.path.expanduser("~/.claude"))
    has_codex = codex_global is not None or os.path.isdir(os.path.expanduser("~/.codex"))

    if not has_claude and not has_codex:
        print(f"  {GRAY}No agents configured.{R}")
        return

    # Header
    print(f"  {'':<22} {CYAN}{'Claude':^15}{R} {GREEN}{'Codex':^15}{R}")
    print(f"  {'─' * 22} {'─' * 15} {'─' * 15}")

    # Installed
    c_inst = f"{GREEN}yes{R}" if has_claude else f"{RED}no{R}"
    x_inst = f"{GREEN}yes{R}" if has_codex else f"{RED}no{R}"
    print(f"  {'Installed':<22} {c_inst:^24} {x_inst:^24}")

    # Hooks
    c_hooks = len(claude_global.get("hooks", {})) if claude_global else 0
    x_hooks = 0  # Codex doesn't have hooks in the same way
    print(f"  {'Hooks':<22} {str(c_hooks) + ' active':^15} {str(x_hooks) + ' active':^15}")

    # MCP servers
    c_mcp = len(claude_global.get("mcpServers", {})) if claude_global else 0
    print(f"  {'MCP Servers':<22} {str(c_mcp):^15} {'n/a':^15}")

    # Model
    c_model = ""
    if claude_global:
        c_model = claude_global.get("model", "default")
    x_model = codex_global.get("model", "default") if codex_global else "default"
    print(f"  {'Model':<22} {c_model:^15} {x_model:^15}")

    # Project docs
    proj_configs = find_project_configs(project_path)
    c_docs = "CLAUDE.md" if "claude_md" in proj_configs or "claude_md_dot" in proj_configs else "missing"
    x_docs = "codex.md" if "codex_md" in proj_configs or "codex_instructions" in proj_configs else "missing"
    c_color = GREEN if c_docs != "missing" else YELLOW
    x_color = GREEN if x_docs != "missing" else YELLOW
    print(f"  {'Project docs':<22} {c_color}{c_docs:^15}{R} {x_color}{x_docs:^15}{R}")

    # Approval
    c_approval = "interactive" if claude_global else "n/a"
    x_approval = codex_global.get("approval_policy", "suggest") if codex_global else "n/a"
    print(f"  {'Approval mode':<22} {c_approval:^15} {x_approval:^15}")

    print()


def cmd_paths():
    """Show all config file locations."""
    print(f"{BOLD}{CYAN}Configuration Paths{R}")
    print(f"{DIM}{'─' * 52}{R}")
    print()

    paths = [
        ("Claude global settings", CLAUDE_GLOBAL),
        ("Claude global CLAUDE.md", CLAUDE_GLOBAL_MD),
        ("Claude project settings", os.path.join(project_path, ".claude", "settings.json")),
        ("Claude project CLAUDE.md", os.path.join(project_path, "CLAUDE.md")),
        ("Claude keybindings", os.path.expanduser("~/.claude/keybindings.json")),
        ("Codex global config", CODEX_GLOBAL),
        ("Codex instructions", CODEX_GLOBAL_MD),
        ("Codex project codex.md", os.path.join(project_path, "codex.md")),
        ("Agents cache", os.path.expanduser("~/.ab0t/.agents/")),
    ]

    for label, path in paths:
        exists = os.path.exists(path)
        status = f"{GREEN}exists{R}" if exists else f"{GRAY}not found{R}"
        print(f"  {WHITE}{label:30s}{R} {status}")
        print(f"    {DIM}{path}{R}")

    print()


# Dispatch
actions = {
    "check": cmd_check,
    "hooks": cmd_hooks,
    "compare": cmd_compare,
    "paths": cmd_paths,
}

handler = actions.get(action)
if handler:
    handler()
else:
    print(f"{RED}Unknown action: {action}{R}")
    print(f"{DIM}Actions: check, hooks, compare, paths{R}")
    raise SystemExit(1)
