# Ticket #002: Fix Ambiguous Path Decoding in `agents`

**Status:** Completed
**Priority:** High
**Type:** Bug Fix
**Created:** 2026-02-04
**Completed:** 2026-02-04 21:29:37 UTC
**Labels:** `bugfix`, `path-resolution`

---

## Problem

Claude Code encodes project paths by replacing `/`, `_`, `.`, and `@` with `-` when creating project folder names under `~/.claude/projects/`. The original `decode_project_path` function used a naive `sed 's/-/\//g'` which converted every `-` back to `/`, producing incorrect paths when the original path contained `-`, `_`, or `.` characters.

### Examples of incorrect decoding

| Encoded folder name | Old (wrong) decode | Actual path |
|---|---|---|
| `-home-ubuntu-www-utils-www--inbox-tree` | `/home/ubuntu/www/utils/www//inbox/tree` | `/home/ubuntu/www/utils/www/_inbox/tree` |
| `-home-ubuntu-tools-consenus--new-project` | `/home/ubuntu/tools/consenus//new/project` | `/home/ubuntu/tools/consenus/.new-project` |
| `-home-ubuntu-www-real-estate` | `/home/ubuntu/www/real/estate` | `/home/ubuntu/www/real-estate` |

---

## Changes Made

### 1. New `decode_project_path` function (lines 79-210)

- Checks a local cache file first for previously resolved paths
- Tries simple all-dashes-to-slashes decode; if that path exists, returns it
- Falls back to a Python-based recursive path walker that:
  - Splits the encoded name on `-`
  - Walks component by component, checking what actually exists on the filesystem
  - Tries variations with `_`, `.`, `-` as separators between parts
  - Tries `.` prefix for hidden directories/files
  - Uses `itertools.product` for mixed-separator combinations (capped at 4 parts per segment)
- Falls back to naive decode if no filesystem match found

### 2. New `encode_project_path` function (lines 213-218)

- Encodes `/`, `_`, `.`, `@` as `-` to match Claude Code's behavior
- Replaces 4 inline `sed` encoding calls in `cmd_tree` and `cmd_show`

### 3. Cache relocation

- All cache files moved from `~/.claude/` to `~/.ab0t/.agents/`:
  - `decode_cache` - resolved path mappings
  - `projects_cache` - project list for quick index lookup
  - `sessions_cache` - session list for resume command
  - `path_cache` - last viewed project path
- `mkdir -p` guards added before all cache writes
- No writes to `~/.claude/` remain; script only reads from it

---

## Files Modified

- `agents` - all changes in this single file

## Testing

- `agents list` - all paths resolve correctly including `_inbox`, `.new-project`, `real-estate`, `sandbox-platform`
- `agents show .` - current directory lookup works
- `agents show /home/ubuntu/www/utils/www/_inbox/tree` - underscore path resolves correctly
- Cache files created in `~/.ab0t/.agents/` as expected
