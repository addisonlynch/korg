# The follow-up bar

Most candidate `[follow-up]`s turn out to be small, in-scope fixes to the diff's own code that
belong in the review round. Follow-ups are reserved for the rare finding that clears the bar
below. Expected rate: **0–1 per PR**; 2+ in one review signals over-deferral.

## Default: `[fix here]`

Every finding starts as `[fix here]`. It becomes `[follow-up]` only by passing ONE of:

- **(a) Out of scope**: unrelated to the PR's stated purpose AND lives in code this diff
  leaves untouched.
- **(b) Separable & substantial**: deserves its own change AND fixing it here would balloon
  the diff past one self-contained change. Both halves required; "separable" describes every
  finding, so (b) turns entirely on the ballooning half. The most common failure mode: citing
  (b) for fixes of a few lines.
- **(c) Needs a decision/owner**: a product call, cross-subsystem tradeoff, or risky
  expansion where no obvious safe default exists. When one exists, state it in the finding
  and label `[fix here]`.

The test is scope, not size: a minor-but-in-scope finding is fixed now, or labeled `[nit]`
if genuinely optional.

## Automatic disqualifiers (rule out `[follow-up]`)

- **Small fix to the diff's own code.** ≤~15 lines touching files this diff changed is
  `[fix here]`, full stop. (Calibration: a try/except around a new file read, a one-entry
  dict addition, and a 3-line fail-loud guard all belong here.)
- **A cut of code this diff added.** Simplifications and subtractions of the diff's own
  additions shrink the diff, so (b) can never pass; altitude findings on new code are
  `[fix here]`. (Calibration: a 10-line pytest hook replaceable by `-rs`, a column with zero
  readers, and doc sections duplicated by the same PR all belong here.)
- **The PR misses the ticket's intent.** That is `[blocker]`, whatever the fix costs.
- **Same defect, same mechanism, more instances.** When the PR fixes 2 of 14 entries in a
  list, flagging the other 12 completes the fix: `[fix here]`. A different subsystem is
  net-new (see the bar-clearing list below).
- **"Worth confirming intent."** Ask the question inside a `[fix here]` finding; the author
  confirms or fixes in the round. A confirmation request is a review comment.

## What legitimately clears the bar

- Needs external data still to be captured: a fixture from a live provider, a measurement
  (e.g. page load time) before changing behavior.
- Genuine design investigation where no safe default exists.
- Feature expansion beyond the linked ticket (e.g. widening an API field mask past what the
  ticket covers).
- Net-new gaps in a subsystem this diff left untouched (fix PRs cover what broke; a parallel
  module's missing feature gets its own ticket).

## Mechanics

- Every surviving `[follow-up]` carries a one-line reason naming which test (a/b/c) it
  passed and why every disqualifier is ruled out, plus the filed `<team>-N` reference as a
  link; every finding, relabeled or not, survives adjudication.
- **When in doubt, `[fix here]`.** A wrongly-inline fix costs one review round; a
  wrongly-filed ticket ships the defect and taxes backlog grooming.
- **A `[follow-up]` asserts its finding is real.** Verify the claim before it survives.

### Labels on a filed follow-up

File the issue on team `linear.team` through the project's Linear MCP server, labelled per the
taxonomy at `planning.label_taxonomy`.

- **`auto-filed`**: always. The description also opens with the italic filer line, naming
  this bot and the PR the finding came from, as the project's Linear rule specifies for a
  ticket filed by a non-interactive job.
- **Area labels**: you have the diff, so the area is unambiguous: apply the taxonomy's labels
  for the changed path. If nothing clearly fits, apply nothing.
- **`bug`**: when the finding is a defect rather than a gap or an enhancement.
- **Never `agent-ready`.** Queueing a ticket for an unattended agent run is a human act; a
  diff the reviewer read must not be able to start one.
- **A `model:*` label**: when the finding is mechanical (the "net-new gaps in an untouched
  subsystem" or "feature expansion beyond the linked ticket" categories above) and you wrote
  real acceptance criteria into the ticket, so a human can queue it as is. Route from
  `model:opus` / `model:sonnet` / `model:haiku`; never `model:fable`, which marks
  interactive-only work.

  The other two categories are not agent-workable: file them for a human, and use `spike`
  when the deliverable is a document rather than a diff.
