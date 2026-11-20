# Calling korg's workflows

korg ships its PR workflows as reusable workflows, and the steps of jobs that need the project's
environment as composite actions. A project adds one small caller per workflow under its own
`.github/workflows/` and pins a korg tag. The reusable workflow
checks out korg at that same ref and runs its scripts from there; the project checkout
supplies `.korg.yml`.

Pin an exact release tag (`@v0.2.2`). korg's `v*` tags cannot be moved or deleted, and there is
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
    uses: addisonlynch/korg/.github/workflows/pr-review.yml@v0.2.2
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
    uses: addisonlynch/korg/.github/workflows/base-guard.yml@v0.2.2
```

No inputs or secrets.

## Respond: the fix loop

**Private repositories only.** The fix round acts on PR review comments with write access and
secrets, and anyone can comment on a public repository's PRs, so `respond-gate` refuses to run on
one.

A respond run needs the project's environment (dependencies, a test database, credentials), so
korg does not own its job. The project keeps the job and calls three composite actions for the
agent's steps; everything between them is the project's.

`.github/workflows/agent-respond.yml`:

```yaml
name: Agent Respond

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  pull_request_review:
    types: [submitted]
  workflow_run:
    workflows: ["Claude PR Review"]   # the review caller's `name:`
    types: [completed]

jobs:
  respond:
    # Only the human reviewer can mention: a bot is never that reviewer, so the responder cannot
    # trigger itself. respond-gate decides whether a loop trigger is a round.
    if: >-
      (github.event_name == 'workflow_run' &&
       github.event.workflow_run.head_repository.full_name == github.repository &&
       startsWith(github.event.workflow_run.head_branch, 'agent/')) ||
      (((github.event_name == 'issue_comment' && github.event.issue.pull_request && contains(github.event.comment.body, '@claude')) ||
        (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@claude')) ||
        (github.event_name == 'pull_request_review' && github.event.review.body && contains(github.event.review.body, '@claude'))) &&
       github.event.sender.login == (vars.HUMAN_REVIEWER || github.repository_owner))
    runs-on: ubuntu-latest
    timeout-minutes: 120
    permissions:
      contents: write
      pull-requests: write
      id-token: write
      checks: read          # the gate reads the agent-review check
    concurrency:
      # Queued triggers converge: the gate reads the PR's current state.
      group: agent-respond-${{ github.event.workflow_run.pull_requests[0].number || github.event.workflow_run.head_branch || github.event.issue.number || github.event.pull_request.number }}
      cancel-in-progress: false
    steps:
      - id: gate
        uses: addisonlynch/korg/.github/actions/respond-gate@vX.Y.Z
        with:
          linear_client_id: ${{ secrets.LINEAR_CLIENT_ID }}
          linear_client_secret: ${{ secrets.LINEAR_CLIENT_SECRET }}

      - if: steps.gate.outputs.action == 'round'
        run: make ci-setup

      - if: steps.gate.outputs.action == 'round'
        uses: addisonlynch/korg/.github/actions/respond-round@vX.Y.Z
        with:
          pr: ${{ steps.gate.outputs.pr }}
          ref: ${{ steps.gate.outputs.ref }}
          round: ${{ steps.gate.outputs.round }}
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          linear_client_id: ${{ secrets.LINEAR_CLIENT_ID }}
          linear_client_secret: ${{ secrets.LINEAR_CLIENT_SECRET }}
          claude_executable: ${{ vars.CLAUDE_EXECUTABLE }}

      - if: failure() || cancelled()
        uses: addisonlynch/korg/.github/actions/respond-failed@vX.Y.Z
        with:
          pr: ${{ steps.gate.outputs.pr }}
          action: ${{ steps.gate.outputs.action }}
```

- **Same ref on all three.** The actions run korg's scripts and plugin from their own ref, so
  the three `uses:` must pin the same tag.
- **`gh` on PATH before the gate.** On a self-hosted runner where it lives in a user bin, add
  that directory to `$GITHUB_PATH` in a step before `respond-gate`.
- **Environment for the agent.** Variables the fix round needs (service URLs, API keys) go in
  the `respond-round` step's `env:`; they reach every step inside it. A service container
  (`services:`) is declared on the job as usual.
- **A Stop hook that re-adds `needs-review`** must skip respond runs: a pushless round halts the
  loop by leaving the label off. Set a job `env:` variable and have the hook check it.
- **Untestable before merge.** `claude-code-action` refuses to run when the workflow file differs
  from the default branch's copy, so a change to this caller runs its agent step only after it
  merges.

| Action | Input | Meaning |
|---|---|---|
| `respond-gate` | `linear_client_id`, `linear_client_secret` | Required for escalation, which writes Linear as the app actor. |
| `respond-round` | `pr`, `ref`, `round` | The gate's outputs. |
| | `claude_code_oauth_token` | Required. |
| | `linear_client_id`, `linear_client_secret` | Optional: without them the round runs the default model with no ticket context. |
| | `claude_executable` | Pre-installed Claude Code binary; set it on self-hosted runners that share a `$HOME`. |
| `respond-failed` | `pr`, `action` | The gate's outputs, when it got that far. |

`.korg.yml` needs `linear.team` and `linear.owner` (the user an escalation assigns).

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
