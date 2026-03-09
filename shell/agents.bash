# agents shell integration
# Source this file from your .bashrc or .zshrc:
#   source ~/.local/bin/ab0t/shell/agents.bash
#
# This wrapper lets "agents go" change your working directory.
# Without it, "agents go" launches in a subshell and the cd is lost
# when the agent exits.

agents() {
    # Intercept "go" — it needs to cd the current shell
    case "${1:-}" in
        go|g|start)
            shift
            if [ -z "${1:-}" ]; then
                command agents go
                return $?
            fi

            # Resolve the project path and agent via the script
            local result
            result=$(command agents _resolve-go "$@") || return $?

            local project_path agent_name
            project_path=$(printf '%s\n' "$result" | head -1)
            agent_name=$(printf '%s\n' "$result" | tail -1)

            # Validate path is an absolute directory before cd
            if [ -z "$project_path" ] || [ ! -d "$project_path" ]; then
                echo "agents: cannot cd to '$project_path'" >&2
                return 1
            fi

            # Allowlist: only known agent binaries
            case "$agent_name" in
                claude|codex|gemini) ;;
                *)
                    echo "agents: unknown agent '$agent_name'" >&2
                    return 1
                    ;;
            esac

            # cd in the current shell — this is why the wrapper exists
            cd "$project_path" || return 1
            echo -e "\033[0;32m→ \033[1m$(pwd)\033[0m"
            echo

            # Launch the agent (not exec — we want to stay in this dir after it exits)
            case "$agent_name" in
                codex)  codex resume --last ;;
                gemini) gemini --resume ;;
                *)      claude -c --verbose ;;
            esac
            ;;
        *)
            # Everything else passes through to the script
            command agents "$@"
            ;;
    esac
}
