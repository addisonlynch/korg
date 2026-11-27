---
disable-model-invocation: true
name: to-tickets
description: Break a PRD, a parent issue, or the current conversation into vertical-slice Linear tickets with native blocked-by links, after the user approves the breakdown.
---

# To Tickets

Names like `linear.team` are keys of the project's `.korg.yml`; `korg-config <key>` prints one.
If `linear.team`, `linear.workspace`, `planning.label_taxonomy` or `rules.testing_signal` is
unset, stop: the project has not configured korg's planning layer. Relative paths in it are from
the project root, and a leading `~` is expanded. Talk to Linear the way the project's Linear rule
in `.claude/rules/` says.

## Step 1: Gather context

Work from the argument if there is one: a parent issue identifier (fetch its body, its comments,
and the PRD its description names), or a PRD path (its `consumed_by` names the parent issue).
Otherwise work from the conversation.

## Step 2: Explore the codebase

If you have not already, read enough of the code to know its current state. Use the project's
vocabulary in titles and descriptions, and respect its decision records in the area you touch.
Look for prefactoring that makes the work easier: make the change easy, then make the easy
change.

## Step 3: Draft vertical slices

Break the work into **tracer-bullet** tickets:

- Each cuts a narrow but complete path through every layer it needs (schema, logic, interface,
  tests): vertical, not one layer of a horizontal split.
- Each is verifiable on its own, by a check `rules.testing_signal` accepts.
- Each fits one autonomous run (~2 hours) in a fresh context.

Give each ticket its **blocking edges**: the tickets that must land before it can start,
prefactoring first.

**Wide refactors are the exception.** One mechanical change whose blast radius fans across the
codebase (rename a column, retype a shared symbol) cannot land green as a vertical slice.
Sequence it expand, migrate, contract: add the new form beside the old; migrate callers in
batches sized by blast radius (per package or directory), each batch a ticket blocked by the
expand and green on its own because the old form still exists; then delete the old form in a
ticket blocked by every batch.

If `planning.hazards` is set, a ticket that touches what it lists says so, and one doing what
it forbids an unattended run to do is not queued (Step 5).

## Step 4: Review the breakdown with the user

Show the breakdown as a numbered list, each with its **title**, what it **blocks on**, and what
it **delivers** end to end. Ask whether the granularity is right, whether each blocking edge
genuinely gates its ticket, and whether any ticket should merge or split. Iterate until the user
approves. Create nothing before that.

When the breakdown is two to four closely related tickets under one parent, ask whether to **run
it as one epic**: one agent run builds every ticket in blocking order and opens a single PR,
which the user reviews and merges once. Without a parent issue from Step 1, an epic needs one:
create it first, its description the objective the tickets add up to.

## Step 5: Publish

Create the tickets on team `linear.team` in dependency order, blockers first, so each one's
edges can point at real identifiers:

- **parent**: the parent issue from Step 1, when there is one
- **blocked by**: Linear's native blocking relation to each blocker
- `title`: concise, max 60 chars
- `labels` per `planning.label_taxonomy`: the area labels for **that ticket**, a `model:*` label
  per `/korg:roadmap`'s model routing, and `agent-ready` **only on a ticket with no blockers**,
  not `model:fable`, that the hazards file does not forbid. The runner ignores blocking links,
  so a blocked ticket queued now could run before its blockers land. **As one epic**: no
  `agent-ready` on any child. Once every child exists, run `agent-epic order <parent>`; when it
  exits 0, put `agent-ready` on the parent only, and otherwise show the user its refusal and
  queue nothing.
- `description`:

```markdown
## What to build
The end-to-end behaviour this ticket makes work, from the user's perspective.

## Done when
- A check `rules.testing_signal` accepts for this kind of change. Never "it works".
```

No file paths or code snippets in tickets, since they go stale. The exception is a snippet from a
prototype that states a decision more precisely than prose (a schema, a type, a state machine):
inline the decision-carrying part and say it came from a prototype.


## Step 6: Confirm

List every ticket as a hyperlink, `https://linear.app/<linear.workspace>/issue/<ID>/`, in
dependency order, marking which are queued now and what each blocked one waits on. For an epic,
say the parent is queued and list the children in the order `agent-epic order` printed.
