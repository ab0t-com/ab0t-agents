#!/bin/bash
#
# fix-claude-paths.sh - Fix Claude project directory naming
#
# The default Claude naming convention uses '-' prefix which causes
# shell parsing issues (looks like command flags). This script renames
# directories to use a more parseable format.
#
# Before: -home-ubuntu-tmp
# After:  home/ubuntu/tmp (or home_ubuntu_tmp with --flat)
#
# Usage:
#   ./fix-claude-paths.sh [OPTIONS] <claude-data-dir>
#
# Options:
#   --dry-run, -n    Show what would be done without making changes
#   --flat           Use underscores instead of nested dirs (home_ubuntu_tmp)
#   --help, -h       Show this help
#

set -euo pipefail

DRY_RUN=false
FLAT_MODE=false
DATA_DIR=""

usage() {
    sed -n '3,18p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

log() { echo "[INFO] $*"; }
log_dry() { echo "[DRY-RUN] Would: $*"; }
log_warn() { echo "[WARN] $*" >&2; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n) DRY_RUN=true; shift ;;
        --flat) FLAT_MODE=true; shift ;;
        --help|-h) usage ;;
        -*) echo "Unknown option: $1" >&2; exit 1 ;;
        *) DATA_DIR="$1"; shift ;;
    esac
done

if [[ -z "$DATA_DIR" ]]; then
    echo "Error: Please specify the claude data directory"
    echo "Usage: $0 [OPTIONS] <claude-data-dir>"
    exit 1
fi

PROJECTS_DIR="$DATA_DIR/projects"

if [[ ! -d "$PROJECTS_DIR" ]]; then
    echo "Error: Projects directory not found: $PROJECTS_DIR"
    exit 1
fi

log "Processing: $PROJECTS_DIR"
echo

# Count directories to process
count=$(find "$PROJECTS_DIR" -maxdepth 1 -type d -name '-*' | wc -l)

if [[ $count -eq 0 ]]; then
    log "No directories starting with '-' found. Nothing to do."
    exit 0
fi

log "Found $count directories to rename"
echo

# Process each directory
renamed=0
for old_path in "$PROJECTS_DIR"/-*; do
    [[ -d "$old_path" ]] || continue

    old_name=$(basename "$old_path")

    # Remove leading dash and convert to new format
    # -home-ubuntu-tmp -> home-ubuntu-tmp (just remove leading dash)
    new_name="${old_name#-}"

    if $FLAT_MODE; then
        # Replace remaining dashes with underscores for truly flat names
        # home-ubuntu-tmp -> home_ubuntu_tmp
        new_name=$(echo "$new_name" | tr '-' '_')
    fi

    new_path="$PROJECTS_DIR/$new_name"

    if [[ "$old_path" == "$new_path" ]]; then
        continue
    fi

    if [[ -e "$new_path" ]]; then
        log_warn "Skipping (target exists): $old_name -> $new_name"
        continue
    fi

    if $DRY_RUN; then
        log_dry "mv '$old_name' -> '$new_name'"
    else
        mv "$old_path" "$new_path"
        log "Renamed: $old_name -> $new_name"
    fi
    renamed=$((renamed + 1))
done

echo
if $DRY_RUN; then
    log "Would rename $renamed directories (dry-run)"
else
    log "Renamed $renamed directories"
fi

# Show result
echo
log "Current directory structure:"
ls "$PROJECTS_DIR" | head -10
[[ $(ls "$PROJECTS_DIR" | wc -l) -gt 10 ]] && echo "... and more"
