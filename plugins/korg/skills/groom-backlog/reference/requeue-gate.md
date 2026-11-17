# The re-queue gate

Re-queueing is either **moving a ticket into `Backlog`/`Todo`** or **adding `agent-ready`**.
Either alone puts it back in front of the dispatcher, so this gate covers both.

**Never re-queue on Linear state alone.** A ticket parked in `Needs Human` can still have a live
`agent/<ID>` PR, and re-queueing it feeds the dispatcher a ticket whose implement run exits on
the open-PR dedup and does nothing. Check GitHub first, per ticket:

```bash
gh pr list --state all --head "agent/<ID>" --json number,state
gh pr list --state open --search "<ID> in:title" --json number,state,headRefName
```

Both queries, because the agent's open-PR dedup checks both.

Judge the **whole array**, not its first element: a ticket can have a closed PR from an
abandoned attempt next to the open one that matters, and `gh` does not promise an order.

- **Any PR is `OPEN`** → do not re-queue. Report "close the PR, or run a fix round on it".
- **Otherwise any PR is `MERGED`** → do not re-queue. Report "this is `Done`, not Backlog".
- **No PR, or only `CLOSED` ones** → re-queueing is fine.
