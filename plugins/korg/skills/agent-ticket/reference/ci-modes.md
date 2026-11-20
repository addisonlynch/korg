# CI modes: `--ci-implement` and `--ci-respond`

## Single-turn contract (both modes)

**Nothing re-invokes a CI run.** Ending your turn ends the job: there is no wake-up when a
subagent finishes, a Monitor fires or a long fetch completes. So run every subagent in the
foreground and collect its result within the turn, and never set up a Monitor or wait on a
notification. Stay in the turn until the deliverable (PR, findings comment or bail) is posted; a
run that ends on "kicked off…" or "waiting for…" has none, and the outcome classifier reds it.

## `--ci-implement`

You declare no outcome: the job's `agent-run-outcome` step classifies the run from evidence. A new
open PR is success, and so is a ticket left `Done` (spike) or `Needs Human` (bail) with no PR.
Anything else reds the run. Nothing checks that `needs-review` landed, so Step 4's check is the
only one. The job has already installed dependencies.

## `--ci-respond`: one fix round

It fires when the human reviewer `@claude`s on a PR (a comment, an inline comment or a review
summary) or when korg's review loop acts on a red `agent-review` check. The job runs on the PR's
branch checkout. On a loop round the prompt names the round number; the workflow counts rounds,
enforces the cap and escalates. A respond round never writes Linear.

**Read the WHOLE PR**: the diff, every inline review comment, the `pr-review` bot's review, the
`**Implementation notes**` comment, and CI status. A human comment scopes the round when it says
something specific; otherwise (and always on loop rounds) address every actionable review comment:
an explicit "change X to Y", "this is wrong" or "missing Y", or a `pr-review` `[blocker]`/`[fix
here]`. Skip `[nit]` and `consider`/`might want to` prose: only blocking severities gate the check.
A merge conflict or a red check is a normal fix (merge the default branch and resolve; or `gh run
view <run-id> --log-failed` and fix), **except** the `agent-review` check and the
`review / claude-review` job. `agent-review` is red by design when the verdict has findings, and
`review / claude-review` can sit red or cancelled for reasons that are not a verdict (a superseded
run, the fail-closed verify step). Treat both as this machinery's own state, as
`../../pr-review/reference/posting.md` step 5 does, never as a CI failure to chase.

When the verdict asks for evidence, add it to the PR body's `## Evidence` section: read the body
with `gh api repos/$REPO/pulls/$PR --jq '.body // ""'`, splice in the subsection, and write it back
with `gh api --method PATCH repos/$REPO/pulls/$PR -F body=@-`. Post it as a PR comment only if the
PATCH fails.

Treat every `[follow-up]` as `[fix here]` unless it clears the bar in
`../../pr-review/reference/follow-up-bar.md`; one that clears it already has its own ticket and is
left alone.

Commit and push with `/korg:commit "Address review — <TEAM>-N"` (never a raw `git commit`, never
`--quick`). Then **reply to each review thread you addressed** with the fix (resolve it if you
can) and **stop**: this is ONE round. Do not re-request review or loop: your push re-runs the
review on agent branches, and the fresh verdict decides what happens next.
