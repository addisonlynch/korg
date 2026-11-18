---
name: open-pr
description: Run /korg:commit (quality gates + commit + push) then open a PR with a structured description. Use when ready to open a PR.
---

# Open PR

Run `/korg:commit` to gate, commit, and push, then draft and open the PR.

Names like `commands.lint` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one. If the file does not exist, stop: the project has not configured korg. Relative paths in it
are from the project root, and a leading `~` is expanded. The default branch is `origin/HEAD`
(`git rev-parse --abbrev-ref origin/HEAD`, minus the `origin/` prefix), or `main` when that is
unset.

Optional keys, each skipping its part when unset:
- `linear.team`, `linear.workspace`: ticket prefixes and links. Ticket ids are `<team>-N`;
  link one as `https://linear.app/<workspace>/issue/<ID>/`. Look ticket titles up through the
  project's Linear MCP server (see its Linear rule in `.claude/rules/`).
- `review.manual_testing`: the project's manual-testing checklists, by area.
- `evidence`: the change types whose run output the PR must carry under `## Evidence`.

## Arguments

Parse `$ARGUMENTS`:
- `--quick` (`-q`): passed through to `/korg:commit` (skips deslop, test-review, security; ignored in CI)
- `--auto` (`-a`): skip the human confirmation checkpoint; open the PR immediately after push
- `--fix-ci`: after the PR opens, poll CI and fix failures (max 3 iterations); no short form

## Phase 1: Commit

Run `/korg:commit` (passing `--quick` if provided). It runs the quality gates, commits, and
pushes the branch. Its scoped test run is the only one this skill makes; no phase runs the full
suite (`${CLAUDE_SKILL_DIR}/../commit/SKILL.md` § Running tests).

If `/korg:commit` stops for any reason, stop here too.

## Phase 2: Draft PR

Show context:
```sh
git log --oneline origin/<default branch>..HEAD
git diff --stat origin/<default branch>...HEAD
```

Draft a **PR title** (under 70 chars). If the change references a `<team>-N` ticket, prepend
`[<team>-N]`: the review bot and the agent runner read the ticket id from it.

Draft a **PR description**. Fill the two `Automated checks` lines with the literal
`commands.lint` and `commands.test` values. Omit `## Tickets resolved` when no ticket is
referenced, and `## Evidence` unless the evidence rule below applies.

```markdown
## Why

[1-2 sentences: problem solved or change motivated]

## What

[Bulleted list. Bold lead per bullet. Ticket bullets: `[<team>-N](https://linear.app/<workspace>/issue/<team>-N/): description`]

## Tickets resolved

[Each as: `- [<team>-N: Title](https://linear.app/<workspace>/issue/<team>-N/)`]

## Automated checks

- [x] `<commands.lint>` passes
- [x] `<commands.test>` passes (the tests this diff calls for; CI runs the full suite)

## Manual testing

**Where to look:** [the page(s), endpoint(s), command(s), or table(s) the change is visible in]
**What is now true:** [the observable result of the change, in one or two lines]
**What must not have changed:** [one sibling the change leaves alone: another type, another source, the other viewport]

[Concrete steps. See § Manual testing below. Steps only: a plan for the reviewer to execute, never results.]

## Evidence

### <name>

[the command that exercised this change type, in a fenced block, followed by its pasted output, in a fenced block. One subsection per matched type.]

Generated with [Claude Code](https://claude.com/claude-code)
```

### Manual testing

When `review.manual_testing` is set, read that file and paste the section(s) matching the paths
the diff touches, filling each box in with the actual command, query, or observation. When it is
unset, write the steps from the diff directly.

**Tests / refactor / docs only**: "No manual testing: `<reason>`" is acceptable. For anything
user-facing or data-changing it is not: when the author cannot observe the change (empty
database, no browser, no credentials), still write the steps for the reviewer to execute, and
say why they were not run.

Three rules bind every non-trivial Manual testing section:

1. **One negative-case step is required.** The empty result, the error branch, the null field.
   The case the author never wrote down is the most common escape class.
2. **Unqualified aggregate pass-conditions are banned for data-pipeline changes.** "N
   discovered / M matched / rate 0.99" is not a pass condition; a destination or row-count
   assertion is. Bugs can improve the aggregate.
3. **Post-merge deferral is a tracked contract.** Deferring ("verify on the next live run")
   requires a named concrete observable (run URL pattern, log line, check state) plus a
   deadline, and the author comments on the merged PR when observed. No named observable is a
   defect in the section itself.

### Evidence

Applies only when `.korg.yml` has an `evidence` key. Read `evidence.exempt` and
`evidence.types` from `.korg.yml` at the project root directly (it is YAML): `korg-config`
prints a nested list as a Python repr or as YAML depending on the installed parser.

Classify `git diff --name-only origin/<default branch>...HEAD`. When every changed file matches
an `evidence.exempt` glob, leave the section out. Otherwise each `evidence.types` entry whose
`paths` match at least one changed file is a matched type, and `## Evidence` gets one
`### <name>` subsection per matched type: the command that ran, in a fenced block, then its
output, in a fenced block, satisfying the type's `need`. A linked CI artifact in the same shape
also counts. With no matched type, leave the section out.

Screenshots do not go here and never satisfy a type: the `pr-review` bot checks only execution
evidence, and fails the `agent-review` check when a matched type's subsection is missing.

## Phase 3: Checkpoint (skip if `--auto`)

Show the drafted title and description. Wait for explicit confirmation before opening.

## Phase 4: Open PR

The PR's base is always the default branch. If the branch is stacked on another branch, rebase
it onto the default branch (or merge the parent in) first: no CI job and no ruleset applies to
another base, so a stacked PR is unreviewable and unblocked.

```sh
gh pr create --base <default branch> --title "<title>" --body "<description>"
```

## Phase 5: Request review

Add `needs-review`, which fires the `pr-review` bot (without it the PR sits BLOCKED):

```sh
gh api --method POST repos/<owner>/<repo>/issues/<PR_NUMBER>/labels -f 'labels[]=needs-review' --jq '.[].name'
```

Use `gh api`: `gh pr edit --add-label` fails on GitHub's sunset Projects-classic query.
If the output does not list `needs-review`, say so and stop. Report the PR URL either way.

## Phase 6: Fix CI (only with `--fix-ci`)

1. Poll `gh pr checks <PR_NUMBER>` every 90 seconds.
2. All pass → report success and stop.
3. Failure → read logs with `gh run view <run-id> --log-failed`, fix locally, then run
   `/korg:commit "fix: <what>"`, which runs the gates, commits and pushes.
4. Repeat. Max 3 iterations. If still failing, report what was tried and stop.

## Stop rules

- Never push to the default branch, `main`, or `master`.
- Never open a PR without explicit confirmation (unless `--auto`).
- Never open a PR against a base other than the default branch.
- Never leave a PR without `needs-review`.
- Never auto-merge.
- Max 3 CI fix iterations.
