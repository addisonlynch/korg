---
disable-model-invocation: true
name: to-prd
description: Synthesize the conversation into a PRD at planning.prd_dir and a parent Linear issue for it. /korg:to-tickets then breaks it into tickets.
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

## Step 2: Sketch the test seams

Name the seams at which the feature will be tested: the interfaces a test drives and observes.
Prefer seams that already exist to new ones, and the highest one available; ideally there is
one. Check with the user that these
match their expectations, then carry them into the PRD's Testing Decisions.

## Step 3: Write the PRD

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

`decision` is never the parent ticket, which does not exist yet. Step 4 fills `consumed_by`.

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

<The seams from Step 2, what each test observes there (external behaviour, not
implementation), the key cases, and prior art in the codebase, per `rules.testing_signal`.>

## Out of Scope

<Adjacent things this PRD does not cover.>

## Further Notes

<Open questions, risks, dependencies on other work.>
```

Tell the user the path it was written to.

## Step 4: Create the parent issue

One issue on team `linear.team` that represents the whole feature (native parent/sub-issue
hierarchy):

- `title`: the PRD's feature name, max 60 chars
- `description`: a one-paragraph summary, the PRD's path, and the key out-of-scope items as
  bullets
- `labels`: the area labels that apply to the feature as a whole, per `planning.label_taxonomy`

Set the PRD's `consumed_by` to its identifier.

## Step 5: Confirm

```
PRD: <path>
Parent: [<ID> — Feature Name](https://linear.app/<linear.workspace>/issue/<ID>/)
```

Then tell the user to run `/korg:to-tickets <ID>` to break it into tickets. Do not call it
yourself.
