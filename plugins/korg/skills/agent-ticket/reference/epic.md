# Epic mode: one run, a parent's children, one PR

The ticket is a parent whose children `agent-epic order` accepted. This run builds the children
one at a time, in that order, on the parent's branch, then opens one PR into the default branch.
It replaces the rest of Steps 2-4 for this ticket. `agent-epic`'s header is the contract: which
children count, the refusals, and what makes a child done. Below, `<P>` is the parent's id and
`ORDER` the ids it printed.

Anything this file does not cover is an **epic bail**, not something to work around.

## Epic bail

1. When every child is already done (`agent-epic check <P>` lists none as `todo`), first discard
   what is uncommitted (`git checkout -- . && git clean -fd`): it is a parent-acceptance fix
   that never passed the gates, and a resume finds that gap again. Then commit and push
   whatever is on the branch, with no `Ticket:` trailer:
   `git add -A && git commit --allow-empty -m "WIP — bailed: <child>: <reason>" && git push origin "$BR"`.
   Locally, leave the worktree as it is instead.
2. Bail on the parent per Step 2's Linear rules: a comment naming the child, what stopped it, and
   the children done so far (from `agent-epic check <P>`), then `Needs Human` assigned to the
   owner. Write nothing to the children.
3. Exit non-zero.

Re-queueing the parent resumes from the next child that is not done.

## 1. Pre-flight, before any code

- For each child in `ORDER`, run Step 1's two dedup searches with the child's id. Any open PR is
  a bail before the branch: the child is being built elsewhere.
- Read each child in full and run Step 2's criteria and decision gates on it, the workflow-file
  bail included. A gate that holds for any child is a bail naming that child, before the branch.
- Read the parent's description: it is the objective the finished epic must meet.

## 2. Branch and resume

Take Step 2's **Branch** section as written, with `<P>`'s number: `BR=agent/<P>`.

With `ON_ORIGIN` (a prior bail's push), run `agent-epic check <P>`. Each child it prints `done` is
skipped. Before building the first `todo` child, run `commands.test` on the merged tree: a red
run is an epic bail, because a done child is only trusted while the tests above it pass.

## 3. Each child, in order

For each `todo` child `<C>` in `ORDER`:

1. **Implement in a fresh subagent.** Resolve its model with `resolve-ticket-model <C>` and spawn
   one foreground subagent on that model (`run_in_background: false`). Give it `<C>`'s full text,
   the parent's objective, the subject line of each child already committed, and these rules:
   Step 3's implementation rules and evidence, run only the tests it writes or edits, return
   its implementation notes, and never commit, push or write Linear. A subagent that reports it
   could not do the child is an epic bail.
2. **Check the criteria.** Read `git diff HEAD` against `<C>`'s acceptance criteria. Name, for
   each criterion, the change or test that meets it. A criterion nothing meets goes back to the
   same subagent once; still unmet, it is an epic bail.
3. **Commit through the gates.** `/korg:commit "<C>: <C's title>" --ticket <C>`, invoked anew for
   each child: never `git commit` a child or write its `Ticket:` trailer yourself, since the
   trailer is what tells `agent-epic check` that the gates ran. Its scoped test
   run reads the whole branch against the default branch, so it tests what the earlier children
   built as well as this one. A gate still red after two fix attempts is an epic bail.
4. **Confirm.** `agent-epic check <P>` must now print `<C> done`. Otherwise, epic bail.

Keep each subagent's notes, headed by its child's id, for Step 5.

## 4. The whole epic

1. `agent-epic check <P>` exits 0, or it is an epic bail naming what it printed.
2. **Parent acceptance.** Spawn one fresh foreground subagent with the parent's description,
   every child's full text and `git diff origin/<default branch>...HEAD`. Ask one question:
   does the change as a whole do what the parent sets out to do, and what is missing or
   contradicted? The subagent did not write the code, so it does not grade its own work.
   - A gap that a child's text already asks for is that child's unfinished work: send it back to
     a fresh subagent for that child, commit through the gates with the same `--ticket`, then
     repeat step 4.1 and ask the question again. One such round per run, covering every gap of
     this kind the answer names; a gap left after it is an epic bail.
   - A gap no child asks for, or one that needs a decision, is an epic bail that names it.

## 5. Open the PR

Run Step 4 as written, with these differences:

- The PR title is `[<P>] <parent title>`. `## Tickets resolved` lists the parent and every child.
  `## What` has one bullet per child, in `ORDER`.
- The implementation notes comment holds one section per child, in `ORDER`, then the parent
  acceptance result.

Review and fix rounds then run as for any agent PR. A fix round's commits carry no trailer, and
need none: the children are already on the branch.
