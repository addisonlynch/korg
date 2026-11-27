---
name: commit
description: Run quality gates (lint, test-review, deslop, security, scoped tests) on uncommitted changes, then commit and push. Use instead of git commit directly.
---

# Commit

Run quality gates on the current changes, then commit and push.

Names like `commands.lint` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one. If the file does not exist, stop: the project has not configured korg. The default
branch is `origin/HEAD` (`git rev-parse --abbrev-ref origin/HEAD`), or `main` when that is
unset.

## Arguments

Parse `$ARGUMENTS`:
- First non-flag argument = commit message (generated if not provided)
- `--quick` (`-q`): Gate 1 and Gate 5 only. Ignored in CI.
- `--ticket <ID>`: adds a `Ticket: <ID>` trailer to the commit, the record epic mode reads to
  know which child the commit built (see `agent-epic`). Only a commit that passed every gate
  may carry it: with `--quick` or `--nochecks`, refuse and say why.
- `--nochecks` (`-nc`): skip every gate and go straight to **Commit and push**. The repo's
  pre-commit hooks still run; if one fails or rewrites files, fix the issue and retry until it
  passes. Use only when the user explicitly asks for a raw commit. Wins over `--quick`. Ignored
  in CI.

In CI (`GITHUB_ACTIONS` is `true`) every gate runs, whatever the change's size: no person reviews
an agent's commit before it is pushed, so the gates are the review.

## Pre-flight

1. Assert the current branch is not the default branch. If it is, stop.
2. `git status --porcelain`: if nothing to commit, stop and say so.
3. Show the scope: `git diff --stat HEAD`

## Gate order

Lint → test-review → deslop → security → one scoped regression run → commit. Every gate that
can edit code runs **before** the tests, so the tests judge the tree that is actually committed
and run once.

Invariants:

- An agent mutates, a deterministic check follows. No agent is the last validator of its own
  edit.
- Reviewers never trigger a test suite. A gate that applied fixes is followed by lint only.
- The authoritative run reflects the final tree. Any edit after it earns exactly one re-run
  of `commands.test`.
- Recovery is bounded: one repair round, then stop and report.
- A failure the diff did not cause is not repaired.
- Whole-repository validation belongs to CI.

## Gate 1: Lint

Run `commands.lint`. If anything still fails after auto-fix, stop and report.

## Gate 2: Test review (skip if `--quick` outside CI, or no test files changed)

```sh
{ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | grep -E '(test_|_test\.|\.test\.|/tests/|/__tests__/)'
```
If any match, run `/korg:test-review`. It runs before deslop so deslop reviews the tests as
they will be committed.

## Gate 3: Deslop (skip if `--quick` outside CI)

Run `/korg:deslop`. Its three reviewers MUST run as parallel subagents; a self-graded verdict
in your own context ("diff is clean, nothing to cut") is not a deslop run. If zero subagents
were spawned, the gate did not run: stop and report.

Scope is `git diff HEAD` plus untracked files, not the whole branch: review accuracy degrades on
large diffs, so each commit is reviewed on its own. Whole-branch review happens at PR review.

After applying fixes, re-run Gate 1. Do not run tests here.

## Gate 4: Security (skip if `--quick` outside CI; triggered, not always-on)

Path triggers:
```sh
git diff --name-only HEAD | grep -E '(auth/|middleware|sql|infra/|terraform/|\.env|requirements.*\.txt|package\.json|pyproject\.toml|Dockerfile)'
```

Content triggers:
```sh
git diff HEAD | grep -E '(eval\(|exec\(|subprocess|dangerouslySetInnerHTML|text\(.*f"|execute\(.*f")'
```

If either fires, run `/security-review` (a Claude Code built-in). Advisory findings go in a
note; blocking findings stop before commit. It runs before the regression run so that any edit
it forces is covered by that run.

## Gate 5: Scoped regression run

Run `commands.test` **once**, on the final tree. Green → continue.

Red → one repair round, then stop and report whatever still fails. Read the failures from the
run's output, or from the log it names; never re-run a suite to see output again. For each
failing test, decide its provenance before touching anything:

1. **Not yours.** When `commands.test_one` is set, re-run just that test against the merge-base
   tree. Substitute `{test}` with the test id and `{root}` with the main checkout's root, so the
   command can reach dependencies installed there:
   ```sh
   root=$(git rev-parse --show-toplevel); base=$(git merge-base HEAD "origin/<default branch>")
   tmp=$(mktemp -d); git worktree add --detach "$tmp" "$base" -q
   (cd "$tmp" && <commands.test_one>); git worktree remove --force "$tmp"
   ```
   If it fails there too, the diff did not cause it. The same holds for a test that passes alone
   on both trees and fails only in a full run, when the diff adds no test that mutates process
   state (env vars, module globals): that order-dependence was already there. Edit nothing;
   record it for the PR description and continue.
   When `commands.test_one` is unset, provenance cannot be checked: stop and report.
2. **Test repair.** The fault is in a test file this change added or edited. Fix the test, then
   run `commands.test`.
3. **Production repair.** Otherwise. Fix the code, re-run Gate 1, then run `commands.test`
   again.

## Commit and push

1. Without a message in the arguments, generate one from `git diff HEAD`: one concise line,
   imperative mood. Do not ask the user.
2. Stage and commit. The trailer names no model version: the run model varies per ticket, so a
   fixed name would mislabel commits. With `--ticket <ID>`, `Ticket: <ID>` goes on the line
   above `Co-Authored-By`, in the same paragraph, or git does not read it as a trailer.
   ```sh
   git add -A
   git commit -m "<message>

   Co-Authored-By: Claude <noreply@anthropic.com>"
   ```
3. `git push -u origin <branch>`
4. Report: branch, commit SHA, push confirmation.

## Stop rules

- Never commit to the default branch, `main`, or `master`.
- Never commit without a message (generated or provided).
- If a gate fails and cannot be auto-fixed, stop before committing.
- `--nochecks` (outside CI) skips the gates, not the pre-commit hooks: never bypass a hook with
  `--no-verify`.
