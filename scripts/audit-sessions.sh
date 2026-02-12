#!/bin/bash
# Audit session content types

DIR="${1:-$HOME/.claude/projects}"

echo "Session content audit"
echo "====================="
echo

for project_dir in "$DIR"/*/; do
    project=$(basename "$project_dir")
    echo "Project: $project"

    for f in "$project_dir"*.jsonl; do
        [[ -f "$f" ]] || continue
        name=$(basename "$f" | cut -c1-8)
        users=$(grep -c '"type":"user"' "$f" 2>/dev/null || echo 0)
        summaries=$(grep -c '"type":"summary"' "$f" 2>/dev/null || echo 0)
        snapshots=$(grep -c '"type":"file-history-snapshot"' "$f" 2>/dev/null || echo 0)
        size=$(du -h "$f" | cut -f1)

        # Determine status
        if [[ $users -gt 0 ]]; then
            status="✓ conversation"
        elif [[ $snapshots -gt 0 ]]; then
            status="⚠ snapshots only"
        else
            status="✗ empty"
        fi

        echo "  $name: users=$users sum=$summaries snap=$snapshots ($size) $status"
    done
    echo
done
