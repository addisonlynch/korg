# korg review checklist

The korg-specific checks the correctness reviewer applies on top of its own checklist.

## Config, not project facts

- Flag a project name, path, team key, ticket prefix or hostname in a skill, script or
  workflow. Each belongs in a `.korg.yml` key; a skill stops when a key it needs is unset
  (CLAUDE.md principles 1 and 12).

## Scripts (`plugins/korg/bin/`)

- Flag a failure that exits zero or prints nothing. Errors exit non-zero with the reason; a
  safer-default fallback prints a `::warning::` (principle 6).
- Flag a new script or branch with no pytest case in `tests/`.
- Flag a `linear-agent-token` change to the scope string: a mint with a different scope
  revokes every outstanding app token.

## Workflows

- Flag an action, tool download or package not pinned by commit SHA or exact version, and a
  korg ref not pinned by tag (principle 8).
- Flag a step that gives the agent a credential beyond the job's scoped token (principle 5).

## Skills

- Flag a hook or guard that infers intent from command text, or state kept in marker files
  (principle 3).
