# Accessibility Color Audit - agents CLI

**Date:** 2026-02-09
**Scope:** All color usage in `agents` script
**Assumption:** Dark terminal background (black/near-black), users may have color vision deficiency

---

## Color Palette In Use

| Variable | ANSI Code | Appearance | Contrast on Dark |
|----------|-----------|------------|-----------------|
| RED | `0;31m` | Standard red | OK |
| GREEN | `0;32m` | Standard green | OK |
| YELLOW | `1;33m` | Bold yellow | HIGH - good |
| BLUE | `0;34m` | Standard blue | LOW - problematic |
| MAGENTA | `0;35m` | Standard magenta | OK |
| CYAN | `0;36m` | Standard cyan | OK |
| WHITE | `1;37m` | Bold white | HIGH - good |
| GRAY | `0;90m` | Bright black | LOW - problematic |
| DIM | `2m` | Dimmed text | VERY LOW - problematic |

---

## Issues Found

### CRITICAL: BLUE (`0;34m`) still used in multiple places

Standard blue is notoriously hard to read on dark backgrounds. We fixed the main `cmd_list` path display (now YELLOW), but BLUE is still used in:

| Line | Location | Usage | Fix Suggestion |
|------|----------|-------|----------------|
| 631 | Python tree walker | `{BLUE}{name}/` - directory names | Change to CYAN or bold blue |
| 468 | Python tree colors | `BLUE = "\033[0;34m"` definition | Change to `\033[1;34m` (bold) or CYAN |
| 784 | `cmd_tree_project` | `${BLUE}files/` label | Change to CYAN |
| 874 | `_draw_tree` fallback | `${BLUE}${name}/` dirs | Change to CYAN |
| 1106 | `cmd_resume` | `${BLUE}$project_path` | Change to YELLOW (matches list/show) |

**Recommendation:** Either replace all `BLUE` with `\033[1;34m` (bold blue, much brighter) at the definition level (line 42), or swap specific uses to CYAN. Easiest fix: change line 42 to bold blue.

### MODERATE: GRAY (`0;90m`) for content text

Gray (bright black) is used for text the user actually needs to read:

| Line | Location | Usage |
|------|----------|-------|
| 769 | `cmd_tree_project` | Session preview quotes `"summary..."` |
| 1054 | `cmd_show` | Session preview quotes `"%.55s"` |
| 935 | `cmd_list` | Default time color (old items >1d) |

**Recommendation:** Session previews are important context. Consider using DIM+WHITE instead of GRAY for preview text, or use `\033[37m` (standard white, not bold) which is brighter than gray.

### MODERATE: DIM (`2m`) used extensively

DIM text can be nearly invisible on some terminal emulators (especially older ones or those with low contrast themes):

| Line | Usage |
|------|-------|
| 565 | Session annotation brackets in tree |
| 639 | "... (N more files)" count |
| 648-649 | Footer hint text |
| 904, 911 | Separator lines |
| 960 | "sessions: N" metadata |
| 972-973 | Usage hints |
| All help text | Comment descriptions |

**Recommendation:** DIM for decorative elements (separators, hints) is fine. But functional text like file counts and session metadata should avoid DIM alone. Consider DIM+WHITE or just GRAY for these.

### LOW: Color-blind considerations

- **RED vs GREEN:** Used in different contexts (errors vs time/success), so not confusing
- **GREEN time vs YELLOW time vs GRAY time:** Sequential aging scale, works well. However, deuteranopia (red-green blindness) users may not distinguish GREEN from YELLOW as clearly. Both are still visible though.
- **MAGENTA session badges:** Distinct from all other colors, good choice

### LOW: No `NO_COLOR` / `TERM` support

The script does not check for:
- `NO_COLOR` environment variable (emerging standard for disabling color)
- `TERM=dumb` or piped output (not a TTY)

Colors are always emitted even when piped to a file or another command, which produces garbled ANSI escape codes.

---

## Quick Fixes (minimal changes)

### Fix 1: Make BLUE readable (1 line change)
Change line 42 from standard to bold blue:
```
BLUE='\033[1;34m'   # was '\033[0;34m'
```
This makes ALL blue usage brighter. Affects: tree directory names, resume path.

### Fix 2: Make resume path match list/show (1 line change)
Line 1106: change `${BLUE}$project_path` to `${YELLOW}$project_path`

### Fix 3: Brighter session previews (2 line changes)
Lines 769, 1054: change `${GRAY}` to `${DIM}${WHITE}` for session preview quotes.

---

## Future Improvements

1. Add `NO_COLOR` support (check env var, disable all colors)
2. Add TTY detection (`[ -t 1 ]`) to skip colors when piped
3. Consider a `--no-color` flag
4. Test with common color blindness simulators (Coblis, Color Oracle)
