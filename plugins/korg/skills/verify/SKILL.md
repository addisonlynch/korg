---
name: verify
description: Run lint and the tests the current diff calls for, to verify all changes pass before proceeding
---

Verify the current change is lint-clean and its tests pass.

Values in `this.form` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one. If the file does not exist, stop: the project has not configured korg.

## Steps

1. List the changed paths:
   ```bash
   { git diff --name-only HEAD; git ls-files --others --exclude-standard; }
   ```

2. Run `commands.lint`. It lints whatever the diff touches, with auto-fixes applied.

3. Run `commands.test` once. It selects the tests the uncommitted diff calls for.

4. Report results. On a failure, read `commands.test_log` when it is set, fix, and re-run with
   `commands.test_rerun` when it is set, otherwise `commands.test`.

## Important

- All steps must pass before proceeding. Passing is not the finish line for whatever task
  called `/korg:verify`: inside `/korg:commit`, `/korg:open-pr`, or a ticket run,
  continue to that workflow's next step.
- Fix lint errors before test failures: they are faster to resolve and may cause the test
  failures.
- If tests fail, find the root cause rather than making the test pass.
- Never re-run a suite to see its output again: the log has it.
