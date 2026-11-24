# How to post feedback

**The hard rule: every finding is an inline comment anchored to a specific file and line, posted
via `gh api`. The summary is the ONLY thing that goes through `gh pr review --comment`. There is
no third option.**

Each finding gets its own inline comment so it appears next to the offending code in the Files
tab, where the author addresses it. `gh pr review --comment` carries the summary alone, never
findings; `gh pr comment` and a bundled multi-finding review comment stay unused.

Anchor every inline comment to the head SHA recorded in `SKILL.md` workflow step 1. To use it as
a shell variable, set it in the same call that posts:
```
HEAD_SHA=<the SHA from workflow step 1>
```

Post one `gh api` call per finding:
```
gh api repos/{REPO}/pulls/{PR_NUMBER}/comments \
  -X POST \
  -f body="[fix here] comment text" \
  -f path="relative/path/to/file.py" \
  -F line=42 \
  -f side="RIGHT" \
  -f commit_id="$HEAD_SHA"
```
For multi-line comments, also pass `-F start_line=38 -f start_side="RIGHT"`. Always use
`side="RIGHT"` (new-file side of the diff).

If `gh api` exits non-zero, fall back to one top-level PR comment containing all findings, and
note at the top that inline posting failed.

1. Use `gh api` for every line-specific finding as shown above. Post one call per finding.
2. Tag every inline comment with exactly one label on the first line:
   - `[blocker]`: the PR misses the linked ticket's intent (the fitness reviewer's verdict).
     Must be addressed before the PR can be cleared.
   - `[fix here]`: correctness bug, security issue, hard convention violation, or an altitude
     finding. Must be addressed.
   - `[follow-up]`: **default is fix-now; follow-ups are rare** (expect 0–1 per PR). A finding
     qualifies only by clearing the bar in `reference/follow-up-bar.md`, which is canonical for
     the three qualifying tests, the disqualifiers, and the required reason + `<team>-N`
     mechanics. On agent-authored PRs, `[follow-up]` means "split off into a new ticket": each
     was already filed as its own ticket (its `<team>-N` is inline), and the fix round fixes
     in-scope findings in place while leaving `[follow-up]`s alone, never treating them as
     lower-priority fixes deferred.
   - `[nit]`: verified minor finding beyond a linter's reach (naming, ordering, a lost
     diagnostic string). Whitespace, quotes, import order, and anything a linter handles stay
     out of findings entirely.
3. If the same class of issue appears more than 3 times, flag the first 2–3 inline and note
   "similar issues at <files/lines>" in the summary. Total inline comments should rarely exceed ~15.
4. Never skip a finding or downgrade it to `[nit]` because confirming it needs code outside the
   diff: a PR whose last round has only nits merges with them unfixed. `[follow-up]` requires a
   verified finding.
5. Submit the summary LAST, after all inline comments are posted. First read CI status
   mechanically, from these commands alone:
   ```
   pr-ci-status {PR_NUMBER}                      # CI (CHECK_RUN_ID set)
   gh pr checks {PR_NUMBER} --repo {REPO}        # local (CHECK_RUN_ID unset)
   ```
   The script wraps `gh pr checks` and swaps in `CI_STATUS_GH_TOKEN` (the job's
   `GITHUB_TOKEN`, set on the review step's env by the review workflow) itself: on the CI path
   the ambient `GH_TOKEN` is the App installation token, which lacks checks-read permission, so
   using it there 403s and blinds the review; and the sandbox refuses a `GH_TOKEN=…` command
   prefix, so the swap lives inside the script. On a local/interactive run the ambient `gh`
   auth reads checks fine: use the plain form.
   Run **one** of these, bare. Never chain the two (`pr-ci-status N || gh pr checks N`):
   `gh pr checks` exits non-zero on a merely pending check, so the `||` can fire on a good read
   and re-run the plain form under the ambient App token, which 403s.
   The script may also print a `CI_NOTE: skipped review — <check>` line. A reviewer bot that
   skipped still reports its check green (some skip bot-authored PRs outright), so a named check
   is **not** a passing check: leave it out of the count and never cite it as a reviewer. It is
   a note, not a gate: a skipped reviewer alone does not fail the verdict.
   On the CI path the script's **last line is the verdict; read it, do not infer one**:
   `CI_STATUS: readable` means the rows above ARE the CI signal, and `CI_STATUS: unreadable`
   means no rows came back at all. Only `unreadable` makes CI UNREADABLE: say so in the summary
   and treat it as not-clean (absent never reads green). A clean verdict on an `unreadable`
   read is forbidden, and step 7 must publish `failure`. Do NOT call CI unreadable off a
   non-zero exit or a trailing `GraphQL: Resource not accessible by integration (…)` line when
   rows are present: that is a PARTIAL error on one nested sub-field, and the rows are complete.
   Misreading a partial error as blindness, and signing off clean on a blind read, are each
   independently forbidden.
   `gh pr checks` exits non-zero when a check is failing, pending, or absent, which is expected,
   so read its per-check output either way; the per-check conclusions (after the exclusion
   below), not the exit code, are what step 7 keys off. Record the verbatim per-check
   conclusions, **disregarding both the review workflow's own job and the `agent-review` check
   run**: both are this workflow's own machinery. A red `agent-review` is a predecessor run's
   verdict or corpse. A red or `cancelled` review-job row is this workflow superseded or
   failing closed: the workflow's concurrency is keyed on the PR number, so the documented
   human retry (remove and re-add `needs-review`) cancels the in-flight run and leaves a
   `cancelled` row on this same SHA, and the fail-closed verify step reddens the job after a
   silent no-op. `gh pr checks` reports `cancelled` as a failure, so counting either as failing
   CI would wedge every retry on an otherwise green PR.
   The PR body's `## Automated checks` boxes and any "lint and tests pass" line in the
   description or the author's notes are claims rather than evidence: a claimed-green PR can
   break the default branch, and this review has no local gate that could verify them. Read CI
   here, at sign-off time, so it describes the PR as it stands when you sign off rather than as
   it stood before a multi-minute fan-out. Then run the **evidence-presence and provenance
   checks** in `SKILL.md` (one PR-body-and-comments read serves both; provenance additionally
   reads the inline review comments).

   Then submit:
   ```
   gh pr review {PR_NUMBER} --repo {REPO} --comment --body "<summary>"
   ```
   The summary is a **header, not findings**. Format:
   - **First line, bold:** label counts, e.g. `**1 blocker, 2 fix-here, 1 follow-up**` or
     `**No blocking issues found.**`
   - **Second line:** each subagent's raw finding count plus the posted total, e.g.
     `reviewers: fitness 1, correctness 6, altitude 2 (9 raw, 7 posted)`. When the fitness
     reviewer was skipped, say so in its slot:
     `reviewers: fitness skipped (no ticket), correctness 6, altitude 2 (8 raw, 7 posted)`. Raw
     must be ≥ posted (dedup and round memory only ever drop findings).
   - **Third line:** the CI status you just read, naming any check that is not passing, e.g.
     `CI: all 4 checks pass` / `CI: backend FAIL, frontend pass, 2 pending`. Pending is a real
     answer: report it as pending, a third value distinct from pass and fail.
   - **Fourth line, present only when evidence is missing:** `Evidence: missing <type> (need
     <what>)` per the evidence-presence check. A satisfied, exempt, unmatched or unconfigured
     check produces no line: the summary has no `Evidence: present` form.
   - **Fifth line, present only when the provenance check hit:** `Provenance: <what was
     bypassed>` per the provenance check in `SKILL.md`. A clean provenance read produces no
     line: the summary has no `Provenance: clean` form.
   - **Sixth line, present only when the altitude reviewer returned a `[criteria]` note:**
     `Criteria: over-specified: <criterion>, reachable with <the smaller shape>` per its roster
     entry in `reference/fan-out.md`. **Never gating**: unlike the evidence and provenance lines,
     this one does not affect the verdict. Only the human can amend a ticket, so it is
     information for them, not work for a fix round.
   - **Seventh line, present only when the fitness reviewer returned an `[unmet-human]` note:**
     `Unmet (human): <criterion>`, one line per note. **Never gating**, like the criteria line:
     a criterion only a human can meet is the owner's to meet, not a fix round's. Before
     submitting the summary, tell the owner on the ticket: read its comments with the Linear
     MCP's `list_comments`, and unless one already starts with `Unmet (human)`, post one with
     `save_comment` that starts `Unmet (human) on <PR URL>:`, mentions the Linear user
     `korg-config linear.owner` names, and quotes each criterion. With `linear.owner` unset,
     skip the comment and say so in the summary's theme sentence.
   - **Then at most one sentence** on overall theme (e.g. "Migration looks safe; one missing
     index flagged inline."). Note here when findings were dropped by round memory.
   - All actual findings, including lists of affected items, files and line numbers, live in
     inline comments on the relevant line; the summary carries zero findings.
6. Submit as a comment review only; approving and requesting changes are the human's actions.
7. **Close the `agent-review` check run with your verdict.** The workflow opened it before you
   started and put its id in the `CHECK_RUN_ID` env var. Check-run writes are GitHub-App-only:
   no `gh api` call under a user token can set this check, so a wedged check is re-run (re-add
   `needs-review` or push a commit), never hand-greened. Clean means you posted **no `[blocker]`
   and no `[fix here]`** findings, **no CI check was failing** when you read it in step 5, the
   evidence-presence check found nothing missing, **and** the provenance check found no bypass
   admission; `[nit]` and `[follow-up]` still count as clean. Severity is assigned when you
   write the finding, and only blocking severities gate.
   A **failing** CI check, an `unreadable` CI read (step 5), missing evidence, and an admitted
   gate bypass (the provenance check) each force the failure verdict, whatever the diff looks
   like.
   **Pending CI stays compatible with a clean verdict**: the bot fires the moment the PR opens,
   so CI is usually still running underneath it, and a pending-fails rule would leave every
   agent PR red. The summary reports the pending status and GitHub shows the human the result.
   - First re-read the head SHA: `gh pr view {PR_NUMBER} --repo {REPO} --json headRefOid -q '.headRefOid'`.
     If it no longer matches the SHA from workflow step 1, a push landed mid-review: **leave the
     check open and skip closing it**, because closing it would vouch for a commit you never
     read. The workflow's finalize step fails it as "Review did not complete" (which dispatches
     no fix round), and the push already queued a fresh review of the new head.
   - Clean → `publish-review-check close success "Clean review" "<summary>"`
   - Otherwise → `publish-review-check close failure "Findings" "<summary>"`

   Call it exactly like that: **literals only, no env vars in the command** (the sandbox
   refuses any command carrying an assignment or `$` expansion, which is why the script takes
   no id argument). It reads `CHECK_RUN_ID` and the token from its own environment, and on a
   local/interactive run (no `CHECK_RUN_ID`) it prints a note and exits 0, so you always run
   it and never need to probe the environment first.

   `<summary>` is one or two lines: the label counts, the CI line, and the evidence and
   provenance lines when they exist. These are the same facts as the review summary's header,
   so the check is readable without opening the review, including why a summary-only gate
   failed it. On agent PRs a failure verdict mechanically triggers the capped fix loop (3
   rounds, then escalation), so label severities deliberately: a `[fix here]` you would not
   spend a fix round on should have been a `[nit]`.

   `gh pr checks` is the sole **CI** signal for this verdict: settle the CI leg from that
   output alone, leaving test execution to CI (findings, evidence, and provenance gate the
   verdict separately, per the clean definition above); mergeability beyond it (conflicts,
   approvals) is still the human's call.
8. **Clear the review trigger, then stop.** The review is *for the human*: fix rounds and
   Linear state belong to others. After posting every finding + the summary, remove the trigger
   label so its absence means "reviewed":
   `gh api --method DELETE repos/{REPO}/issues/{PR_NUMBER}/labels/needs-review` (use `gh api`;
   `gh pr edit` errors on GitHub's sunset Projects-classic query). That label removal is the
   run's final write: responder labels stay untouched, and Linear state stays with the human
   and the GitHub integration (the human drives merge; the integration owns `In Review`/`Done`).
   The human reads your review and decides: merge, request a fix round, fix it themselves, or
   close. This runs the same for agent PRs and human PRs.

**Comment style:**
Good: `[fix here] requests.get is sync; this route is async. Use httpx.AsyncClient or run in a thread.`
Bad: `[fix here] I noticed you're using requests here. While requests is a great library, in async contexts it can sometimes cause issues with the event loop...`
One or two sentences. State the problem. Optionally name the fix. Nothing else: preamble,
apology, and lecture all stay out.
