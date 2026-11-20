# Linear work items

## Talking to Linear

The team key and workspace urlKey are `linear.team` and `linear.workspace` in `.korg.yml`.
Address everything by **name** (team key, label names, state names). Linear's API
filters by name server-side, so nothing pins an id.

- **Interactive / skills**: the `linear` MCP server in `.mcp.json` (`get_issue`, `list_issues`,
  `save_issue`, `save_comment`, `list_issue_labels`).
- **Shell / CI scripts**: `linear-issue <ID>` (on PATH from the plugin): one GraphQL query,
  state and labels expanded to names. Raw GraphQL: `POST https://api.linear.app/graphql`,
  header `Authorization: $LINEAR_API_KEY`.

## Agent identity: who acts as whom

Two Linear identities exist:

- **Interactive sessions** use the human's personal API key and act as that human.
- **CI** acts as the workspace OAuth app (the app actor): every job mints a
  30-day token with `linear-agent-token` (client_credentials grant from the `LINEAR_CLIENT_ID` /
  `LINEAR_CLIENT_SECRET` secrets) and exports it as `LINEAR_API_KEY`.

Never point CI at a personal key, and never use the app credentials interactively.

## Referencing work items

Render every work-item identifier as a hyperlink, never plain text. Look the ticket up first
so the link text is accurate: `[<ID> — Title](https://linear.app/<linear.workspace>/issue/<ID>/)`.

## Acceptance criteria on code-change work items

A work item that will produce a code change must include an **Acceptance criteria** section
with checks `.claude/rules/testing-signal.md` accepts. Spike and idea items that produce no
code change are exempt; when ambiguous, require criteria.

## Description formatting

Descriptions are markdown; no HTML. A ticket filed by anything other than a human's
interactive session (a CI job, the pr-review bot) opens with one italic line naming what filed
it, and the PR or run it came from:

```markdown
*This ticket was filed by the pr-review bot, from https://github.com/addisonlynch/korg/pull/12.*
```

## Labels

The full taxonomy lives in `.korg/label-taxonomy.md`. Read it before applying, creating or
renaming a label.

## Statuses

- **Backlog:** Backlog, Needs Shaping
- **Unstarted:** Todo
- **Started:** In Progress, In Review, Needs Human, Ready to Merge
- **Completed:** Done
- **Canceled:** Canceled, Duplicate

## Who moves state

The Linear GitHub integration is **not** connected for this repo, so nothing moves a code
ticket on a git event.

- The human who opens or merges the PR moves the ticket to **In Review** and **Done**. No skill
  or workflow writes those two transitions.
- An autonomous path handing work to a human sets **Needs Human** and assigns the owner in one
  `save_issue` call: the assignment is what notifies them.
- Humans own everything else: re-queueing, Needs Shaping, Ready to Merge, Canceled, and the
  merge.
