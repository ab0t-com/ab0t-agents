# Tickets

This directory contains feature proposals, bug investigations, and technical specifications for the agents project.

## Structure

```
tickets/
├── README.md              # This file
├── 001-multi-agent-support.md
├── 002-feature-name.md
└── ...
```

## Ticket Format

Each ticket follows this naming convention:

```
<number>-<short-description>.md
```

- **Number**: 3-digit zero-padded (001, 002, etc.)
- **Description**: Lowercase, hyphen-separated

## Ticket Template

```markdown
# Ticket #XXX: Title

**Status:** Open | In Progress | Completed | Closed
**Priority:** Critical | High | Medium | Low
**Type:** Feature | Bug | Research | Refactor
**Created:** YYYY-MM-DD
**Labels:** `label1`, `label2`

---

## Summary

Brief description of the ticket.

---

## Background

Context and motivation.

---

## Proposed Solution

Technical approach.

---

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

---

## Notes

Additional context.
```

## Workflow

1. **Create**: New tickets start with status `Open`
2. **Assign**: Move to `In Progress` when work begins
3. **Branch**: Create branch `feature/<ticket-num>-description`
4. **Implement**: Reference ticket in commits
5. **Close**: Mark `Completed` when merged, or `Closed` if abandoned

## Linking Tickets to Code

Reference tickets in:
- Branch names: `feature/001-multi-agent-support`
- Commit messages: `feat: add provider interface (#001)`
- PR descriptions: `Implements #001`

## Current Tickets

| # | Title | Status | Priority |
|---|-------|--------|----------|
| 001 | Multi-Agent Support | Open | High |

---

*See [CONTRIBUTING.md](../CONTRIBUTING.md) for full GitOps workflow.*
