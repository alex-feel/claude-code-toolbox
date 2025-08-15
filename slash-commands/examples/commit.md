---
description: Create conventional commits with automatic staging and pre-commit validation
argument-hint: "[issue-id] [additional context]"
allowed-tools: Bash(git *), Read, Grep
---

# Git Commit Workflow

Ultrathink and reason step by step, laying out a short numbered plan before you output any Git commands, then execute that plan.

## Arguments Processing

Parse `$ARGUMENTS` to understand the context:
- If it starts with `#` or contains issue/ticket ID patterns (e.g., JIRA-123, #456, GH-789), treat it as an issue reference
- If it contains keywords like "no-verify", "skip-hooks", inform user that bypassing hooks is not allowed
- Otherwise, treat it as additional context or instructions for the commit

**Provided arguments**: $ARGUMENTS

## Commit Rules You MUST Follow

### 1. Read Project Conventions

First, check for project-specific commit conventions:

```bash
# Check for CONTRIBUTING.md or similar files
@CONTRIBUTING.md
@.github/CONTRIBUTING.md
@docs/CONTRIBUTING.md
```

If found, follow those conventions strictly. Otherwise, use the fallback conventions below.

### 2. Fallback Conventional Commits

When no project-specific conventions exist, use ONLY these types (no scopes unless explicitly allowed):

- **feat** – a new feature or capability
- **fix** – a bug fix, issue resolution, or revert
- **docs** – documentation-only changes
- **test** – adding, modifying, or fixing tests
- **chore** – maintenance, refactoring, tooling, dependencies
- **ci** – CI/CD configuration and pipeline changes
- **perf** – performance improvements
- **style** – code style/formatting (no logic changes)

### 3. Pre-Commit Preparation

#### Clear the staging area
```bash
# Unstage everything first
git restore --staged :/ 2>/dev/null || git reset

# Verify clean staging
git diff --cached --name-status
```

### 4. Analyze Changes

#### Comprehensive change analysis
```bash
# List all changed files
git status --short

# Show detailed diff for understanding
git diff --stat

# Identify file types and purposes
git diff --name-only | while read file; do
  echo "$file: $(file -b "$file" 2>/dev/null || echo "unknown")"
done
```

### 5. Group Changes Logically

Analyze the changes and group them into atomic, logical commits:

1. **Feature commits** (feat): New functionality
2. **Bug fixes** (fix): Corrections to existing code
3. **Documentation** (docs): README, comments, docs/
4. **Tests** (test): Test files, test utilities
5. **Maintenance** (chore): Dependencies, configs, refactoring
6. **CI/CD** (ci): Workflow files, build configs
7. **Performance** (perf): Optimizations
8. **Style** (style): Formatting, linting fixes

**IMPORTANT**: Never mix different types in one commit!

### 6. Stage and Commit Each Group

For each logical group:

#### Stage files selectively
```bash
# For whole files
git add path/to/file1 path/to/file2

# For partial changes (interactive)
git add -p path/to/file

# For new files with correct permissions
git add --chmod=+x path/to/executable  # if needed

# Verify what's staged
git diff --cached --stat
```

#### Create the commit
```bash
# Commit format with imperative mood, ≤72 chars
git commit -m '<type>: <description>'

# With body (for complex changes)
git commit -m '<type>: <description>

<blank line>
Explanation of why this change is needed.
Do not wrap lines in the body.
Each sentence stays on a single line.

$ARGUMENTS'  # Append arguments if they're issue IDs
```

### 7. Handle Pre-commit Hooks

**CRITICAL**: You MUST fix all pre-commit warnings!

If pre-commit hooks fail:
1. **Read the error messages carefully**
2. **Fix the issues** (never use --no-verify)
3. **Re-stage the fixed files**
4. **Retry the commit**

Common pre-commit fixes:
- **Linting errors**: Fix code style issues
- **Formatting**: Apply required formatting
- **Tests failing**: Ensure tests pass
- **Security issues**: Address vulnerabilities

### 8. Commit Message Best Practices

#### Subject line rules
- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter after type
- No period at the end
- Limit to 72 characters
- Be specific but concise

#### Good examples
```text
feat: implement user authentication with JWT
fix: resolve memory leak in data processor
docs: add API migration guide for v2
test: increase coverage for payment module
chore: upgrade React to v18.2.0
```

#### Bad examples
```text
feat: Updated code  # Too vague, wrong tense
fix: fix bug.      # Redundant "fix", has period
docs: Documentation  # Not imperative
test: tests         # Too vague
```

### 9. Multi-commit Workflow

If changes require multiple commits:

1. **Plan the sequence** (feat → fix → docs → test → chore)
2. **Stage and commit** each type separately
3. **Maintain buildability** (each commit should work)
4. **Reference issues** consistently

### 10. Final Verification

After all commits:
```bash
# Review commit history
git log --oneline -5

# Verify clean working tree
git status

# Check that tests still pass
npm test || yarn test || make test  # Use appropriate command

# Ensure pre-commit passes on all files
git diff --name-only HEAD~$(git rev-list --count HEAD ^origin/HEAD) | xargs pre-commit run --files
```

## Execution Plan

Based on the changes detected, I will:
1. Analyze all modifications
2. Group them by commit type
3. Create atomic commits in logical order
4. Ensure each commit passes pre-commit hooks
5. Verify the final state

Now executing this plan...
