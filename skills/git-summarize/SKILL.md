---
name: git-summarize
description: >-
  Summarize all project changes, stage and commit them, push to remote,
  and create a PR to master. Use whenever the user wants to commit and
  create a pull request with auto-generated change summaries.
allowed-tools: Bash
user-invocable: true
argument-hint: "[branch-name] [base-branch]"
---

# Git Summarize & PR

This skill summarizes all pending changes in the project, stages them, creates a meaningful commit, pushes to the remote, and opens a pull request to the `master` (or specified base) branch.

## Workflow

Execute the following steps in order. If any step fails, stop and report the error to the user.

### Step 1: Detect the base branch

Check if `master` branch exists:
```bash
git branch --list master
```
If `master` does not exist, check for `main`:
```bash
git branch --list main
```
If `$2` is provided, use that as the base branch instead:
- `$ARGUMENTS` -- if the user provides two arguments like `/git-summarize feature-branch develop`, then `$2` is the base branch.

### Step 2: Verify there are changes to commit

```bash
git status --porcelain
```
If there are no changes, inform the user there is nothing to commit and stop.

### Step 3: Get the full diff of all changes

```bash
git diff HEAD
```
Also get untracked files separately:
```bash
git diff --cached
```
Check for untracked files:
```bash
git ls-files --others --exclude-standard
```

### Step 4: Generate a summary

Based on the output from Step 3, generate a short but meaningful summary of the changes. The summary should:

- Group related changes together
- Mention new files, modified files, and deleted files
- Highlight the purpose of the changes (new feature, bug fix, refactor, etc.)
- Be written in past tense

### Step 5: Stage all changes

```bash
git add -A
```

### Step 6: Commit with the summary

Omit the `-m` flag to allow the commit message editor to open. The user can edit the auto-generated message if needed. If your instructions require a non-interactive commit, use the summary as the commit message:

```bash
git commit -m "<summary>"
```

### Step 7: Determine the current branch

```bash
git rev-parse --abbrev-ref HEAD
```

If the first positional argument `$1` was provided, use that as the branch name for the PR.

### Step 8: Push to remote

```bash
git push -u origin <current-branch>
```
If the branch has already been pushed with upstream:
```bash
git push
```

### Step 9: Create the pull request

Use `gh` CLI to create the PR. The base branch is `master` (or `main`, or `$2` if provided):

```bash
gh pr create --base <base-branch> --head <current-branch> --title "<pr-title>" --body "<pr-body>"
```

Where:
- `<pr-title>` is a concise one-line summary of the changes
- `<pr-body>` is a detailed description using the summary from Step 4
- The PR body should include a `## Summary` section and a `## Changes` section

After creating the PR, show the PR URL to the user.

## Edge Cases

- **No git repository**: Check with `git rev-parse --git-dir`. If not in a git repo, stop and inform the user.
- **No changes**: If `git status --porcelain` is empty, inform the user and stop.
- **No `gh` CLI**: Check `which gh`. If not installed, tell the user to install it: `brew install gh` (macOS) and run `gh auth login`.
- **No remote**: Check `git remote -v`. If no remote configured, warn the user.
- **Branch already has a PR**: If `gh pr list --head <current-branch>` shows an existing PR, inform the user instead of creating a duplicate.
- **Uncommitted changes after commit**: Re-check `git status` to ensure everything was committed.

## After Success

Print a summary of what was done:
- What was committed (the commit SHA and message)
- Which branch was pushed
- The PR URL
