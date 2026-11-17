---
disable-model-invocation: true
name: to-prd
description: Synthesize the conversation into a PRD at planning.prd_dir, then create a parent Linear issue with one child ticket per unit of work.
---

# To PRD

Names like `planning.prd_dir` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one. If `linear.team`, `linear.workspace`, `planning.label_taxonomy`, `planning.prd_dir` or
`rules.testing_signal` is unset, stop: the project has not configured korg's planning layer.
Relative paths in it are from the project root, and a leading `~` is expanded. Talk to Linear the way the
project's Linear rule in `.claude/rules/` says.

**Do not interview the user.** Synthesize from the conversation. If critical information is
genuinely missing, ask one focused question before proceeding.

## Step 1: Explore the codebase

Before writing anything, read enough of the codebase to know what already exists that this
feature touches or extends, and any decision records and glossary the project's `CLAUDE.md`
points to. Name things in the project's vocabulary. The PRD is grounded in the actual system,
not a generic spec.

## Step 2: Write the PRD

Write `<planning.prd_dir>/<kebab-case-feature-name>.md`, creating the directory if it is
missing. Open it with this frontmatter:

```yaml
---
question: the one question this PRD answers
decision: the commitment the PRD makes: the bet being taken, and what it rules out
verdict: the scope that survived shaping
consumed_by:
---
```

`decision` is never the parent ticket, which does not exist yet. Step 3 fills `consumed_by`.

```markdown
# PRD: <Feature Name>

**Date:** <YYYY-MM-DD>
**Status:** Draft

## Problem Statement

<What user or system pain does this solve? Specific, one paragraph.>

## Solution

<What we're building, at a high level. One to three paragraphs.>

## User Stories

1. As a <actor>, I want <capability>, so that <benefit>.

One capability per story; 5 to 15 stories depending on scope.

## Implementation Decisions

<Key technical choices: data model, interfaces, algorithm. No file paths, they rot. Snippets
that encode an architectural decision (a schema, a type, a state shape) are fine.>

## Testing Decisions

<What needs tests, of what kind, and the key cases, per the project's testing-signal rule
(`rules.testing_signal`).>

## Out of Scope

<Adjacent things this PRD does not cover.>

## Further Notes

<Open questions, risks, dependencies on other work.>
```

Tell the user the path it was written to.

## Step 3: Create the parent issue

One issue on team `linear.team` that represents the whole feature (native parent/sub-issue
hierarchy):

- `title`: the PRD's feature name, max 60 chars
- `description`: a one-paragraph summary, the PRD's path, and the key out-of-scope items as
  bullets
- `labels`: the area labels that apply to the feature as a whole, per `planning.label_taxonomy`

Keep its `id` for Step 4, and set the PRD's `consumed_by` to its identifier. That closes the
loop between the PRD and the work that acts on it.

## Step 4: Create the child issues

Derive children from the User Stories and Implementation Decisions. Each is independently
actionable by an agent in one session (~2 hours). For each, create an issue on team
`linear.team` with the parent from Step 3:

- `title`: concise, max 60 chars
- `labels`: the area labels for **that child**, not a copy of the parent's; one that fits none
  carries none. A `model:*` label per `/korg:roadmap`'s model routing.
- `description`:

```markdown
## What
One sentence.

## Why
Which user story this satisfies.

## Done when
A check `rules.testing_signal` accepts for this kind of change. Never "it works".
```

**Sizing:** one ticket per logical unit of work. A story that spans layers (schema, logic,
interface) splits into one ticket per layer, each noting its dependency. No tickets for
documentation, planning or "investigation" unless something is genuinely unknown.

**Order:** create them in dependency order: storage and schema first, then the logic over it,
then the interfaces on top.

If `planning.hazards` is set, a child that touches what it lists says so in its description.

## Step 5: Confirm

List every ticket as a hyperlink, `https://linear.app/<linear.workspace>/issue/<ID>/`:

```
Parent: [<ID> — Feature Name](url)

Children:
- [<ID> — Ticket title](url)
```

Then: "The PRD is at `<path>`. Ready to start on any of these?"
