# korg

A Claude Code plugin for agent-driven development: quality gates on every commit, with more
layers (PR review, ticket planning, an autonomous ticket loop) to follow.

## Install

In the project's `.claude/settings.json`:

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
default_branch: main

commands:
  # Lint whatever the uncommitted diff touches, applying auto-fixes. Non-zero on failure.
  lint: make lint
  # Run the tests the uncommitted diff calls for.
  test: make test
  # Optional. Re-run only the last failures.
  test_rerun: make test args=--lf
  # Optional. Where `test` writes its full output; read on failure instead of re-running.
  test_log: test-output.log
  # Optional. Run one test id. `{test}` is the id, `{root}` the main checkout's root, so the
  # command can run inside a temporary worktree against dependencies installed in the checkout.
  test_one: "{root}/.venv/bin/python -m pytest {test} -q"
  # Optional. Format one file after every Write/Edit. `{file}` is the absolute path.
  format_file: "ruff format {file}"

rules:
  # Optional. A rule file saying which tests should exist; test-review deletes the rest.
  testing_signal: .claude/rules/testing-signal.md
```

## Skills

| Skill | What it does |
|---|---|
| `/korg:commit` | Lint → test-review → deslop → security → scoped tests → commit and push |
| `/korg:verify` | Lint and the scoped tests |
| `/korg:deslop` | Three-agent adversarial review of the diff, then the worthwhile fixes |
| `/korg:test-review` | Test-quality review of the tests the diff touched |

Project rules in `.claude/rules/*.md` (with optional `paths:` frontmatter) and the root
`CLAUDE.md` are enforced by deslop's rules cop.
