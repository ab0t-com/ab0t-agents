# Contributing to Agents

This document defines the GitOps workflow, conventions, and best practices for contributing to this project. It is designed for both human contributors and autonomous AI systems.

---

## Table of Contents

1. [Overview](#overview)
2. [Repository Structure](#repository-structure)
3. [Branch Strategy](#branch-strategy)
4. [Issue Management](#issue-management)
5. [Pull Request Workflow](#pull-request-workflow)
6. [Commit Message Convention](#commit-message-convention)
7. [Versioning and Tags](#versioning-and-tags)
8. [Release Process](#release-process)
9. [Hotfix Procedure](#hotfix-procedure)
10. [Rebase Workflow](#rebase-workflow)
11. [Code Review Standards](#code-review-standards)
12. [AI Contributor Guidelines](#ai-contributor-guidelines)
13. [Conflict Resolution](#conflict-resolution)
14. [Security](#security)

---

## Overview

This project follows a **trunk-based development** model with short-lived feature branches. All changes flow through pull requests with mandatory review before merging to `main`.

### Core Principles

1. **`main` is always deployable** - Never commit broken code to main
2. **Small, focused changes** - One logical change per PR
3. **Rebase over merge** - Keep history linear and clean
4. **Atomic commits** - Each commit should be self-contained and buildable
5. **Documentation as code** - Update docs in the same PR as code changes

---

## Repository Structure

```
.
├── agents                 # Main executable
├── agents.1.txt           # Man page documentation
├── install.sh             # Installation script
├── scripts/               # Development and release scripts
│   └── build-release.sh
├── releases/              # Versioned release archives
├── docs/                  # Additional documentation (future)
├── tests/                 # Test scripts (future)
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── .gitignore
```

---

## Branch Strategy

### Protected Branches

| Branch | Purpose | Protection Rules |
|--------|---------|------------------|
| `main` | Production-ready code | Require PR, require review, require status checks, no force push |
| `release/*` | Release preparation | Require PR, require review |

### Branch Naming Convention

All branch names must follow this pattern:

```
<type>/<issue-number>-<short-description>
```

#### Branch Types

| Type | Purpose | Example |
|------|---------|---------|
| `feature/` | New functionality | `feature/42-add-search-command` |
| `fix/` | Bug fixes | `fix/17-tree-depth-overflow` |
| `hotfix/` | Urgent production fixes | `hotfix/99-security-patch` |
| `docs/` | Documentation only | `docs/23-update-man-page` |
| `refactor/` | Code refactoring | `refactor/31-extract-json-parser` |
| `test/` | Adding/updating tests | `test/44-add-install-tests` |
| `chore/` | Maintenance tasks | `chore/50-update-gitignore` |
| `perf/` | Performance improvements | `perf/61-optimize-session-load` |
| `ci/` | CI/CD changes | `ci/70-add-shellcheck` |
| `release/` | Release preparation | `release/1.1.0` |

#### Rules

- Use lowercase only
- Use hyphens (`-`) as word separators
- Keep descriptions under 50 characters
- Always include issue number when one exists
- No special characters except hyphens

#### Examples

```bash
# Good
feature/42-add-search-command
fix/17-handle-empty-sessions
docs/23-examples-section
hotfix/99-fix-path-injection

# Bad
Feature/42-Add-Search          # Wrong: uppercase
feature/add-search             # Wrong: missing issue number
feature/42_add_search          # Wrong: underscores
feature/42                     # Wrong: no description
my-feature                     # Wrong: missing type prefix
```

### Sub-Branching (Feature Branches)

For large features requiring multiple sub-tasks:

```
feature/42-add-search-command           # Parent feature branch
├── feature/42-search-index             # Sub-branch 1
├── feature/42-search-cli               # Sub-branch 2
└── feature/42-search-tests             # Sub-branch 3
```

Sub-branches merge into the parent feature branch via PR, then the parent merges to `main`.

```bash
# Create sub-branch from feature branch
git checkout feature/42-add-search-command
git checkout -b feature/42-search-index

# When complete, PR into parent feature branch (not main)
# Then finally PR parent into main
```

---

## Issue Management

### Issue Templates

#### Bug Report

```markdown
## Bug Description
[Clear description of the bug]

## Environment
- OS: [e.g., macOS 14.0, Ubuntu 22.04]
- Bash version: [e.g., 5.2.15]
- Claude Code version: [e.g., 2.0.76]
- Agents version: [e.g., 1.0.0]

## Steps to Reproduce
1. [First step]
2. [Second step]
3. [...]

## Expected Behavior
[What should happen]

## Actual Behavior
[What actually happens]

## Logs/Screenshots
[If applicable]
```

#### Feature Request

```markdown
## Feature Description
[Clear description of the feature]

## Use Case
[Why is this feature needed? What problem does it solve?]

## Proposed Solution
[How should this work?]

## Alternatives Considered
[Other approaches you've thought about]

## Additional Context
[Any other relevant information]
```

### Issue Labels

| Label | Description | Color |
|-------|-------------|-------|
| `bug` | Something isn't working | `#d73a4a` |
| `feature` | New feature request | `#a2eeef` |
| `enhancement` | Improvement to existing feature | `#84b6eb` |
| `documentation` | Documentation only | `#0075ca` |
| `good first issue` | Good for newcomers | `#7057ff` |
| `help wanted` | Extra attention needed | `#008672` |
| `priority: critical` | Must be fixed immediately | `#b60205` |
| `priority: high` | Should be fixed soon | `#d93f0b` |
| `priority: medium` | Normal priority | `#fbca04` |
| `priority: low` | Nice to have | `#0e8a16` |
| `wontfix` | Will not be worked on | `#ffffff` |
| `duplicate` | Duplicate of another issue | `#cfd3d7` |
| `blocked` | Waiting on external dependency | `#f9d0c4` |
| `in-progress` | Currently being worked on | `#1d76db` |
| `needs-review` | Ready for review | `#5319e7` |
| `ai-generated` | Created by AI contributor | `#c5def5` |
| `ai-assigned` | Assigned to AI contributor | `#bfdadc` |

### Issue Lifecycle

```
┌─────────┐     ┌───────────┐     ┌─────────────┐     ┌────────┐
│  Open   │ ──▶ │ Triaged   │ ──▶ │ In Progress │ ──▶ │ Review │
└─────────┘     └───────────┘     └─────────────┘     └────────┘
                                                           │
                     ┌──────────┐     ┌────────┐           │
                     │ Wontfix  │ ◀── │ Closed │ ◀─────────┘
                     └──────────┘     └────────┘
```

1. **Open**: Issue created, awaiting triage
2. **Triaged**: Labels applied, priority set, assigned
3. **In Progress**: Work has started (branch created)
4. **Review**: PR submitted, under review
5. **Closed**: Merged or resolved
6. **Wontfix**: Decided not to address

### Linking Issues

Always reference issues in:
- Branch names: `feature/42-description`
- Commit messages: `feat: add search (#42)`
- PR descriptions: `Closes #42` or `Fixes #42`

---

## Pull Request Workflow

### Creating a Pull Request

#### 1. Sync with main

```bash
git checkout main
git pull --rebase origin main
git checkout -b feature/42-my-feature
```

#### 2. Make changes with atomic commits

```bash
# Work on your changes
git add -p                    # Stage interactively
git commit                    # Commit with proper message
```

#### 3. Keep branch updated

```bash
git fetch origin
git rebase origin/main
```

#### 4. Push and create PR

```bash
git push -u origin feature/42-my-feature
# Create PR via GitHub UI or CLI
gh pr create --title "feat: add search command" --body "..."
```

### PR Title Convention

PR titles must follow the commit message format:

```
<type>(<scope>): <description>
```

Examples:
- `feat(cli): add search command`
- `fix(tree): handle empty sessions`
- `docs(readme): update installation instructions`

### PR Description Template

```markdown
## Summary
[Brief description of what this PR does]

## Related Issues
Closes #42

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] Performance improvement
- [ ] Test update

## Changes Made
- [Change 1]
- [Change 2]
- [...]

## Testing Done
- [ ] Tested manually on [OS/environment]
- [ ] Added/updated tests
- [ ] All existing tests pass

## Checklist
- [ ] My code follows the project style guidelines
- [ ] I have performed a self-review
- [ ] I have commented hard-to-understand areas
- [ ] I have updated documentation
- [ ] My changes generate no new warnings
- [ ] I have rebased on latest main

## Screenshots (if applicable)
[Add screenshots for UI changes]

## Notes for Reviewers
[Any specific areas to focus on, concerns, or context]
```

### PR Size Guidelines

| Size | Lines Changed | Review Time |
|------|---------------|-------------|
| XS | < 50 | < 15 min |
| S | 50-200 | 15-30 min |
| M | 200-500 | 30-60 min |
| L | 500-1000 | 1-2 hours |
| XL | > 1000 | Split required |

**Rule**: If a PR exceeds 500 lines, consider splitting it.

### PR Review Requirements

| Target Branch | Required Reviewers | Required Checks |
|---------------|-------------------|-----------------|
| `main` | 1 | All CI passing |
| `release/*` | 2 | All CI passing |
| `hotfix/*` | 1 (expedited) | Critical CI only |

### Merging Strategy

**Always use rebase and merge** (not squash, not merge commit):

```bash
# Via GitHub UI: Select "Rebase and merge"

# Or via CLI:
git checkout main
git pull --rebase origin main
git rebase main feature/42-my-feature
git checkout main
git merge --ff-only feature/42-my-feature
git push origin main
```

This maintains:
- Linear history
- Individual commit attribution
- Atomic, reviewable commits

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description | Version Bump |
|------|-------------|--------------|
| `feat` | New feature | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation only | None |
| `style` | Formatting, no code change | None |
| `refactor` | Code change, no feature/fix | None |
| `perf` | Performance improvement | PATCH |
| `test` | Adding/updating tests | None |
| `chore` | Maintenance tasks | None |
| `ci` | CI/CD changes | None |
| `build` | Build system changes | None |
| `revert` | Reverting a commit | Varies |

### Scope

Scope indicates the area of the codebase:

| Scope | Area |
|-------|------|
| `cli` | Main agents script |
| `tree` | Tree command |
| `list` | List command |
| `show` | Show command |
| `resume` | Resume command |
| `stats` | Stats command |
| `install` | Installation script |
| `release` | Release scripts |
| `docs` | Documentation |
| `man` | Man page |

### Subject Rules

- Use imperative mood: "add" not "added" or "adds"
- Don't capitalize first letter
- No period at the end
- Max 50 characters

### Body Rules

- Wrap at 72 characters
- Explain "what" and "why", not "how"
- Separate from subject with blank line

### Footer Rules

- Reference issues: `Closes #42`, `Fixes #17`, `Refs #99`
- Breaking changes: `BREAKING CHANGE: description`
- Co-authors: `Co-authored-by: Name <email>`

### Examples

#### Simple commit

```
feat(cli): add search command
```

#### Commit with body

```
fix(tree): handle sessions with no messages

Previously, sessions without any user messages would cause
a division by zero error when calculating the summary.

Now we skip empty sessions and display "[empty session]"
as the summary text.

Fixes #17
```

#### Breaking change

```
feat(cli)!: change default depth from 4 to 3

BREAKING CHANGE: The default tree depth is now 3 instead of 4.
Users relying on the previous default should explicitly pass -d 4.

Closes #42
```

#### Multiple footers

```
feat(resume): add session selection prompt

When multiple sessions exist, prompt the user to select
which session to resume instead of defaulting to the latest.

Closes #55
Refs #32
Co-authored-by: Claude <claude@anthropic.com>
```

### Commit Message Validation

Commit messages are validated by CI. Invalid messages will fail the build.

```bash
# Validate locally before committing
echo "feat(cli): add search" | npx commitlint
```

---

## Versioning and Tags

We follow [Semantic Versioning](https://semver.org/) (SemVer).

### Version Format

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
```

| Component | When to Increment |
|-----------|-------------------|
| MAJOR | Breaking changes |
| MINOR | New features (backward compatible) |
| PATCH | Bug fixes (backward compatible) |
| PRERELEASE | Pre-release versions (alpha, beta, rc) |
| BUILD | Build metadata (optional) |

### Examples

```
1.0.0        # Initial release
1.0.1        # Patch release (bug fix)
1.1.0        # Minor release (new feature)
2.0.0        # Major release (breaking change)
2.0.0-alpha  # Alpha pre-release
2.0.0-beta.1 # Beta pre-release
2.0.0-rc.1   # Release candidate
```

### Tag Convention

Tags must match version numbers with `v` prefix:

```bash
# Format
v<MAJOR>.<MINOR>.<PATCH>[-PRERELEASE]

# Examples
v1.0.0
v1.1.0
v2.0.0-alpha
v2.0.0-rc.1
```

### Creating Tags

```bash
# Annotated tag (required for releases)
git tag -a v1.1.0 -m "Release v1.1.0: Add search command"

# Push tags
git push origin v1.1.0
# Or push all tags
git push origin --tags
```

### Tag Message Format

```
Release v<VERSION>: <Summary>

Changes:
- <Change 1>
- <Change 2>
- <...>

Contributors:
- <Name>
- <Name>
```

---

## Release Process

### Release Types

| Type | Branch | Version Example | Process |
|------|--------|-----------------|---------|
| Major | `release/X.0.0` | `2.0.0` | Full release cycle |
| Minor | `release/X.Y.0` | `1.2.0` | Standard release cycle |
| Patch | `release/X.Y.Z` | `1.1.1` | Expedited release |
| Hotfix | `hotfix/X.Y.Z` | `1.1.2` | Emergency release |

### Standard Release Cycle

#### 1. Create release branch

```bash
git checkout main
git pull --rebase origin main
git checkout -b release/1.1.0
```

#### 2. Version bump

Update version in:
- `agents` (AGENTS_VERSION variable)
- `CHANGELOG.md`
- `README.md` (if version mentioned)

```bash
# In agents script
AGENTS_VERSION="1.1.0"
```

#### 3. Update CHANGELOG

Move items from `[Unreleased]` to new version section:

```markdown
## [1.1.0] - 2026-01-15

### Added
- Search command for finding sessions by content

### Fixed
- Tree depth overflow on deep directories
```

#### 4. Create PR and review

```bash
git add -A
git commit -m "chore(release): prepare v1.1.0"
git push -u origin release/1.1.0
gh pr create --title "chore(release): prepare v1.1.0" --base main
```

#### 5. After PR approval and merge

```bash
git checkout main
git pull --rebase origin main

# Create tag
git tag -a v1.1.0 -m "Release v1.1.0"
git push origin v1.1.0

# Build release
./scripts/build-release.sh 1.1.0
```

#### 6. GitHub Release

```bash
gh release create v1.1.0 \
  --title "v1.1.0" \
  --notes-file RELEASE_NOTES.md \
  releases/agents-1.1.0.tar.gz \
  releases/agents-1.1.0.zip \
  releases/agents-1.1.0.sha256
```

### Release Checklist

```markdown
## Release v1.1.0 Checklist

### Preparation
- [ ] All features for this release are merged to main
- [ ] All tests pass on main
- [ ] No critical bugs open for this milestone

### Version Bump
- [ ] Updated AGENTS_VERSION in `agents`
- [ ] Updated CHANGELOG.md with release date
- [ ] Moved unreleased items to version section
- [ ] Updated any version references in docs

### Review
- [ ] Release PR created
- [ ] PR approved by maintainer
- [ ] All CI checks pass

### Release
- [ ] PR merged to main
- [ ] Tag created and pushed
- [ ] Release archives built
- [ ] SHA256 checksums generated
- [ ] GitHub Release created
- [ ] Release assets uploaded

### Verification
- [ ] Installation works: `curl ... | bash`
- [ ] `agents --version` shows correct version
- [ ] Core commands work (list, show, tree, resume)
- [ ] Man page accessible: `agents man`

### Announcement
- [ ] Release notes published
- [ ] Update any external documentation
```

---

## Hotfix Procedure

Hotfixes are for critical bugs in production that cannot wait for the next release.

### Hotfix Criteria

- Security vulnerability
- Data loss or corruption
- Complete feature breakage
- Crash affecting all users

### Hotfix Workflow

#### 1. Create hotfix branch from latest tag

```bash
# Find latest release tag
git describe --tags --abbrev=0  # e.g., v1.1.0

# Create hotfix branch
git checkout v1.1.0
git checkout -b hotfix/1.1.1-fix-path-injection
```

#### 2. Make minimal fix

```bash
# Only fix the critical issue, nothing else
git add -p
git commit -m "fix(cli): sanitize path input to prevent injection

CVE-2026-XXXX: Path input was not sanitized, allowing
arbitrary command execution.

Fixes #99"
```

#### 3. Version bump

```bash
# Update version to patch level
# AGENTS_VERSION="1.1.1"
git commit -m "chore(release): bump version to 1.1.1"
```

#### 4. Expedited PR

```bash
git push -u origin hotfix/1.1.1-fix-path-injection

gh pr create \
  --title "fix(cli): security hotfix v1.1.1" \
  --body "SECURITY HOTFIX - Expedited review requested" \
  --label "priority: critical" \
  --base main
```

#### 5. After merge

```bash
git checkout main
git pull --rebase origin main
git tag -a v1.1.1 -m "Hotfix v1.1.1: Security patch"
git push origin v1.1.1

# Build and release immediately
./scripts/build-release.sh 1.1.1
gh release create v1.1.1 --title "v1.1.1 (Security Hotfix)" ...
```

#### 6. Backport if needed

If supporting multiple major versions:

```bash
# Backport to v1.0.x line
git checkout v1.0.5
git checkout -b hotfix/1.0.6-security
git cherry-pick <commit-hash>
# Continue with version bump and release
```

---

## Rebase Workflow

We use rebase to maintain linear history. **Never merge main into feature branches.**

### Keeping Branch Updated

```bash
# On your feature branch
git fetch origin
git rebase origin/main

# If conflicts occur:
# 1. Resolve conflicts in each file
# 2. git add <resolved-files>
# 3. git rebase --continue
# 4. Repeat until complete

# Force push (safe for feature branches)
git push --force-with-lease origin feature/42-my-feature
```

### Interactive Rebase (Cleaning Commits)

Before creating a PR, clean up your commits:

```bash
# Rebase last N commits interactively
git rebase -i HEAD~5

# Or rebase all commits since branching from main
git rebase -i origin/main
```

In the editor:
```
pick abc1234 feat(cli): add search command
squash def5678 WIP: search progress
squash ghi9012 fix typo
pick jkl3456 test(cli): add search tests
reword mno7890 docs: update readme
```

Commands:
- `pick` - Keep commit as-is
- `reword` - Keep but edit message
- `squash` - Combine with previous commit
- `fixup` - Combine with previous, discard message
- `drop` - Remove commit entirely

### Golden Rules of Rebasing

1. **Never rebase public/shared branches** (main, release/*)
2. **Always use `--force-with-lease`** not `--force`
3. **Rebase before creating PR**, not after reviews start
4. **If PR has reviews**, ask before rebasing

### Force Push Safety

```bash
# Safe: checks if remote has new commits
git push --force-with-lease origin feature/42-my-feature

# Dangerous: never use on shared branches
git push --force origin feature/42-my-feature  # AVOID
```

---

## Code Review Standards

### Reviewer Responsibilities

1. **Correctness**: Does the code work as intended?
2. **Design**: Is this the right approach?
3. **Readability**: Is the code clear and maintainable?
4. **Security**: Are there any vulnerabilities?
5. **Testing**: Is there adequate test coverage?
6. **Documentation**: Are changes documented?

### Review Checklist

```markdown
## Code Review Checklist

### Correctness
- [ ] Logic is correct
- [ ] Edge cases handled
- [ ] Error handling appropriate
- [ ] No regressions introduced

### Design
- [ ] Follows existing patterns
- [ ] No over-engineering
- [ ] Changes are focused
- [ ] No unnecessary dependencies

### Quality
- [ ] Code is readable
- [ ] Variables/functions well-named
- [ ] No dead code
- [ ] No debug code left in

### Security
- [ ] Input validated
- [ ] No injection vulnerabilities
- [ ] No sensitive data exposed
- [ ] Permissions checked

### Testing
- [ ] Tests included for new code
- [ ] Existing tests pass
- [ ] Edge cases tested

### Documentation
- [ ] README updated if needed
- [ ] CHANGELOG updated
- [ ] Man page updated if needed
- [ ] Code comments where necessary
```

### Review Comments

Use conventional prefixes:

| Prefix | Meaning | Action Required |
|--------|---------|-----------------|
| `blocking:` | Must be fixed before merge | Yes |
| `suggestion:` | Consider this improvement | Optional |
| `question:` | Need clarification | Response needed |
| `nitpick:` | Minor style issue | Optional |
| `praise:` | Highlighting good work | None |

Examples:
```
blocking: This allows command injection via unsanitized input

suggestion: Consider extracting this into a function for reuse

question: Why did you choose this approach over X?

nitpick: Extra whitespace on line 42

praise: Great error message, very helpful for debugging
```

### Review Response Time

| Priority | Initial Response | Full Review |
|----------|------------------|-------------|
| Critical/Hotfix | < 2 hours | < 4 hours |
| High | < 1 day | < 2 days |
| Normal | < 2 days | < 5 days |
| Low | < 1 week | < 2 weeks |

---

## AI Contributor Guidelines

This section provides guidelines for autonomous AI systems contributing to this project.

### AI Identification

AI contributors must identify themselves:

1. **In commits**:
   ```
   feat(cli): add search command

   Co-authored-by: Claude <claude@anthropic.com>
   ```

2. **In PR descriptions**:
   ```markdown
   ## AI Contribution Notice
   This PR was created by an AI assistant (Claude).
   Human review is required before merging.
   ```

3. **Using labels**: Apply `ai-generated` label to PRs

### AI Commit Guidelines

1. **Atomic commits**: One logical change per commit
2. **Clear messages**: Follow conventional commits strictly
3. **No placeholders**: Never commit TODO, FIXME, or placeholder code
4. **Complete work**: Only commit working, tested code
5. **Explain reasoning**: Use commit body to explain non-obvious decisions

### AI PR Guidelines

1. **Self-review first**: Describe what you checked
2. **List assumptions**: Document any assumptions made
3. **Flag uncertainties**: Highlight areas needing human judgment
4. **Request specific review**: Point reviewers to critical sections

### AI Limitations Disclosure

AI contributors should disclose:
- Areas of uncertainty
- Decisions requiring human judgment
- Potential edge cases not tested
- Security implications needing verification

### Example AI PR Description

```markdown
## Summary
Added search command to find sessions by content.

## AI Contribution Notice
This PR was created by Claude (AI assistant).
Human review required before merging.

## Changes Made
- Added `search` subcommand in `agents`
- Implemented grep-based content search
- Added search examples to man page

## Testing Done
- [x] Manual testing with sample sessions
- [x] Tested empty query handling
- [x] Tested regex special characters

## Areas Needing Human Review
1. **Line 245-260**: Search performance on large session directories
   - I chose simple grep; may need optimization for >1000 sessions
2. **Security**: Search pattern is passed to grep
   - Verified basic escaping, but needs security review

## Assumptions Made
- Sessions are small enough to grep without timeout
- Users expect case-insensitive search by default

## Uncertainties
- Not sure if BSD grep (macOS) handles --include the same way
- May need testing on older bash versions
```

---

## Conflict Resolution

### Merge Conflicts

When rebasing causes conflicts:

```bash
git rebase origin/main
# CONFLICT in file.sh

# 1. Open conflicted file
# 2. Look for conflict markers:
<<<<<<< HEAD
# Your changes
=======
# Their changes
>>>>>>> origin/main

# 3. Resolve by keeping correct code (or combining)
# 4. Remove conflict markers
# 5. Stage and continue
git add file.sh
git rebase --continue
```

### Process Conflicts

When multiple people work on same area:

1. **Communicate early**: Comment on issue before starting work
2. **Check for WIP**: Look for open PRs before branching
3. **Coordinate splits**: Agree on who does what
4. **Sequential merging**: Coordinate merge order if needed

### Dispute Resolution

For disagreements on approach:

1. **Discuss in PR**: Document reasoning
2. **Seek third opinion**: Request additional reviewer
3. **Maintainer decides**: Final call by project maintainer
4. **Document decision**: Record reasoning for future reference

---

## Security

### Reporting Vulnerabilities

**Do not open public issues for security vulnerabilities.**

1. Email: [security contact - to be configured]
2. Include: Description, reproduction steps, impact assessment
3. Allow: 90 days for fix before public disclosure

### Security Review Checklist

```markdown
## Security Checklist

### Input Validation
- [ ] All user input validated
- [ ] Path traversal prevented
- [ ] Command injection prevented
- [ ] No eval of user input

### Data Protection
- [ ] No secrets in code
- [ ] No sensitive data in logs
- [ ] Secure file permissions

### Dependencies
- [ ] No new dependencies added
- [ ] Existing dependencies up to date
- [ ] No known vulnerabilities
```

### Handling Secrets

- Never commit secrets, tokens, or credentials
- Use environment variables
- Add sensitive files to `.gitignore`
- Rotate any accidentally committed secrets immediately

---

## Quick Reference

### Common Commands

```bash
# Start new feature
git checkout main && git pull --rebase origin main
git checkout -b feature/42-my-feature

# Keep updated
git fetch origin && git rebase origin/main

# Clean commits before PR
git rebase -i origin/main

# Push feature branch
git push -u origin feature/42-my-feature
git push --force-with-lease origin feature/42-my-feature  # after rebase

# Create PR
gh pr create --title "feat(cli): add feature" --body "..."

# After PR merged, cleanup
git checkout main && git pull --rebase origin main
git branch -d feature/42-my-feature
```

### Commit Message Cheat Sheet

```bash
feat(scope): add feature          # New feature
fix(scope): fix bug               # Bug fix
docs(scope): update docs          # Documentation
style(scope): format code         # Formatting
refactor(scope): restructure      # Refactoring
perf(scope): improve performance  # Performance
test(scope): add tests            # Testing
chore(scope): maintenance         # Chores
ci(scope): update CI              # CI/CD
```

### Branch Cheat Sheet

```bash
feature/42-description   # New features
fix/42-description       # Bug fixes
hotfix/42-description    # Urgent fixes
docs/42-description      # Documentation
refactor/42-description  # Refactoring
test/42-description      # Tests
chore/42-description     # Maintenance
release/1.2.0            # Releases
```

---

## Appendix: Git Configuration

Recommended git configuration for contributors:

```bash
# Set rebase as default pull strategy
git config --global pull.rebase true

# Set push default to current branch
git config --global push.default current

# Enable rerere (reuse recorded resolution)
git config --global rerere.enabled true

# Helpful aliases
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.st status
git config --global alias.lg "log --oneline --graph --decorate"
git config --global alias.sync "!git fetch origin && git rebase origin/main"
```

---

*Last updated: 2026-01-06*
*Version: 1.0.0*
