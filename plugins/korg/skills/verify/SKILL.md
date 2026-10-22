---
name: verify
description: Run lint and the tests the current diff calls for, to verify all changes pass before proceeding
---

Verify the current change is lint-clean and its tests pass.

Names like `commands.lint` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one. If the file does not exist, stop: the project has not configured korg.

## Steps

1. Run `commands.lint`.

2. Run `commands.test` once. It selects the tests the uncommitted diff calls for.

3. Report results. On a failure, read the failures from the run's output, or from the log it
   names, fix, and re-run `commands.test`.

## Important

- All steps must pass before proceeding. Passing is not the finish line for whatever task
  called `/korg:verify`: inside `/korg:commit`, `/korg:open-pr`, or a ticket run,
  continue to that workflow's next step.
- Fix lint errors before test failures: they are faster to resolve and may cause the test
  failures.
- If tests fail, find the root cause rather than making the test pass.
- Never re-run a suite to see its output again.
