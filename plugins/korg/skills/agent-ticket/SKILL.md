---
name: agent-ticket
description: Work ONE specific Linear ticket - implement it and open a review-ready PR via /korg:open-pr --auto, then stop; or run one review fix round on a PR (--ci-respond). The caller supplies the ticket to implement; this skill does not pick. Use when the user invokes /korg:agent-ticket or asks an agent to work a specific ticket end to end.
---

# Agent Ticket

Names like `linear.team` are keys of the project's `.korg.yml`; `korg-config <key>` prints one.
If `linear.team`, `linear.workspace` or `linear.owner` is unset, stop: the project has not
configured korg's agent layer. Relative paths in it are from the project root, and a leading `~`
is expanded. Talk to Linear the way the project's Linear rule in `.claude/rules/` says, and
address teams, labels and states by name, never by id. Below, `<TEAM>` is `linear.team` and "the
owner" is the Linear user named `linear.owner`, resolved by name. The default branch is
`origin/HEAD` (minus the `origin/` prefix), or `main` when that is unset.

Optional keys:
- `commands.worktree_setup`: run inside a new local worktree (env files, dependency install),
  with `{root}` substituted by the main checkout's root.
- `commands.test_one`: runs one test file while implementing, with `{test}` the file and `{root}`
  the main checkout's root.
- `rules.testing_signal`: which tests should exist.
- `agent.extensions`: a project file of extra steps (a skill to load for a ticket label, how to
  capture evidence, a nudge to post after the PR opens). Read it at Step 2 and follow each step
  where it says it applies.
- `evidence`: the change types whose PR must carry run output (see Step 3).
- `planning.hazards`: what an unattended run must never do (see the decision gate).

## Inputs

**`TICKET_ID`**, required except with `--ci-respond` (which works the PR it runs on and takes
none): an env var (CI) or the skill argument (`/korg:agent-ticket 42` or
`/korg:agent-ticket <TEAM>-42`), in any order with the flags. Strip the `<TEAM>-` prefix to get the
number `N`. Without `--ci-respond`, if it is empty, print `agent-ticket requires a ticket id — invoke as
/korg:agent-ticket <TEAM>-N` and exit non-zero.

## Flags

- (no flag): local run in a worktree. Steps 1-4; you drive any fix round with `@claude`.
- `--ci-implement`: unattended, on the GitHub Actions job checkout. Steps 1-4.
- `--ci-respond`: one fix round on a PR (Step 5).

Both CI modes follow [`reference/ci-modes.md`](reference/ci-modes.md) as well.

## Queue and Linear writes

The queue is the Linear `agent-ready` label. The dispatcher consumes it at dispatch (an atomic
`issueRemoveLabel` right after `gh workflow run`), so a ticket gets one dispatch whatever its run
does, and re-queueing is a human act. A local run leaves the label as the human set it. The
branch `agent/<TEAM>-N` (no slug suffix) is the ticket's one branch.

Linear's GitHub integration owns every code-ticket state transition; the agent writes state only
where no git event exists:

- **A bail:** a comment saying what the human must decide, then `Needs Human`, assigned to the
  owner, and `agent-ready` removed if present. Each bail below says how the run exits.
- **The spike path:** `In Progress` at research start, then `Done`, assigned to the owner.

Write a state and its assignee in **one** issue update, never two: a partial failure must not move
the state without sending the notification. CI talks to Linear as an app actor, so the assignment
is what reaches the owner's inbox. A state this skill needs that the team lacks is an error: say
which, and exit non-zero.

## Step 1: resolve and validate the ticket

Fetch `<TEAM>-N` from Linear; fail fast if it does not exist. Dedup against open PRs by **both**
title and branch:

```bash
gh pr list --state open --search "<TEAM>-<N> in:title" --json number,headRefName
gh pr list --state open --head "agent/<TEAM>-<N>" --json number
```

If either returns a PR, print `<TEAM>-<N> already has open PR #<num>; nothing to do` and exit 0.
**This exit touches nothing**: no label, Linear write, comment or commit. Do not adopt, review or
finish that PR; retrying a ticket that has one is an interactive decision.

## Step 2: judge

Read the full ticket, `agent.extensions` when it is set, and in `--ci-implement` the
`planning.hazards` file when it is set.

### Spike gate

A ticket labelled `spike` (case-insensitive) delivers findings, not code. It takes this path
instead of the gates below:

1. Set state → `In Progress`. This also drops the ticket from the dispatcher's Backlog/Todo
   filter, which matters for a local run that still carries `agent-ready`.
2. If the ticket already carries sufficient findings from a prior run, the comment says so and
   links or summarizes them; otherwise do the research. Fetches follow the project's rules.
3. Post the findings as Linear comments: one record, split into `Part 1/3`, … when longer than
   about 20,000 characters.
4. **The comment is a precondition of `Done`.** Only after the create call succeeded, set state →
   `Done`, assign the owner, and remove `agent-ready`. If no comment could be posted, leave the
   state at `In Progress` and exit non-zero.
5. No branch, worktree or PR. Exit 0 once `Done` is set.

### Criteria-present gate

If the ticket will produce a code change, it must have an **Acceptance criteria** (or **Done when**) section with
checkable conditions. Without one, bail with a comment that the ticket needs that section before
an agent can work it, and exit 0. Planning, research, epic and idea tickets are exempt when their
content clearly means no code change; when that is ambiguous, require criteria. A criterion
checked only after deploy is the owner's to check: the ticket still needs one the run can check,
and the post-deploy one is never a reason to bail.

### Decision gate

Whether a finished diff would *satisfy* the criteria is advisory: implement and let
`pr-review`'s fitness reviewer judge. Whether the ticket leaves you something to decide is a gate.
Bail when any of these holds, with a comment naming each that holds, and exit 0:

- **No clear change.** The ticket does not say what to change.
- **An open question.** The fix depends on something the ticket leaves open: a cause it asks you
  to find, or alternatives ("X, or Y") with no word on which applies. A question is not open when
  the ticket says what to do for every answer you could find.
- **An owner decision.** Satisfying it would spend money, or change something the repo or the
  ticket says the owner decides, and the ticket does not decide it.
- **A hazard** (`--ci-implement` only, when `planning.hazards` is set). It does something that
  file forbids an unattended run, whatever the ticket says.

Bail the same way in `--ci-implement` when satisfying the ticket requires editing
`.github/workflows/`: the app token cannot push workflow files, so the run would fail at the final
push.

### Branch

```bash
BR=agent/<TEAM>-<N>
git fetch origin <default branch>
git fetch origin "$BR" 2>/dev/null && ON_ORIGIN=1 || ON_ORIGIN=
```

- **CI:** with `ON_ORIGIN` (a prior bail's WIP push), `git checkout -b "$BR" FETCH_HEAD`, merge the
  default branch in, read the tip commit and continue from it: a re-queue means the human resolved
  the blocker. Otherwise `git checkout -b "$BR" origin/<default branch>`.
- **Local:** the checkout is the worktree `WT=.claude/worktrees/agent-<TEAM>-<N>`. If it already
  exists, it holds a prior local bail's work: `cd` into it and continue from its state. Otherwise
  create it from the origin branch with `ON_ORIGIN` (`git worktree add "$WT" -b "$BR" FETCH_HEAD`,
  then merge the default branch in), or from `origin/<default branch>` without, then `cd "$WT"` and
  run `commands.worktree_setup` when it is set.

If a branch command fails (for example `agent/<TEAM>-N` exists locally with no worktree), stop and
report the error with a non-zero exit; do not delete or overwrite anything.

## Step 3: implement

Do not write Linear state here: it is integration-owned.

Keep a running log of implementation notes as you go: every decision that was not in the spec,
every departure from the obvious approach, every tradeoff the reviewer should know. Step 4 posts
it; the fix-round responder reads it, the reviewer does not.

Make the smallest change that does all of what the ticket names, the way it names it. A part left
undone or a cheaper approach is not an implementation note: it is the bail at the end of this
step. Only the project's rules override the ticket (a test `rules.testing_signal` excludes, below).
No speculative refactors or adjacent cleanup.
Honor every rule in `CLAUDE.md` and `.claude/rules/`. Run only the test files you are writing or
editing (`commands.test_one`): the regression run happens once, inside `/korg:open-pr`. Before
adding a test, check it against `rules.testing_signal` when set: a test the rule excludes is not
written, even when the ticket asks for one, and the criterion becomes the observable the rule
describes.

**Evidence**: when `.korg.yml` has `evidence.types`, run what each type your diff matches needs
before Step 4, so `/korg:open-pr` can fill `## Evidence`. Evidence that arrives later costs a whole
fix round.

If you understand the ask but cannot see how to do it, or hit a decision only the human can make:
**first preserve the work**. Locally, leave the worktree as it is. In `--ci-implement`, commit and
push it with no PR (`git add -A && git commit -m "WIP — bailed: <reason>" && git push origin "$BR"`),
because the runner is ephemeral. Then bail with a comment saying what you tried (naming the
branch if pushed), and exit non-zero. Never open a partial PR.

## Step 4: open the PR and request review

Run `/korg:open-pr --auto`, with no other flags. Never `--quick`: no human reviews the diff before
commit, so deslop, test-review and security must run. If a gate inside it fails and a couple of
attempts do not fix it, take the Step 3 bail. If its output does not list `needs-review`, bail
(leave the PR open) and exit non-zero.

Then post the implementation notes as a **single PR comment** whose first line is
`**Implementation notes — <TEAM>-N**`, do anything `agent.extensions` says follows the PR, and
**exit**. No model label goes on the PR: the reviewer and responder read the `model:*` label from
the ticket. Do not watch CI or the review.

## Step 5: respond to review (`--ci-respond`)

One stateless fix round, triggered by a human `@claude` or a red `agent-review` check. Procedure:
[`reference/ci-modes.md`](reference/ci-modes.md).

## Rules

- Never push to the default branch, merge, `git push --force`, or commit with `--no-verify`.
- One ticket per run.
- During implement, push only through `/korg:open-pr --auto`; the one exception is the
  `--ci-implement` bail's `WIP — bailed` commit.
- A failure before Step 2 accepts the ticket (setup, auth, a transient environment) exits
  non-zero without touching Linear, so a re-dispatch can retry.
