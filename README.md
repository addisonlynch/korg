# korg

A Claude Code plugin for agent-driven development: quality gates on every commit, ticket
planning in Linear, and PR review, with an autonomous ticket loop to follow.

## Install

```
/plugin install korg --marketplace addisonlynch/korg
```

Or, to enable it for everyone working in a project, in its `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "korg": { "source": { "source": "github", "repo": "addisonlynch/korg" } }
  },
  "enabledPlugins": { "korg@korg": true }
}
```

Headless runs load it with `claude -p --plugin-dir <checkout>/plugins/korg`.

Requires `bash`, `git`, `jq`, and either `python3` with PyYAML or `yq`.

## Configure

The plugin reads `.korg.yml` at the project root. The gates own the order and the policy;
the project owns how its stacks are linted and tested.

```yaml
commands:
  # Lint the project. Non-zero on failure.
  lint: make lint
  # Run the tests the uncommitted diff calls for. On failure the gates read its output.
  test: make test
  # Optional. Run one test id. `{test}` is the id, `{root}` the main checkout's root, so the
  # command can run inside a temporary worktree against dependencies installed in the checkout.
  # `{root}` is substituted as-is: quote it, since a checkout path may contain spaces.
  test_one: '"{root}/.venv/bin/python" -m pytest {test} -q'
  # Optional. Lint-fix one file after every Write/Edit. `{file}` is the absolute path, shell-quoted.
  format_file: "ruff format {file}"

rules:
  # What counts as a checkable acceptance criterion and which tests should exist; test-review
  # deletes the rest. Optional for the gates, required by the planning skills.
  testing_signal: .claude/rules/testing-signal.md

# The planning layer (roadmap, to-prd, to-tickets, groom-backlog). Each planning skill stops
# when a key it needs is unset. Relative paths are from the project root; a leading ~ is expanded.
linear:
  team: ENG       # team key, addressed by name
  workspace: acme # urlKey, for ticket links
planning:
  # Every label on the team and when to apply it. The project owns it; korg never edits it.
  label_taxonomy: .korg/label-taxonomy.md
  # Optional. What an unattended run must never do, and what a ticket touching a sensitive area
  # must say. roadmap --auto, to-tickets and groom-backlog refuse agent-ready work it forbids.
  hazards: .korg/ticket-hazards.md
  # Where /korg:to-prd writes PRDs. A leading ~ is expanded.
  prd_dir: ~/vault/prds
  # Optional. A plan file whose `## Now` section groom-backlog checks the queue against.
  plan: ~/vault/plan.md

# The PR layer (open-pr, pr-review). pr-review also requires linear.team, linear.workspace and
# planning.label_taxonomy above, and reads rules.testing_signal when set.
review:
  # Required by pr-review. The stack-specific correctness checks; korg's own checklist holds
  # only what every stack shares.
  checklist: .korg/review-checklist.md
  # Optional. Manual-testing steps by area, pasted into the PR description by open-pr.
  manual_testing: .korg/manual-testing.md
# Optional; absent = off. Change types whose PR must carry run output (a fenced command and its
# output) under `## Evidence`. pr-review fails the agent-review check when one is missing. A
# screenshot never counts: a fix round cannot capture one.
evidence:
  exempt: ["**/*.md", ".claude/**", ".github/**"]  # every changed file matches → exempt
  types:
    - name: Migration                               # the `### Migration` subsection
      paths: ["db/migrations/**"]
      need: post-migrate assertion output
```

The planning skills talk to Linear the way the project's Linear rule in `.claude/rules/` says
(including the italic filer line a non-interactive job opens a ticket with), and assume:

- states `Backlog`, `Needs Shaping`, `Todo`, `Needs Human`;
- type labels `bug`, `chore`, `idea`, `spike`, and `agent-ready`, `auto-filed`;
- `model:opus`, `model:sonnet`, `model:haiku` route the runner's model; `model:fable` marks
  interactive-only work and never coexists with `agent-ready`;
- an agent runner that takes `agent-ready` tickets (stripping the label), works each on an
  `agent/<ID>` branch in about two hours, and skips a ticket that already has an open PR. It
  ignores blocked-by links, so to-tickets queues only unblocked tickets and groom-backlog queues
  the rest as their blockers land;
- `gh`, for groom-backlog's re-queue check.

The review layer runs in CI as reusable workflows: see [docs/callers.md](docs/callers.md) for
the caller each project adds, its inputs and secrets, and the required-check names. The
`needs-review` label requests a review, `no-auto-review` opts a PR out, and the bot publishes its
verdict as the `agent-review` check.

`/korg:to-prd` opens each PRD with `question` / `decision` / `verdict` / `consumed_by`
frontmatter and fills `consumed_by` with the parent ticket.

## Skills

| Skill | What it does |
|---|---|
| `/korg:commit` | Lint → test-review → deslop → security → scoped tests → commit and push |
| `/korg:verify` | Lint and the scoped tests |
| `/korg:deslop` | Three-agent adversarial review of the diff, then the worthwhile fixes |
| `/korg:test-review` | Test-quality review of the tests the diff touched |
| `/korg:roadmap` | Capture an idea as a Linear issue, or `--auto` to scope and queue it for the agent runner |
| `/korg:to-prd` | Write a PRD from the conversation, with its test seams, and a parent issue for it |
| `/korg:to-tickets` | Break a PRD, parent issue or conversation into vertical-slice tickets with blocked-by links, after you approve the breakdown |
| `/korg:open-pr` | `/korg:commit`, then open the PR with a structured description and request review |
| `/korg:pr-review` | The review bot's instructions: correctness, fitness and altitude reviewers, one review, the `agent-review` check |
| `/korg:groom-backlog` | Triage the backlog: stale, stuck, unready, mislabelled and duplicate tickets, and queue the ones whose blockers are done |

Project rules in `.claude/rules/*.md` (with optional `paths:` frontmatter) and the root
`CLAUDE.md` are enforced by deslop's rules cop.

## Contributing

How korg is built: [CLAUDE.md](CLAUDE.md).

## License

MIT. See [LICENSE](LICENSE).
