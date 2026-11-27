# The fan-out

How the orchestrator fetches the ticket, spawns the reviewers, and processes their findings.
The reviewer input contract in `SKILL.md` governs everything here.

## Fetching the ticket (orchestrator, once, before fan-out)

1. Extract the linked ticket identifier `<team>-N` from the PR title prefix `[<team>-N]`, or
   failing that from the head branch name `agent/<team>-N`.
2. Fetch the ticket through the project's Linear MCP server (see its Linear rule in
   `.claude/rules/`). In CI the MCP is the only permitted path (the review workflow's allowlist
   has no Bash entry for it); on a local run `linear-issue <ID>` works as a fallback when the
   MCP is not connected.
3. **An epic PR** carries a `Ticket: <ID>` trailer on some of its commits (read them with
   `gh pr view <PR> --json commits`): one per child the agent built. Fetch each child named
   there the same way. The ticket text every reviewer receives is then the parent's description
   (the objective) followed by each child's full text, in commit order, and the fitness
   reviewer's per-criterion pass walks every child's criteria. A child whose fetch fails is
   named in the summary as unchecked.
4. If no ticket is linked, or the fetch fails, continue: note "no ticket context; fitness
   check skipped" for the summary, skip the fitness reviewer, and spawn only reviewers 2 and 3,
   without ticket text but with everything else their roster entries name.

## Spawning the reviewers

Spawn the reviewers in parallel (one message, one `Task` call per reviewer: three, or two when
fitness is skipped). Each is a read-only analyst: it inspects the diff and the repo and **returns
a list of findings**; every post to GitHub is the orchestrator's, made after collecting the
results. Pass each subagent `REPO`, `PR_NUMBER`, the head SHA, and its inputs per the roster
below. Pass file paths as absolute paths: a subagent does not inherit this skill's directory.

**Pin `run_in_background: false` on every `Task` call** so the turn blocks until every subagent
returns. A backgrounded reviewer ends the turn at "waiting for results", reports success, and
strips `needs-review` with zero findings posted: a silent no-op review.

Each finding a subagent returns must be a record with: `label` (one of `[blocker]` / `[fix here]`
/ `[follow-up]` / `[nit]`), `path`, `line`, optional `start_line`, and `body` text.

## The roster

1. **Fitness reviewer**: fresh context, one question: **does this PR accomplish the ticket's
   intent?** Input: the full ticket (title, description, acceptance criteria) + the full branch
   diff. Two passes; the per-criterion pass is the floor:
   - **Per-criterion pass (the floor):** walk the ticket's acceptance criteria one by one. For
     each criterion, check the diff and run any mechanical verification the criterion names: a
     grep, a named test's existence **and what it actually asserts**, an API field. All
     verification stays read-only: inspect files and run greps; test execution belongs to CI. A
     criterion whose named artifact is absent, or whose named test lacks the assertion the
     criterion requires, is a `[blocker]`, even when the intent looks satisfied. One exception,
     when `rules.testing_signal` is set: a criterion naming a test that rule excludes is void,
     because the author was right not to write it. A criterion checked only after deploy is void
     too: no diff can satisfy it.
   - **Human-only criteria:** a criterion the PR leaves unmet that only a human can meet
     (output from production, or an action the CI account cannot reach) is not a `[blocker]`:
     no fix round can meet it. Return it as an **`[unmet-human]` note**: the criterion verbatim
     and why only a human can meet it. It never gates; `reference/posting.md` step 5 says where
     it goes.
   - **Intent pass (on top):** judge intent as well as letter: a criterion met in substance
     though unmet in wording counts as met once the substance is verified in the diff, and the
     per-criterion floor above always applies; a PR that satisfies every literal criterion while
     missing the point of the ticket is a `[blocker]`.

   Returns only `[blocker]` findings (plus any `[unmet-human]` notes), each naming the criterion
   or the part of the ticket's intent the PR misses, anchored to the most relevant changed line
   or, for an outright omission with no natural anchor, to the first changed file's first
   changed line. A PR that
   accomplishes the ticket returns zero findings. Skipped entirely when there is no ticket
   context.
2. **Correctness & conventions reviewer**: walks every changed file applying
   `reference/correctness-checklist.md` (Test integrity & CI, Comments, Security) and the
   project's stack-specific checklist at `review.checklist`. Pass the subagent both paths plus
   the ticket text; it reads both itself, including running `pr-test-integrity-flag` per the
   **Test integrity & CI** section. Returns `[fix here]` / `[follow-up]` / `[nit]` findings.
   **Diff-scoped** (see constraint below).
3. **Altitude reviewer**: applies the six-question subtraction-only rubric in
   `reference/altitude-review.md`. Also receives the ticket's **acceptance criteria**, with this
   instruction: every deliverable the criteria require is in scope and stays off the cut list.
   Returns `[fix here]` (approach is wrong for the change's job) or `[follow-up]` findings.
   Exempt from the diff-scoped constraint (see below).
   - **Over-specified criteria.** When the criteria fix the *implementation shape* (which files
     exist, how the work is split) and the outcome they describe is reachable with materially
     less code, the reviewer returns one **`[criteria]` note**: the criterion verbatim, and what
     the smaller shape would be. It is not a finding: it names no diff line, is never posted
     inline, and never gates (only the human can amend a ticket, so a fix round cannot resolve
     it, and cutting a criterion-named artifact would trip the fitness reviewer's per-criterion
     floor next round). The orchestrator carries it into the summary per `reference/posting.md`
     step 5. Criteria naming a checkable observation (a grep, a named test, an API field, a UI
     element or browser observable) are what a ticket's acceptance criteria are required to be,
     and are not over-specification.

Pass reviewers 2 and 3 the path of `reference/follow-up-bar.md` alongside their other inputs:
they must apply its bar before labeling any finding `[follow-up]`.

## The diff-scoped constraint (correctness reviewer only)

**The correctness & conventions reviewer reviews the diff as given: its output is findings on
the changed lines, plus notes where the diff depends on untouched code. Code rewrites stay out
of its output entirely, inside or beyond the changed lines, as do alternative implementations
and architectural proposals beyond the changed lines.
When a problem needs more than ~5 lines of fix, it writes a `[fix here]` finding describing the
issue and stops: the author solves it. Code blocks in findings stay under ~5 lines and appear
only when a one-line fix is the clearest way to point at the problem.**

The other two reviewers operate beyond the changed lines, each for a reason its roster entry
already states:

- **Fitness**: a missed-intent `[blocker]` is by definition about work absent from the diff, so
  its scope necessarily extends past the changed lines; its roster entry defines the anchoring
  for omissions, and it returns `[blocker]`s exclusively. Its output is findings: prose only,
  code stays with the author.
- **Altitude**: its whole job is approach-level: it may name that the chosen implementation is
  wrong for the change's job, that a construct lacks a reason to exist, or that a materially
  simpler version exists, i.e. it proposes cuts that span more than the changed lines. It is
  still subtraction-only per its rubric: propose cuts exclusively, and stay silent on an
  already-minimal diff.

## After collection

Record each subagent's **raw** finding count (the length of the list it returned, before dedup).
Then dedup overlapping findings (same file+line+issue → keep one), then **re-adjudicate every
`[follow-up]`** against `reference/follow-up-bar.md`: a `[follow-up]` keeps its label only when
it clearly clears that bar; otherwise relabel it `[fix here]` (or `[blocker]` when the finding's
own text shows the PR misses the ticket's intent). The round-memory check and posting follow, per
the workflow in `SKILL.md`.
