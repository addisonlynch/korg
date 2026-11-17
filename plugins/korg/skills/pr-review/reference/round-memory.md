# Round memory (orchestrator, after collection, before posting)

This is the single sanctioned read of review threads in the whole run (the one exception to the
reviewer input contract in `SKILL.md`, and it belongs to the orchestrator, never a reviewer).
Fetch prior rounds' inline comments and their replies (on a first-round PR this returns nothing
and the check is a no-op):

```
gh api repos/{REPO}/pulls/{PR_NUMBER}/comments --paginate
```

Filter the candidate findings against them:

- **Never re-file a dismissed finding.** If a prior thread raised the same issue and it was
  dismissed with a reasoned reply, by the human or by the responder with the human's assent,
  drop the candidate, however it is reworded. A dismissal you merely disagree with is still a
  dismissal.
- **A reversal must name what it reverses.** If a candidate objects to code that exists because a
  prior round's finding demanded it (round 2 forced a change, round 3 filed a blocker against
  that same change), it may be posted only if its body names that prior decision and justifies
  the reversal; otherwise drop it.
- **A genuinely new finding passes untouched on a first review.** No prior thread covering it →
  post it normally. On a re-review, its *severity* is bounded by the admissibility rule below;
  round memory itself still never drops it.

## Re-review admissibility (the convergence rule)

Applies only when a prior bot review exists on the PR (the fetch above returned threads). Your
job in round N is re-verifying the prior rounds' findings against the new commits: the check
must green when those are resolved, and a reviewer that keeps finding one fresh nit per round
on code nobody touched must never keep the loop alive or escalate a clean PR.

A candidate finding with **no prior thread** is admissible at a gating severity
(`[blocker]` / `[fix here]`) only when the code it flags **changed since the previously
reviewed commit**:

1. The previously reviewed SHA is the newest prior review's `commit_id`
   (`gh api repos/{REPO}/pulls/{PR_NUMBER}/reviews`, last entry: every round submits a
   summary review per the completion contract, so this exists on every re-review even when
   the prior round posted no inline comments). Fall back to the newest prior inline
   comment's `original_commit_id` only if the reviews read fails.
2. `gh api repos/{REPO}/compare/{PRIOR_SHA}...{HEAD_SHA}`: the files and patch hunks that
   actually changed between rounds.
3. Anchored inside that changed set → post at whatever severity it earns. The previous round's
   own fixes can genuinely introduce bugs, and those must gate.
4. Anchored on a surface unchanged since the prior round → post as `[nit]` (or `[follow-up]`
   when it clears that bar), noting it was surfaced on a re-review. Never `[blocker]` or
   `[fix here]`: it stays visible to the human without burning a fix round. If it is real, the
   human promotes it; the loop does not.
