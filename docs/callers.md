# Calling korg's workflows

korg ships its PR workflows as reusable workflows. A project adds one small caller per
workflow under its own `.github/workflows/` and pins a korg tag. The reusable workflow
checks out korg at that same ref and runs its scripts from there; the project checkout
supplies `.korg.yml`.

Pin an exact release tag (`@v0.2.4`). korg's `v*` tags cannot be moved or deleted, and there is
no floating `@v1`.

## PR review

`.github/workflows/claude-pr-review.yml`:

```yaml
# Keep this name: a workflow_run listener in the project triggers on it.
name: Claude PR Review

on:
  pull_request:
    types: [labeled, synchronize]
  pull_request_review:
    types: [submitted]

permissions:
  contents: read
  pull-requests: write
  id-token: write
  checks: write
  statuses: read
  actions: read

jobs:
  review:
    uses: addisonlynch/korg/.github/workflows/pr-review.yml@v0.2.4
    secrets: inherit
    with:
      runner_target: ${{ vars.RUNNER_TARGET }}
      human_reviewer: ${{ vars.HUMAN_REVIEWER }}
      # linear_mcp_server: linear
      claude_executable: ${{ vars.CLAUDE_EXECUTABLE }}
```

Concurrency lives inside the reusable workflow, one group per called job, so the caller
sets none. A workflow-level group would let a submitted review cancel an in-flight bot
review.

| Input | Default | Meaning |
|---|---|---|
| `runner_target` | `''` | `''` or `github`: `ubuntu-latest`. Anything else: `[self-hosted, <value>]`. |
| `claude_executable` | `''` | Pre-installed Claude Code binary on a self-hosted runner. Set it on any self-hosted runner whose jobs share a `$HOME`: without it the action installs Claude per job into that `$HOME`, and concurrent jobs collide. Ignored on hosted runners. |
| `human_reviewer` | repository owner | Login whose submitted review is the verdict on workflow-file PRs. Set it when the owner is an organization. |
| `linear_mcp_server` | `linear` | Server name in the project's `.mcp.json`; the reviewer's allowlist grants `mcp__<name>`. |

| Secret | Required | Used for |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | yes | The reviewer run. |
| `LINEAR_CLIENT_ID`, `LINEAR_CLIENT_SECRET` | no | Minting the Linear app-actor token. Without them the review still runs, with the default model and no ticket criteria. |

The project also needs the `needs-review` and `no-auto-review` labels. Re-reviews on push
fire only for `agent/*` branches.

## Base guard

`.github/workflows/pr-base-guard.yml`:

```yaml
name: PR Base Guard

# No `branches:` filter: this is the gate that sees PRs stacked on other branches.
on:
  pull_request:
    types: [opened, reopened, edited]

permissions:
  contents: read

jobs:
  guard:
    uses: addisonlynch/korg/.github/workflows/base-guard.yml@v0.2.4
```

No inputs or secrets.

## Required checks

A reusable workflow's jobs report as `<caller job> / <called job>`. With the caller job ids
above, update the branch rulesets:

| Before | After |
|---|---|
| `base-is-main` | `guard / base-is-main` |
| `claude-review`, `human-verdict` (if required) | `review / claude-review`, `review / human-verdict` |
| `agent-review` | `agent-review` (unchanged: a script publishes it as a check run) |

Requiring `agent-review` alone is enough for the review gate. A different caller job id
changes the prefix.

## Agent runs

korg has no reusable workflow for the agent runs: a project keeps its own
`agent-dispatch.yml`, `agent-implement.yml` and `agent-respond.yml` and calls korg's skill and
scripts from them.

- Clone korg at the pinned tag into `$RUNNER_TEMP/korg`: unlike the review workflow's clone, it
  sits outside the checkout, so the agent's `git add -A` never sweeps it into the PR. Then put
  its scripts on the path before any step that calls one, since they call each other by bare
  name: `echo "$RUNNER_TEMP/korg/plugins/korg/bin" >> "$GITHUB_PATH"`.
- Pass `--plugin-dir "$RUNNER_TEMP/korg/plugins/korg"` to Claude, and prompt
  `/korg:agent-ticket <TEAM>-N --ci-implement` or `/korg:agent-ticket --ci-respond`.
- Set `KORG_AGENT_RUN: implement` in the implement step's `env`. It arms korg's Stop hook, which
  sends the agent back once when it tries to end the run on its `agent/<TEAM>-N` branch with
  neither a PR carrying `needs-review` nor a `WIP — bailed` commit. Leave it unset in respond.
- `agent-dispatch` runs `gh workflow run agent-implement.yml -f ticket=<TEAM>-N -f model=<model>`
  and counts in-flight runs by the ticket id in their run names. So the file keeps that name,
  declares `workflow_dispatch` inputs `ticket` and `model`, and has a `run-name` containing the
  ticket (`implement <TEAM>-N`).
- When claude-code-action mints its own token (no `github_token` input), it skips the run,
  without failing it, if the workflow file differs from the default branch's copy. A change to
  `agent-implement.yml` or `agent-respond.yml` then cannot be exercised before it merges.
