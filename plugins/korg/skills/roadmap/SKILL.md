---
name: roadmap
description: Capture a feature idea or queue a task for the autonomous agent runner as a Linear issue. Use when the user says "add this to the roadmap", "roadmap idea", "future feature", "queue this", "do this tonight", "save this for later", "put this in the backlog", or invokes /korg:roadmap. Pass --auto to scope and mark as agent-ready.
---

# Roadmap

Names like `linear.team` are keys of the project's `.korg.yml`; `korg-config <key>` prints one.
If `linear.team`, `linear.workspace`, `planning.label_taxonomy` or `rules.testing_signal` is
unset, stop: the project has not configured korg's planning layer. Relative paths in it are from the project root, and a leading `~` is expanded. Talk to Linear the way the project's Linear rule in
`.claude/rules/` says, and address teams, labels and states by name.

**`--auto`** (`-a`): scope and queue for the autonomous agent runner: full context grilling, and
the item is marked `agent-ready`. Without the flag, quick capture only.

## Step 1: Get the description (both paths)

Use the argument if provided (the text after `--auto` on the auto path). If none, ask:

- quick capture: "What's the idea?"
- `--auto`: "What do you want the agent to work on?"

Then follow the matching path below, and finish at **Create the work item**.

---

## Quick capture (no flag)

If the description is 4 words or fewer, or lacks a concrete outcome ("improve UI", "better
data"), ask one sharpening question: "What's the specific outcome or user benefit?" Weave the
answer in. Skip if already clear. Then create the work item, with the description = the full
captured text.

---

## Agent-ready (`--auto`)

The agent works autonomously with no way to ask questions mid-run, so the ticket has to carry
everything it needs.

### Step 2: Scope check

Estimate whether this fits in one autonomous run (~2 hours). If larger (a multi-file refactor,
a new subsystem, anything requiring design decisions), say:

> "This sounds larger than one autonomous run. Want to break it down with /korg:to-tickets, or write a PRD first with /korg:to-prd?"

Don't proceed until scoped to ~2 hours.

### Step 3: Hazard check

If `planning.hazards` is set, read that file. It lists what an
unattended run must never do in this project and what a ticket touching a sensitive area must
say. Refuse a task the file forbids; carry any "must say" into the draft's Constraints.

### Step 4: Grill for context (one question at a time, max 4)

1. **Where?** Search the codebase to find the relevant files. Confirm rather than ask; only ask
   if you genuinely can't locate it.
2. **What exactly?** Specific enough to implement without guessing. Skip if already obvious.
3. **Done when?** Do not skip or accept a vague answer. Push for a checkable criterion of the
   kind `rules.testing_signal` allows for this kind of change: classify the change by that file
   first, then ask for the check it names. If the user says "it works", ask "What's the
   specific check?" in that file's terms. If still vague: "Without a clear acceptance criterion
   the agent won't know when to stop. Let's define one before queuing this."
4. **Constraints?** Only if the task touches something the hazards file or a shared utility
   makes sensitive. Skip for most tasks.

### Step 5: Draft

```
## What
<one sentence>

## Where
- `path/to/file` — `Symbol`

## Why
<motivation, if not obvious>

## Investigation steps (if applicable)
1. ...

## Done when
<verifiable, per rules.testing_signal. Not "it works".>

## Out of scope
<adjacent things the agent should NOT do; omit if nothing is obviously adjacent>

## Constraints
<only if relevant; omit otherwise>
```

Show the draft and ask: "Does this look right, or anything to change?" On confirmation, create
the work item with the draft as the description.

---

## Create the work item (both paths)

Create the issue on team `linear.team`:

- `title`: concise, max 60 chars
- `description`: markdown. When the caller is a non-interactive job rather than a person, open
  with the italic filer line the project's Linear rule specifies.
- `labels` (by name), per the taxonomy at `planning.label_taxonomy`: the area and type labels
  that clearly apply, a `model:*` label (below) when the item is a code change, and on the
  `--auto` path `agent-ready`. A multi-ticket initiative becomes a parent issue with sub-issues
  (native hierarchy); stamp `spike` if the deliverable is a document, not a
  diff.

Confirm with a hyperlink built from the response's `identifier`:

- quick capture: `Added to backlog: [<ID> — <title>](https://linear.app/<linear.workspace>/issue/<ID>/)`
- `--auto`: `Queued: [<ID> — <title>](https://linear.app/<linear.workspace>/issue/<ID>/)`

## Model routing

The agent runner picks its model from a `model:*` label. Stamp one on every ticket that will
produce a code change; skip it for research, planning and idea captures with no diff, and for a
`spike` (a doc deliverable: it gets `agent-ready` and no `model:*`). You are the classifier:

| Label | Use for |
|---|---|
| `model:opus` | Multi-file or cross-subsystem changes, subtle correctness, concurrency or data-shape risk, non-trivial algorithms, anything needing design judgment. **Default when unsure.** |
| `model:sonnet` | Localized, well-specified, mechanical work. |
| `model:haiku` | Trivial and fully specified: a string, a constant, a one-line config edit named in the ticket. |
| `model:fable` | Work the user intends to drive interactively. |

**`model:fable` and `agent-ready` never coexist**: Fable runs only in an interactive shell, so
the dispatcher never takes it. On the `--auto` path, route from opus, sonnet or haiku. If the
work genuinely wants Fable, capture it without `--auto` and say so.
