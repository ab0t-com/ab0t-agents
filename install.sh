#!/bin/bash
#
# agents - Coding Agent Session Browser
# Installation script
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ab0t-com/ab0t-agents/main/install.sh | bash
#   wget -qO- https://raw.githubusercontent.com/ab0t-com/ab0t-agents/main/install.sh | bash
#
# Or clone and run locally:
#   git clone https://github.com/ab0t-com/ab0t-agents.git
#   cd ab0t-agents && ./install.sh
#
# Safety:
#   - Idempotent: safe to run multiple times
#   - Backups existing installation before overwriting
#   - Validates downloads before installing
#   - No sudo required (installs to user directory)
#   - Dry-run mode available
#

set -euo pipefail

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    DIM=''
    RESET=''
fi

# Configuration
REPO="ab0t-com/ab0t-agents"
REPO_CLONE_URL="https://github.com/${REPO}.git"
REPO_TAR_URL="https://github.com/${REPO}/archive/refs/heads/main.tar.gz"
BIN_DIR="${AGENTS_BIN_DIR:-$HOME/.local/bin}"
INSTALL_DIR="${AGENTS_INSTALL_DIR:-$BIN_DIR/ab0t}"

# Flags
DRY_RUN=false
FORCE=false
VERBOSE=false

# Logging
log_info() { echo -e "${BLUE}[INFO]${RESET} $*"; }
log_success() { echo -e "${GREEN}[OK]${RESET} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $*"; }
log_error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
log_debug() { if $VERBOSE; then echo -e "${DIM}[DEBUG] $*${RESET}"; fi; }
log_dry() { echo -e "${CYAN}[DRY-RUN]${RESET} Would: $*"; }

# Safe execution (respects dry-run)
safe_exec() {
    if $DRY_RUN; then
        log_dry "$*"
        return 0
    fi
    "$@"
}

show_banner() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╔═══════════════════════════════════════════╗"
    echo "  ║   agents - Coding Agent Session Browser   ║"
    echo "  ╚═══════════════════════════════════════════╝"
    echo -e "${RESET}"
}

# Check for required dependencies
check_dependencies() {
    local missing=()

    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi

    if ! command -v bash &> /dev/null; then
        missing+=("bash")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required dependencies: ${missing[*]}"
        exit 1
    fi

    log_debug "Dependencies check passed"
}

# Check if coding agent data exists (informational only)
check_agent_data() {
    local found=false
    if [ -d "$HOME/.claude" ]; then
        log_debug "Found ~/.claude directory"
        found=true
    fi
    if [ -d "$HOME/.codex" ]; then
        log_debug "Found ~/.codex directory"
        found=true
    fi
    if [ -d "$HOME/.gemini" ]; then
        log_debug "Found ~/.gemini directory"
        found=true
    fi
    if ! $found; then
        log_warn "No coding agent data found (~/.claude, ~/.codex, or ~/.gemini)"
        echo -e "${DIM}  This is normal if you haven't used a coding agent yet.${RESET}"
        echo -e "${DIM}  The tool will work once you start using one.${RESET}"
        echo
    fi
}

# Create installation directories safely
create_dirs() {
    if [ ! -d "$INSTALL_DIR" ]; then
        log_info "Creating $INSTALL_DIR"
        safe_exec mkdir -p "$INSTALL_DIR"
    else
        log_debug "Directory exists: $INSTALL_DIR"
    fi
}

# Backup existing file or directory
backup_path() {
    local target="$1"
    if [ -e "$target" ]; then
        local backup="${target}.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "Backing up existing $(basename "$target") to ${backup##*/}"
        safe_exec cp -r "$target" "$backup"
        return 0
    fi
    return 1
}

# Validate a file is not empty and looks like a shell script
validate_script() {
    local file="$1"

    if [ ! -f "$file" ]; then
        log_error "File does not exist: $file"
        return 1
    fi

    if [ ! -s "$file" ]; then
        log_error "File is empty: $file"
        return 1
    fi

    # Check it starts with shebang
    if ! head -1 "$file" | grep -q '^#!/'; then
        log_error "File doesn't appear to be a valid script: $file"
        return 1
    fi

    log_debug "Validated: $file"
    return 0
}

# Locate source files - either local repo or download
# Sets SOURCE_DIR to a directory containing: agents, agents.1.txt, scripts/
locate_source() {
    # Check if we're running from inside the repo (local install)
    local script_dir=""

    # BASH_SOURCE is empty when piped from curl
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "bash" ]; then
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi

    if [ -n "$script_dir" ] && [ -f "$script_dir/agents" ] && [ -d "$script_dir/scripts" ]; then
        log_debug "Using local source files from $script_dir"
        SOURCE_DIR="$script_dir"
        SOURCE_IS_TEMP=false
        return 0
    fi

    # Download from GitHub
    log_info "Downloading from repository..."
    local temp_dir
    temp_dir=$(mktemp -d)
    SOURCE_IS_TEMP=true

    # Prefer tarball (faster, no git needed), fall back to git clone
    if command -v curl &> /dev/null; then
        log_debug "Downloading tarball with curl"
        if curl -sSL "$REPO_TAR_URL" | tar -xz -C "$temp_dir" 2>/dev/null; then
            SOURCE_DIR="$temp_dir/ab0t-agents-main"
            if [ -f "$SOURCE_DIR/agents" ] && [ -d "$SOURCE_DIR/scripts" ]; then
                return 0
            fi
        fi
    elif command -v wget &> /dev/null; then
        log_debug "Downloading tarball with wget"
        if wget -qO- "$REPO_TAR_URL" | tar -xz -C "$temp_dir" 2>/dev/null; then
            SOURCE_DIR="$temp_dir/ab0t-agents-main"
            if [ -f "$SOURCE_DIR/agents" ] && [ -d "$SOURCE_DIR/scripts" ]; then
                return 0
            fi
        fi
    fi

    # Fall back to git clone
    if command -v git &> /dev/null; then
        log_debug "Falling back to git clone"
        if git clone --depth 1 "$REPO_CLONE_URL" "$temp_dir/repo" 2>/dev/null; then
            SOURCE_DIR="$temp_dir/repo"
            if [ -f "$SOURCE_DIR/agents" ] && [ -d "$SOURCE_DIR/scripts" ]; then
                return 0
            fi
        fi
    fi

    log_error "Failed to download source files. Need curl, wget, or git."
    rm -rf "$temp_dir"
    return 1
}

# Install all files from SOURCE_DIR to INSTALL_DIR
install_files() {
    log_info "Installing agents..."

    # Validate source
    if ! validate_script "$SOURCE_DIR/agents"; then
        log_error "Source script validation failed"
        return 1
    fi

    # Check if scripts/ directory exists in source
    if [ ! -d "$SOURCE_DIR/scripts" ]; then
        log_error "scripts/ directory not found in source"
        return 1
    fi

    local dest_script="$INSTALL_DIR/agents"
    local dest_man="$INSTALL_DIR/agents.1.txt"
    local dest_scripts="$INSTALL_DIR/scripts"

    # Check if update is needed (compare main script)
    if [ -f "$dest_script" ] && ! $FORCE; then
        if cmp -s "$SOURCE_DIR/agents" "$dest_script"; then
            # Also check scripts dir exists
            if [ -d "$dest_scripts" ]; then
                log_success "Already up to date"
                return 0
            fi
        fi
    fi

    # Backup existing installation
    backup_path "$dest_script" 2>/dev/null || true
    backup_path "$dest_scripts" 2>/dev/null || true

    # Install main script
    log_info "Installing agents to $INSTALL_DIR"
    safe_exec cp "$SOURCE_DIR/agents" "$dest_script"
    safe_exec chmod +x "$dest_script"

    # Install scripts/ directory
    log_info "Installing scripts/ directory"
    safe_exec rm -rf "$dest_scripts"
    safe_exec cp -r "$SOURCE_DIR/scripts" "$dest_scripts"

    # Install shell integration
    if [ -d "$SOURCE_DIR/shell" ]; then
        local dest_shell="$INSTALL_DIR/shell"
        log_info "Installing shell/ integration"
        safe_exec rm -rf "$dest_shell"
        safe_exec cp -r "$SOURCE_DIR/shell" "$dest_shell"
    fi

    # Install man page if available
    if [ -f "$SOURCE_DIR/agents.1.txt" ]; then
        safe_exec cp "$SOURCE_DIR/agents.1.txt" "$dest_man"
    else
        log_warn "Man page not found, skipping"
    fi

    # Create symlink in BIN_DIR so 'agents' is on PATH
    local symlink="$BIN_DIR/agents"
    if [ "$BIN_DIR" != "$INSTALL_DIR" ]; then
        # Remove old file/symlink if it exists
        if [ -e "$symlink" ] || [ -L "$symlink" ]; then
            safe_exec rm -f "$symlink"
        fi
        safe_exec ln -s "$INSTALL_DIR/agents" "$symlink"
        log_success "Symlinked $symlink → $INSTALL_DIR/agents"
    fi

    return 0
}

# Cleanup temp source dir if needed
cleanup_source() {
    if ${SOURCE_IS_TEMP:-false} && [ -n "${SOURCE_DIR:-}" ]; then
        rm -rf "$(dirname "$SOURCE_DIR")" 2>/dev/null || true
    fi
}

# Configure shell integration (PATH + source wrapper)
configure_shell() {
    local shell_name
    shell_name=$(basename "${SHELL:-bash}")
    local rc_file=""

    case "$shell_name" in
        bash) rc_file="$HOME/.bashrc" ;;
        zsh)  rc_file="$HOME/.zshrc" ;;
        fish) rc_file="$HOME/.config/fish/config.fish" ;;
        *)    rc_file="" ;;
    esac

    if [ -z "$rc_file" ]; then
        log_warn "Could not detect shell rc file. Manually add to your shell config:"
        echo -e "  ${CYAN}export PATH=\"\$PATH:$INSTALL_DIR\"${RESET}"
        echo -e "  ${CYAN}source $INSTALL_DIR/shell/agents.bash${RESET}"
        return
    fi

    local changed=false

    # Add PATH if needed
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        if [ -f "$rc_file" ] && grep -qF "$INSTALL_DIR" "$rc_file" 2>/dev/null; then
            log_debug "PATH entry already in $rc_file (not yet loaded)"
        else
            if [ "$shell_name" = "fish" ]; then
                safe_exec bash -c "echo 'set -gx PATH \$PATH $INSTALL_DIR' >> \"$rc_file\""
            else
                safe_exec bash -c "echo 'export PATH=\"\$PATH:$INSTALL_DIR\"' >> \"$rc_file\""
            fi
            log_success "Added PATH to $rc_file"
            changed=true
        fi
    fi

    # Add shell wrapper source if needed (not for fish — bash/zsh only)
    if [ "$shell_name" != "fish" ] && [ -f "$INSTALL_DIR/shell/agents.bash" ]; then
        if [ -f "$rc_file" ] && grep -qF "shell/agents.bash" "$rc_file" 2>/dev/null; then
            log_debug "Shell integration already in $rc_file"
        else
            safe_exec bash -c "echo 'source $INSTALL_DIR/shell/agents.bash' >> \"$rc_file\""
            log_success "Added shell integration to $rc_file"
            changed=true
        fi
    fi

    if $changed; then
        echo
        echo -e "${DIM}Run ${GREEN}source $rc_file${DIM} or open a new terminal to activate.${RESET}"
    fi
}

# Verify installation
verify_installation() {
    local dest_script="$INSTALL_DIR/agents"

    if $DRY_RUN; then
        log_dry "Verify installation at $dest_script"
        return 0
    fi

    if [ -x "$dest_script" ] && [ -d "$INSTALL_DIR/scripts" ]; then
        echo
        log_success "Installation complete!"
        echo
        echo -e "${DIM}Installed to: $INSTALL_DIR${RESET}"

        # Try to get version
        local version
        version=$("$dest_script" --version 2>/dev/null || echo "")
        if [ -n "$version" ]; then
            echo -e "${DIM}$version${RESET}"
        fi
        return 0
    else
        log_error "Installation verification failed"
        return 1
    fi
}

# Show quick start
show_quickstart() {
    echo
    echo -e "${BOLD}Quick Start:${RESET}"
    echo -e "  ${GREEN}agents${RESET}          ${DIM}# List your projects${RESET}"
    echo -e "  ${GREEN}agents show .${RESET}   ${DIM}# Show sessions here${RESET}"
    echo -e "  ${GREEN}agents stats${RESET}    ${DIM}# Usage statistics${RESET}"
    echo -e "  ${GREEN}agents help${RESET}     ${DIM}# Full documentation${RESET}"
    echo

    # Shell integration hint
    if [ -f "$INSTALL_DIR/shell/agents.bash" ]; then
        echo -e "${BOLD}Shell Integration ${DIM}(recommended):${RESET}"
        echo -e "  Add to your ${CYAN}~/.bashrc${RESET} or ${CYAN}~/.zshrc${RESET}:"
        echo
        echo -e "    ${GREEN}source $INSTALL_DIR/shell/agents.bash${RESET}"
        echo
        echo -e "  ${DIM}Enables 'agents go' to cd into project directories.${RESET}"
        echo
    fi
}

# Uninstall function
uninstall() {
    log_info "Uninstalling agents..."

    local dest_script="$INSTALL_DIR/agents"
    local dest_man="$INSTALL_DIR/agents.1.txt"
    local dest_scripts="$INSTALL_DIR/scripts"

    if [ -f "$dest_script" ]; then
        safe_exec rm "$dest_script"
        log_success "Removed $dest_script"
    else
        log_warn "$dest_script not found"
    fi

    if [ -f "$dest_man" ]; then
        safe_exec rm "$dest_man"
        log_success "Removed $dest_man"
    fi

    if [ -d "$dest_scripts" ]; then
        safe_exec rm -rf "$dest_scripts"
        log_success "Removed $dest_scripts"
    fi

    # Remove shell integration
    if [ -d "$INSTALL_DIR/shell" ]; then
        safe_exec rm -rf "$INSTALL_DIR/shell"
        log_success "Removed $INSTALL_DIR/shell"
    fi

    # Remove symlink from BIN_DIR
    local symlink="$BIN_DIR/agents"
    if [ -L "$symlink" ]; then
        safe_exec rm -f "$symlink"
        log_success "Removed symlink $symlink"
    fi

    # Remove ab0t dir if empty
    if [ -d "$INSTALL_DIR" ]; then
        rmdir "$INSTALL_DIR" 2>/dev/null && log_success "Removed $INSTALL_DIR" || \
            log_warn "Files remain in $INSTALL_DIR (remove manually if desired)"
    fi

    log_success "Uninstall complete"
    exit 0
}

# Show help
show_help() {
    cat << EOF
agents install script

Usage: ./install.sh [OPTIONS]

Options:
  --help, -h         Show this help
  --uninstall, -u    Remove agents from system
  --dry-run, -n      Show what would be done without making changes
  --force, -f        Force reinstall even if up to date
  --verbose, -v      Show detailed output

Environment variables:
  AGENTS_INSTALL_DIR   Installation directory (default: ~/.local/bin/ab0t)
  AGENTS_BIN_DIR       Symlink directory on PATH (default: ~/.local/bin)

Installs to ~/.local/bin/ab0t/:
  agents             Main CLI script
  agents.1.txt       Man page
  scripts/           Python modules (adapters, stats, session management)
  shell/             Shell integration (agents.bash)

Symlinks:
  ~/.local/bin/agents → ~/.local/bin/ab0t/agents

Examples:
  ./install.sh                              # Install locally
  ./install.sh --dry-run                    # Preview installation
  ./install.sh --uninstall                  # Remove installation
  curl -sSL URL/install.sh | bash           # Install from GitHub
  AGENTS_INSTALL_DIR=~/bin ./install.sh     # Custom directory

Safety:
  - Idempotent: safe to run multiple times
  - Creates backups before overwriting existing files
  - Validates downloads before installing
  - No sudo required (user directory only)
EOF
    exit 0
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                show_help
                ;;
            --uninstall|-u)
                show_banner
                uninstall
                ;;
            --dry-run|-n)
                DRY_RUN=true
                shift
                ;;
            --force|-f)
                FORCE=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}

# Main installation flow
main() {
    parse_args "$@"

    show_banner

    if $DRY_RUN; then
        log_warn "Dry-run mode: no changes will be made"
        echo
    fi

    check_dependencies
    check_agent_data
    create_dirs

    # Always cleanup temp source on exit
    trap cleanup_source EXIT

    if locate_source && install_files; then
        verify_installation
        configure_shell
        show_quickstart
    else
        log_error "Installation failed"
        exit 1
    fi
}

main "$@"
