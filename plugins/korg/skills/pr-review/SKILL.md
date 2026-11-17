---
name: pr-review
description: Use when reviewing a pull request. Triggers on requests like "review this PR", "look at PR #123", or any GitHub PR URL. Posts inline comments via gh api and a final summary via gh pr review --comment. Do NOT use for code review of uncommitted local changes.
---

# PR Review

Names like `review.checklist` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one. If `linear.team`, `linear.workspace`, `review.checklist` or `planning.label_taxonomy` is
unset, stop: the project has not configured korg's review layer. Relative paths in it are from
the project root, and a leading `~` is expanded. Talk to Linear through the project's Linear MCP
server (see its Linear rule in `.claude/rules/`), and address teams, labels and states by name.
Ticket ids are `<team>-N`, where `<team>` is `linear.team`; link one as
`https://linear.app/<workspace>/issue/<ID>/`, where `<workspace>` is `linear.workspace`.

Two keys are optional: `evidence` turns on the evidence-presence check below, and
`rules.testing_signal` gives the fitness reviewer its void-criterion exception
(`reference/fan-out.md`).

You are reviewing a pull request. Your job is to catch real bugs, security issues, violations of
project conventions, approach-level over-engineering, and PRs that miss the point of their
ticket. Leave style to the project's linters and formatters.

You are the **orchestrator**: you fan out into parallel subagent reviewers, collect their
findings, dedup, run the round-memory check, and post every surviving finding, subject to
the repetition cap in `reference/posting.md`.

The detail lives in reference files; the workflow below names the file to read at each step.
Read each one only when you reach its step.

## Completion contract

**The review is done when every finding is posted as an inline comment AND the summary is
submitted via `gh pr review --comment`, all within this run.** Run the subagents in the
foreground, wait for every reviewer you spawned, post every finding, submit the summary, close
the `agent-review` check run with your verdict (or deliberately skip closing it, per
`reference/posting.md` step 7), and remove `needs-review`. Ending the turn after only fan-out or
only collection silently no-ops the review: `needs-review` is stripped and the human sees an
approved-looking PR with no review.

## Reviewer input contract

**Reviewers receive the diff and the ticket only.** Sycophancy toward the author's narrative is
structural, beyond what prompting can remove, so the excluded inputs are excluded absolutely:

- Each reviewer subagent receives: `REPO`, `PR_NUMBER`, the head SHA, the ticket text you fetched,
  and the file paths named in its roster entry. It reads the diff itself (`gh pr diff`) and
  inspects the repo tree as needed.
- The PR description, the author's implementation notes (in CI the implementing agent posts an
  `**Implementation notes — <team>-N**` PR comment: the author's own account, for the human and
  the fix-round responder), PR comments, and review threads stay outside every reviewer's input:
  pass none of them in, and instruct each subagent to leave them unfetched.
- **Scoped exceptions, all orchestrator-only:** the round-memory check (workflow step 5) reads
  prior rounds' review threads, and the evidence-presence and provenance checks (workflow
  step 6) read the PR body and comments. These reads belong to the orchestrator alone.
- You, the orchestrator, stay clean otherwise: fetch `title`, `headRefName`, and `headRefOid` from
  `gh pr view --json`, and read the PR body only for the evidence-presence and provenance checks.

## Evidence-presence check (run by the orchestrator, in workflow step 6)

Skip this section entirely when `.korg.yml` has no `evidence` key. Read `evidence.exempt` and
`evidence.types` from `.korg.yml` at the project root directly (it is YAML): `korg-config`
prints a nested list as a Python repr or as YAML depending on the installed parser.

```yaml
evidence:
  exempt: ["**/*.md", ".claude/**", ".github/**"]   # every changed file matches → exempt
  types:
    - name: Migration          # the ### subsection heading
      paths: ["db/migrations/**"]
      need: post-migrate assertion output (a query result or migration-status output)
```

Before a clean verdict, check that the PR carries its type's execution evidence in its one
required location, the PR body's `## Evidence` section. **Presence only**: the check asks
whether the required subsection exists, not whether its content looks right. A wrong pasted
output is a review finding, and the PR still passes this check.

1. Classify the PR from `gh pr diff {PR_NUMBER} --repo {REPO} --name-only`. When *every* changed
   file matches an `evidence.exempt` glob, the PR is exempt and the check produces nothing; a
   single file outside them drops the PR through to the types. Every `evidence.types` entry
   whose `paths` match at least one changed file is a matched type. A PR can match several, and
   each needs its own evidence. A PR matching no type needs none.
2. Read the PR body and comments (`gh pr view {PR_NUMBER} --repo {REPO} --json body,comments`)
   for a `## Evidence` section with a `### <name>` subsection per matched type. Evidence is
   present for a type only when its subsection holds a fenced command and a fenced output, or a
   linked CI artifact in the same shape. Prose describing a run, and evidence sitting in
   `## Automated checks`, `## Manual testing` (steps only, never results), or an
   implementation-notes comment, do not count: `## Evidence` is the PR's one home for this. The
   one exception is the fix-round fallback: a round that produces the missing evidence either
   edits it into the body's `## Evidence` section or, failing that, posts it as a PR comment, so
   check both when evaluating a PR mid fix-loop.
3. Missing evidence on any matched type fails the `agent-review` check (`reference/posting.md`
   step 7). Its sole surfacing is a summary line, same pattern as the CI-status line:
   `Evidence: missing <type> (need <what>)`, with `<what>` the type's `need`. Present evidence
   needs no summary mention.

**Screenshots are never checked here, and an image never satisfies a type.** Every type asks
for the output of something that ran, and a picture is not that. A fix round can produce any
execution evidence, but it cannot capture or publish a screenshot, so a missing-screenshot
failure could only be cleared by a human. A missing or wrong screenshot is still fair game as an
ordinary review finding; it is not this check's business.

## Provenance check (run by the orchestrator, in workflow step 6)

Reads the PR body and comments (the same read as the evidence-presence check), plus the inline
review comments (`gh api repos/{REPO}/pulls/{PR_NUMBER}/comments --paginate`: issue comments
and review-thread comments are separate endpoints, and an admission can sit in either). Scan
all of it for admissions of gate or permission **bypass**:

- commits created via `gh api` / the Git Data API instead of the gated `/korg:commit` path
- claims that a denied command (`git commit`, `git push`, a blocked gate) was routed around
- self-reported gate results (test suite, deslop, security) with no CI artifact backing them,
  when the same text admits the gated path was skipped

Any hit is a **gating finding**: name it in the summary (`Provenance: <what was bypassed>`, same
pattern as the CI and evidence lines) and withhold the clean verdict in `reference/posting.md`
step 7. The gates exist because self-reported results are unverifiable, so an admitted bypass
always fails the verdict, whatever the diff looks like. A clean provenance read produces no
summary line.

Like missing evidence, a provenance hit is **summary-only by design**: the admission lives in
the PR's paper trail rather than on a diff line, so it is exempt from the inline-finding
contract and no inline comment is posted for it. Its reason travels in the review summary and
the check-run summary (`reference/posting.md` step 7), which is where a dispatched fix round or
the human reads it.

## Orchestrator workflow

1. `gh pr view {PR_NUMBER} --repo {REPO} --json title,headRefName,headRefOid`: the title (or
   branch name) gives the ticket id; `headRefOid` is the head SHA. That SHA is the commit under
   review: it anchors every inline comment, and `reference/posting.md` step 7 re-checks it before
   labeling. Shell variables vanish between tool calls, so carry the literal value forward
   rather than relying on `$HEAD_SHA` being set later.
2. Read `reference/fan-out.md`. Fetch the ticket and spawn the reviewers as it specifies:
   **three** parallel foreground `Task` calls, or **two** when there is no ticket context (the
   fitness reviewer is skipped; the completion contract then covers those two).
3. Collect the returned findings and process them per the **After collection** section of
   `reference/fan-out.md` (record raw counts, dedup, re-adjudicate every `[follow-up]`).
4. Reviewers and orchestrator are read-only throughout: running tests, starting servers,
   installing dependencies, and modifying code are all out of scope.
5. Read `reference/round-memory.md` and run the round-memory check on the surviving findings.
6. Read `reference/posting.md` and follow it exactly: post each finding inline via `gh api`, run
   the **evidence-presence and provenance checks** above alongside the CI-status read in its
   step 5, submit the summary, close the `agent-review` check run with your verdict, and clear
   `needs-review`. Then stop. Fix rounds and Linear state belong to others: on agent PRs a red
   check triggers the capped fix loop mechanically, and on human PRs the human reads the review.
