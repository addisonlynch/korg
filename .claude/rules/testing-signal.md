# Testing signal: when a change warrants a test

What counts as a checkable acceptance criterion, and when a change should carry a test. Read
when writing acceptance criteria (the planning skills), at commit (`test-review`), and when
reviewing a diff (`pr-review`).

## Acceptable checks

- a passing test in `tests/`
- a lint pass: `shellcheck`, `actionlint`, `claude plugin validate plugins/korg`
- a command's output (name the command and the line to look for)
- a run on a consuming project: the skill or workflow, the throwaway ticket or PR it ran on,
  and what it produced

"It works" is not a criterion.

## `plugins/korg/bin/`: a test is the natural signal

Scripts are deterministic: arguments and stubbed `gh`/`curl`/`korg-config` output in, stdout
and exit code out. Ask for a pytest case in `tests/` using `tests/helpers.py`, covering the
branch the change adds or fixes.

## Skills and workflows: a real run, no test

A `SKILL.md`, its `reference/` files, or a reusable workflow is proven by a real run (CLAUDE.md
principle 10). A pytest that greps a skill's text is not a check; delete it.

## Docs and config

`README.md`, `docs/`, `CLAUDE.md` and `.korg.yml` carry no test. Lint is the check where one
applies.
