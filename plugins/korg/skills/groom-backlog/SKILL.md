---
disable-model-invocation: true
name: groom-backlog
description: Triage the project's Linear backlog (stale, stuck, unready, mislabelled and duplicate tickets, and ones whose blockers are done), then apply the fixes you approve.
---

# Groom Backlog

Names like `linear.team` are keys of the project's `.korg.yml`; `korg-config <key>` prints one.
If `linear.team`, `linear.workspace`, `planning.label_taxonomy` or `rules.testing_signal` is
unset, stop: the project has not configured korg's planning layer. Relative paths in it are from the project root, and a leading `~` is expanded. Talk to Linear
the way the project's Linear rule in `.claude/rules/` says.

Read the backlog out of Linear, produce a grooming report, then execute the changes the user
approves. This is the bridge between quick capture (`/korg:roadmap`) and the agent queue, which
needs `agent-ready` plus acceptance criteria. Labels are applied at capture, so grooming is the
backstop.

**This skill never invents work.** No new feature tickets, no new abstractions, no scope
expansion. Propose cuts and clarifications, not additions.

## Scope flag

- (default): the whole open backlog: `Backlog`, `Needs Shaping`, `Todo`, and anything stuck in
  `Needs Human`.
- **`--new`** (`-n`): only the untriaged slice: open items with no type label (`bug`, `chore`,
  `idea`, `spike`) and no `agent-ready`.

## Step 1: Pull the backlog

List team `linear.team`'s issues in each in-scope state, paging as needed (`--new` filters the
result client-side). For each, capture `identifier`, `title`, `state`, `labels`, `updatedAt`,
`createdAt`, whether the description is empty, the parent if set, and its blocked-by relations
with each blocker's state. Fetch a body only when
Step 3 needs it. If the scope is empty, say so and stop.

## Step 2: Hygiene pass

Flag, with each ticket as a hyperlink:

- **Stale**: no activity in 30+ days. Usually "not yet prioritized", not dead: a **review** item
  with its age. Never pre-fill a Cancel recommendation.
- **Stuck `agent-ready`**: in `Backlog`/`Todo` with `agent-ready` for 14+ days, unclaimed.
  Blocked, mis-scoped, or criteria too weak to pick up. Recommend re-checking the criteria or
  dropping the label.
- **Stuck in `Needs Human`**: a decision is owed. List these first; they block the agent loop.
  Recommend a concrete next action.
- **Newly unblocked**: no `agent-ready`, has blocked-by relations, and every blocker is `Done`
  or `Canceled`. Recommend `agent-ready` when it meets Step 4's bar; it goes under "Make ready"
  with no drafted criteria when it already has a **Done when**.
- **Empty body**: not actionable. Recommend sharpen or cancel.
- **Possible duplicate**: near-identical titles or overlapping scope; search to confirm.
  Recommend merging into the older ticket.

Resolve none of these yourself; they go in the report. Before recommending any re-queue, run
[`reference/requeue-gate.md`](reference/requeue-gate.md).

## Step 3: Readiness pass (the core)

For each code-change candidate, apply the acceptance-criteria convention: at least one
mechanically checkable condition of a kind `rules.testing_signal` accepts. "Make it better" is
not one.

1. Fetch the body.
2. Has a **Done when** (or an older **Acceptance criteria**) section with a checkable statement → ready
   candidate (Step 4). Has none → draft 1 to 3 criteria from the ticket's intent, grounded in
   real files, tests or fields. Present the draft; never apply it silently.
3. Planning, research, spike, parent and idea items that clearly produce no code change are
   exempt; note them as exempt. When ambiguous, require criteria.

The smallest criterion a reviewer could check, not a checklist.

## Step 4: Labeling pass

Propose a label only where one **clearly** applies per `planning.label_taxonomy`; report noise
is the failure mode, so stay quiet when unclear.

- **Type**, only when obvious.
- **Area**, only where it clearly fits.
- **Routing:**
  - `agent-ready`: scoped to ~one autonomous run (~2h) with acceptance criteria, or a `spike`,
    and no blocker that is not `Done` (the runner ignores blocking links).
    The dispatcher strips it on dispatch, so adding it back is a re-queue and needs the gate.
  - `Needs Shaping` (a state): a design decision is owed first; which kind goes in the body.
  - `Needs Human` (a state): an autonomous path handing work to a human (an agent bail, a
    roadmap filing by a non-interactive job). Grooming never moves a ticket into it.

Never mark a non-`spike` ticket `agent-ready` without acceptance criteria. If
`planning.hazards` is set, never mark one `agent-ready` that does what that file forbids an
unattended run to do: route it `Needs Shaping` or leave it for a human. `model:fable` and
`agent-ready` never coexist.

## Step 5: Prioritization pass

Only when `planning.plan` is set and the file has a `## Now` section; otherwise skip and say so.
Flag `Now` items with no ready ticket, and `agent-ready` tickets that map to work the plan
parks. Do not reorder Linear or invent priority where the plan is silent.

## Step 6: Label cross-tab

Default scope only. Run [`reference/cross-tab.md`](reference/cross-tab.md) and fold the result
into the report.

## Step 7: Report and confirm

One report, grouped by action, every ticket a hyperlink
(`https://linear.app/<linear.workspace>/issue/<ID>/`):

```
## Backlog grooming — {scope}, {N} items reviewed

### Decisions owed (Needs Human / stuck)
- [<ID> — title](url) — {why} → suggest: {action}

### Make ready (add criteria + agent-ready)
- [<ID> — title](url) — drafted criteria:
  - {criterion}

### Re-tag
- [<ID> — title](url) — add `bug` → {why}

### Stale — review (no auto-cancel)
- [<ID> — title](url) — untouched 34d; still relevant?

### Duplicate / merge candidates
- [<ID> — title](url) — duplicate of [<ID>](url); cancel newer

### Plan divergence
- Now item "{x}" has no ready ticket

### Label cross-tab
(shape in reference/cross-tab.md)
```

Omit empty sections. Then ask: **"Apply these? (all / pick by number / none)"** Do not mutate
Linear before the user answers.

## Step 8: Execute approved changes

Only what the user approved:

- **Labels and state**, by name. A cancel gets a one-line reason comment. A move into
  `Backlog`/`Todo` or an added `agent-ready` passes the re-queue gate first.
- **Acceptance criteria**: append a `## Done when` section to the description.
- **Duplicates**: copy any unique detail into the survivor, then cancel the loser with a comment
  `Duplicate of <ID>`.

Confirm each change as a hyperlink, then summarize what changed and what is left to decide.

## Guardrails

- Recommend first; mutate only after explicit approval.
- No new feature tickets: that is `/korg:roadmap`, `/korg:to-prd` and `/korg:to-tickets`.
- No story points, sizes or sprints. "Ready" means `agent-ready` plus acceptance criteria.
