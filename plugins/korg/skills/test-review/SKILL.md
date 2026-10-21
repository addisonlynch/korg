---
name: test-review
description: Author-side review of test quality on the current change. Deletes tests the project's testing-signal rule excludes, then catches tautological asserts, over-mocking, mocked databases, and snapshot abuse. Edits tests in place. Run before commit when the diff includes test files.
---

# Test review

Use before commit when the change adds or modifies tests. The goal is that tests exercise
behavior, not that they pass.

Values in `this.form` are keys of the project's `.korg.yml`; `korg-config <key>` prints
one.

## Contract

- **Reads:** the test files this change touched, and the code they exercise.
- **Answers:** do these tests actually exercise behavior?
- **May:** rewrite or delete tests this branch added.
- **May not:** touch a non-test file; remove or alter an assert, fixture, skip, xfail, or mock
  that exists at the merge-base; add a skip or xfail anywhere. A pre-existing test that looks
  wrong is a finding to report, not an edit to make: changing it changes what "correct" means
  one step before the run that judges the change.

## Scope

Only test files this change touched:

```sh
{ git diff --name-only HEAD; git ls-files --others --exclude-standard; } \
  | grep -E '(test_|_test\.|\.test\.|/tests/|/__tests__/)'
```

Untracked files are included because a new test file is invisible to `git diff HEAD` until it
is staged. Scope is `HEAD`, not `<default_branch>...HEAD`: on a branch's first commit the
latter is empty and reviews nothing.

If the list is empty, stop.

## Step 0: should this test exist

When `rules.testing_signal` is set, apply that rule file to every **new** test file and every
new test block in an existing one. A test outside what the rule allows is deleted here, however
well-written. A ticket that asked for the test does not override the rule: delete it anyway and
surface the swap as a finding, naming the check that replaces it.

## Failure modes to catch

### 1. Tautological assertions

For every assertion in the changed tests, ask: **would this still pass if the implementation
returned `None`, `{}`, the input unchanged, or `True`?** If yes, it is tautological.

Common shapes:
- `assert result is not None` as the only assertion
- `assert mock.called` without checking the arguments or the result
- `assert isinstance(result, dict)` with no check on contents
- Asserting against another call to the same code path
- Snapshots generated from the broken implementation

**Fix:** assert on the actual value: the specific number, row count, or error message. For
non-deterministic values, assert on shape *and* a property (range, sort order, length, key set).

### 2. Over-mocking

```sh
grep -cE 'mock\.|MagicMock|@patch|monkeypatch|jest\.mock|vi\.mock' <file>
```

- **More than 5 per file**: flag it. The test probably mocks the thing under test.
- **Mocking the function under test**: always wrong. Remove it.
- **Mocking the database** in a test that exercises ORM models, queries, or migrations: always
  wrong (rule 3).

**Fix:** mock only at trust boundaries (external HTTP APIs, payment processors, email, the
clock). Inside the system, use real objects.

### 3. Real database for database code

A test that touches ORM models, migrations, or queries must hit a real database: a
container-backed fixture or the persistent test database the project already uses (check the
test configuration). Patching the session, engine, connection, or a query method is banned;
replace it with a real fixture.

### 4. Snapshot abuse

Flag a snapshot when:
- It is over 50 lines (split it or assert on specific properties)
- It includes timestamps, UUIDs, or other volatile output (normalize first)
- It is added without a comment saying what behavior it pins down

**Fix:** snapshots are for genuinely stable output (rendered HTML, formatted reports). For
everything else, write specific assertions.

### 5. Coverage without behavior

A test that imports a module and instantiates a class without exercising behavior. Delete it or
add a real assertion on the intended behavior.

## Process

1. Identify changed test files (command above).
2. Run Step 0.
3. For each remaining file: read it fully; list each test's assertions and answer the tautology
   question; run the mock count; check for database mocking; check snapshot rules when
   snapshots are involved.
4. Apply fixes in place. A fix that would widen scope (a database fixture the project does not
   have) is a finding, not an edit.
5. Re-run the affected tests (`commands.test_one` when set, otherwise the project's test runner
   on those files). Confirm they pass and that at least one assertion in each changed test
   would fail if the implementation regressed.

## Stop rules

- Do not add tests beyond fixing the ones in the diff.
- Do not refactor unrelated test infrastructure.
- Do not change production code: a test that reveals a bug is a finding.
- If the project lacks a real-database fixture and adding one is out of scope, leave the test
  mocked and add `# TODO(test-review): replace DB mock with real fixture` with the date.

## Output

- Files reviewed
- Fixes applied (file:line, what changed)
- Findings surfaced but not fixed, with the reason
