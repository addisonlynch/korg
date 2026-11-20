# KORG label taxonomy

Every label on the KORG team, and when to apply it. A label earns its place only if you would
run the query **and** the answer would change what you do.

Apply labels at creation, by name.

## Update protocol

This file changes first; Linear second. Adding, renaming or retiring a label means editing this
file, then making the change in Linear with the description matching its row here. No sync
surface (GitHub issues included) may introduce a label outside this file.

## Type: `Type` group, one per ticket

`chore`, `idea`, `spike`, and `bug` (a workspace-level label, so it sits outside the group).
Apply only when obvious; shaped feature work carries no type label.

- `bug`: something is broken.
- `chore`: maintenance with no behaviour change for a consuming project.
- `idea`: unshaped, captured for later.
- `spike`: the deliverable is a document or finding, not a code change. May be `agent-ready`;
  carries no `model:*` label.

## Model: `Model` group

`model:opus`, `model:sonnet`, `model:haiku`, `model:fable`. The runner's model routing input,
read by name. `model:fable` is never dispatched: Fable runs only interactively, so it never
coexists with `agent-ready`.

## Dispatch and provenance

- `agent-ready`: an agent may take this. Set by a human, or by pr-review on a mechanical
  follow-up. The runner removes it when it claims the ticket. Means claimable, not claimed.
- `auto-filed`: created by a machine (pr-review follow-ups). Provenance, not a hold.

## Not labels

| Concern | Where it lives |
|---|---|
| Epics | Native parent/sub-issues and projects |
| Shaping owed | **Needs Shaping** status; what kind goes in the body |
| A human decision owed | **Needs Human** status |
| Ready to merge | **Ready to Merge** status |
| Priority | Linear's priority field |

`Feature` and `Improvement` are Linear's workspace defaults. They are not in this taxonomy, so
don't apply them.
