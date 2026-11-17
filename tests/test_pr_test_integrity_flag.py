"""pr-test-integrity-flag: the deterministic flags for a deleted test file, a net drop in test
assertions, and a neutered Makefile test recipe."""

from pathlib import Path

import pytest
from helpers import run, stub_dir

_DELETED_TEST_FILE_DIFF = """\
diff --git a/backend/tests/test_foo.py b/backend/tests/test_foo.py
deleted file mode 100644
index abc1234..0000000
--- a/backend/tests/test_foo.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def test_foo():
-    assert 1 == 1
-    assert 2 == 2
"""

_ADDED_TEST_FILE_DIFF = """\
diff --git a/backend/tests/test_bar.py b/backend/tests/test_bar.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/backend/tests/test_bar.py
@@ -0,0 +1,2 @@
+def test_bar():
+    assert 1 == 1
"""

_WEAKENED_ASSERTION_DIFF = """\
diff --git a/backend/tests/test_weak.py b/backend/tests/test_weak.py
index 1111111..2222222 100644
--- a/backend/tests/test_weak.py
+++ b/backend/tests/test_weak.py
@@ -1,4 +1,3 @@
 def test_weak():
-    assert x is not None
-    assert y > 0
     pass
"""

_STRENGTHENED_ASSERTION_DIFF = """\
diff --git a/backend/tests/test_weak.py b/backend/tests/test_weak.py
index 1111111..2222222 100644
--- a/backend/tests/test_weak.py
+++ b/backend/tests/test_weak.py
@@ -1,3 +1,4 @@
 def test_weak():
-    assert x is not None
+    assert x is not None
+    assert x != 0
     pass
"""

# An `assert` removed from production code (stripped under `-O`; replacing it with a raise is the
# correct move) is not a weakened test — the counter is gated on test paths, so this stays silent.
_PROD_ASSERT_REMOVED_DIFF = """\
diff --git a/backend/src/api/foo.py b/backend/src/api/foo.py
index 1111111..2222222 100644
--- a/backend/src/api/foo.py
+++ b/backend/src/api/foo.py
@@ -1,4 +1,3 @@
 def foo():
-    assert x is not None
-    assert y > 0
     return x
"""

# Assertions moved between two test files: removed in one, added in the other, net zero. Per-file
# counting would flag test_a.py (removed 2, added 0); cross-file totals net it out.
_MOVED_ASSERTIONS_DIFF = """\
diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py
index 1111111..2222222 100644
--- a/backend/tests/test_a.py
+++ b/backend/tests/test_a.py
@@ -1,4 +1,2 @@
 def test_a():
-    assert x is not None
-    assert y > 0
     pass
diff --git a/backend/tests/test_b.py b/backend/tests/test_b.py
index 3333333..4444444 100644
--- a/backend/tests/test_b.py
+++ b/backend/tests/test_b.py
@@ -1,2 +1,4 @@
 def test_b():
+    assert x is not None
+    assert y > 0
     pass
"""


# Parametrized over all six frontend/scripts/ is_test_path() case-arms (.test/.spec x ts/tsx/mjs),
# not just one extension.
def _frontend_scripts_deletion_diff(path: str) -> str:
    return f"""\
diff --git a/{path} b/{path}
deleted file mode 100644
index abc1234..0000000
--- a/{path}
+++ /dev/null
@@ -1,3 +0,0 @@
-test("routes", () => {{
-  expect(1).toBe(1)
-}})
"""


# The weakened-assertions half, for a .mjs file.
_WEAKENED_FRONTEND_SCRIPTS_MJS_DIFF = """\
diff --git a/frontend/scripts/evidence/publish.test.mjs b/frontend/scripts/evidence/publish.test.mjs
index 1111111..2222222 100644
--- a/frontend/scripts/evidence/publish.test.mjs
+++ b/frontend/scripts/evidence/publish.test.mjs
@@ -1,4 +1,3 @@
 test("publishes frames", () => {
-  expect(frames.length).toBe(2)
   expect(frames[0].name).toBe("before.png")
 })
"""

# The inverse: a non-test file deleted under frontend/scripts/ must stay silent — the allow-list
# widening must not turn into "flag everything under frontend/scripts/".
_DELETED_FRONTEND_SCRIPTS_NON_TEST_DIFF = """\
diff --git a/frontend/scripts/prerender.ts b/frontend/scripts/prerender.ts
deleted file mode 100644
index abc1234..0000000
--- a/frontend/scripts/prerender.ts
+++ /dev/null
@@ -1,2 +0,0 @@
-export function prerender() {}
-
"""

# The primary reward-hack: gut a test target's recipe (`pytest` -> `true`) while leaving the
# `test-backend:` header as unchanged diff context. The removed `pytest` line must still flag —
# matching only the `test*:` header would miss the very case this exists to catch.
_MAKEFILE_TEST_TARGET_DIFF = """\
diff --git a/Makefile b/Makefile
index 5555555..6666666 100644
--- a/Makefile
+++ b/Makefile
@@ -1,2 +1,2 @@
 test-backend:
-	pytest
+	true
"""

_MAKEFILE_NON_TEST_DIFF = """\
diff --git a/Makefile b/Makefile
index 5555555..6666666 100644
--- a/Makefile
+++ b/Makefile
@@ -1,2 +1,2 @@
-dev:
-	honcho start
+dev:
+	honcho start -e .env.local
"""

_UNRELATED_DIFF = """\
diff --git a/README.md b/README.md
index 7777777..8888888 100644
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old text
+new text
"""

_MAKEFILE_TEST_SUBSTRING_DIFF = """\
diff --git a/Makefile b/Makefile
index 5555555..6666666 100644
--- a/Makefile
+++ b/Makefile
@@ -1,2 +1,2 @@
-dev:
-	honcho start
+dev:
+	honcho start --latest
"""

_MAKEFILE_FRONTEND_TEST_TARGET_DIFF = """\
diff --git a/Makefile b/Makefile
index 5555555..6666666 100644
--- a/Makefile
+++ b/Makefile
@@ -1,2 +1,2 @@
 test-frontend:
-	cd frontend && npm run test
+	true
"""

_MAKEFILE_ADDED_TEST_TARGET_DIFF = """\
diff --git a/Makefile b/Makefile
index 5555555..6666666 100644
--- a/Makefile
+++ b/Makefile
@@ -1,1 +1,3 @@
 dev:
+test-api:
+	pytest tests/test_api
"""

# The false positives a bare-token match produced: the `.PHONY` line every new target must edit,
# the `@test -n "$(m)"` recipe guard, and a `npm run test:build` recipe. None runs the suite —
# `test:build` in particular is one character off the `npm run test` recipe that does.
_MAKEFILE_TEST_TOKENS_NON_TARGET_DIFF = """\
diff --git a/Makefile b/Makefile
index 5555555..6666666 100644
--- a/Makefile
+++ b/Makefile
@@ -1,6 +1,6 @@
-.PHONY: dev install test test-backend
+.PHONY: dev install test test-backend lint
 revision:
-	@test -n "$(m)"
+	@test -n "$(m)" || echo hi
 build:
-	npm run test:build
+	npm run test:build --prod
"""



class TestPrTestIntegrityFlag:
    def _run(self, tmp_path: Path, diff_text: str, *, gh_exit: int = 0):
        stubs = stub_dir(
            tmp_path,
            {
                "gh": (
                    "#!/usr/bin/env bash\n"
                    'printf \'%s\\n\' "$@" > "$STUB_DIR/gh_argv"\n'
                    f"[ {gh_exit} -eq 0 ] || exit {gh_exit}\n"
                    'cat "$STUB_DIR/diff.txt"\n'
                )
            },
        )
        (stubs / "diff.txt").write_text(diff_text)
        return run("pr-test-integrity-flag", ["42"], stubs, {"GITHUB_REPOSITORY": "owner/repo"})

    def test_flags_a_deleted_test_file(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, _DELETED_TEST_FILE_DIFF)
        assert result.returncode == 0, result.stderr
        assert "deleted test file: backend/tests/test_foo.py" in result.stdout

    def test_flags_a_deleted_root_level_tests_module(self, tmp_path: Path) -> None:
        """`tests/*.py` covers helpers and conftest files that are not named `test_*.py`."""
        diff = _DELETED_TEST_FILE_DIFF.replace("backend/tests/test_foo.py", "tests/conftest.py")
        result = self._run(tmp_path, diff)
        assert result.returncode == 0, result.stderr
        assert "deleted test file: tests/conftest.py" in result.stdout

    def test_adding_a_test_file_is_not_flagged(self, tmp_path: Path) -> None:
        """The inverse of the deletion check: a diff that only adds tests must stay silent."""
        result = self._run(tmp_path, _ADDED_TEST_FILE_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_flags_removed_assertions_with_no_replacement(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, _WEAKENED_ASSERTION_DIFF)
        assert result.returncode == 0, result.stderr
        assert "weakened assertions in test files (removed 2, added 0)" in result.stdout

    def test_replaced_or_added_assertions_are_not_flagged(self, tmp_path: Path) -> None:
        """The inverse: an assertion removed but replaced (or a net addition) must stay silent."""
        result = self._run(tmp_path, _STRENGTHENED_ASSERTION_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_removing_a_production_code_assert_is_not_flagged(self, tmp_path: Path) -> None:
        """Only assertions inside test files count: a runtime `assert` stripped from production
        code (correct under `-O`) is not a weakened test."""
        result = self._run(tmp_path, _PROD_ASSERT_REMOVED_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_moving_assertions_between_test_files_is_not_flagged(self, tmp_path: Path) -> None:
        """Cross-file totals, not per-file: assertions relocated from one test file to another net
        to zero. Per-file counting would false-positive on the source file."""
        result = self._run(tmp_path, _MOVED_ASSERTIONS_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_a_deleted_test_file_is_not_double_reported(self, tmp_path: Path) -> None:
        """A deletion is one finding, not two: its removed asserts must not also trip the weakened
        assertions check, which counted them off the `+++ /dev/null` old-path side."""
        result = self._run(tmp_path, _DELETED_TEST_FILE_DIFF)
        assert result.returncode == 0, result.stderr
        assert "deleted test file: backend/tests/test_foo.py" in result.stdout
        assert "weakened assertions" not in result.stdout

    @pytest.mark.parametrize(
        "path",
        [
            "frontend/scripts/site-routes.test.ts",
            "frontend/scripts/site-routes.test.tsx",
            "frontend/scripts/evidence/publish.test.mjs",
            "frontend/scripts/site-routes.spec.ts",
            "frontend/scripts/site-routes.spec.tsx",
            "frontend/scripts/evidence/publish.spec.mjs",
        ],
        ids=["test-ts", "test-tsx", "test-mjs", "spec-ts", "spec-tsx", "spec-mjs"],
    )
    def test_flags_a_deleted_frontend_scripts_test_file(self, tmp_path: Path, path: str) -> None:
        """Every `frontend/scripts/` case-arm must flag a deletion, not just the `.test.ts` one."""
        result = self._run(tmp_path, _frontend_scripts_deletion_diff(path))
        assert result.returncode == 0, result.stderr
        assert f"deleted test file: {path}" in result.stdout

    def test_flags_weakened_assertions_in_a_frontend_scripts_mjs_file(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, _WEAKENED_FRONTEND_SCRIPTS_MJS_DIFF)
        assert result.returncode == 0, result.stderr
        assert "weakened assertions in test files (removed 1, added 0)" in result.stdout

    def test_a_deleted_non_test_file_under_frontend_scripts_is_not_flagged(self, tmp_path: Path) -> None:
        """The inverse: the frontend/scripts/ arms must not flag every deletion under that
        directory, only actual test files."""
        result = self._run(tmp_path, _DELETED_FRONTEND_SCRIPTS_NON_TEST_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_flags_a_neutered_test_recipe(self, tmp_path: Path) -> None:
        """Gutting a `pytest` recipe to `true` under an unchanged `test-backend:` header must flag
        off the removed `pytest` line — the header is diff context, not a changed line."""
        result = self._run(tmp_path, _MAKEFILE_TEST_TARGET_DIFF)
        assert result.returncode == 0, result.stderr
        assert "touches Makefile test target: Makefile" in result.stdout

    def test_flags_a_neutered_frontend_test_recipe(self, tmp_path: Path) -> None:
        """The frontend half: a `test-frontend:` recipe that shells out to `npm run test` must flag
        off the removed npm line."""
        result = self._run(tmp_path, _MAKEFILE_FRONTEND_TEST_TARGET_DIFF)
        assert result.returncode == 0, result.stderr
        assert "touches Makefile test target: Makefile" in result.stdout

    def test_a_makefile_diff_that_only_adds_a_test_invocation_is_not_flagged(self, tmp_path: Path) -> None:
        """The inverse of the neutering check: a brand-new test target adds a `pytest` line and
        removes nothing. Flagging it would fail the agent-review check for a strict improvement."""
        result = self._run(tmp_path, _MAKEFILE_ADDED_TEST_TARGET_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_a_non_test_makefile_change_is_not_flagged(self, tmp_path: Path) -> None:
        """The inverse: a Makefile change that runs no test suite (e.g. `make dev`) is in scope,
        not test integrity — flagging every Makefile edit would drown the real signal."""
        result = self._run(tmp_path, _MAKEFILE_NON_TEST_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_test_as_a_substring_of_an_unrelated_word_is_not_flagged(self, tmp_path: Path) -> None:
        """`--latest` contains "test" but isn't one; a bare substring match would false-positive
        on "latest"/"fastest"/"protest" and drown the real signal in every unrelated Makefile diff."""
        result = self._run(tmp_path, _MAKEFILE_TEST_SUBSTRING_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_makefile_lines_that_run_no_test_suite_are_not_flagged(self, tmp_path: Path) -> None:
        """The `.PHONY` line, a `@test -n` recipe guard, and a `npm run test:build` recipe all carry
        a `test` token but none runs the suite. `test:build` is the close one: it must not match the
        `npm run test` recipe that does."""
        result = self._run(tmp_path, _MAKEFILE_TEST_TOKENS_NON_TARGET_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_an_unrelated_diff_is_not_flagged(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, _UNRELATED_DIFF)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_every_category_can_fire_in_one_diff(self, tmp_path: Path) -> None:
        combined = _DELETED_TEST_FILE_DIFF + _WEAKENED_ASSERTION_DIFF + _MAKEFILE_TEST_TARGET_DIFF
        result = self._run(tmp_path, combined)
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        assert "deleted test file: backend/tests/test_foo.py" in lines
        # test_foo.py's own removed asserts are excluded (reported as a deletion); only test_weak.py counts.
        assert "weakened assertions in test files (removed 2, added 0)" in lines
        assert "touches Makefile test target: Makefile" in lines

    def test_reads_the_prs_own_diff(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, _UNRELATED_DIFF)
        assert result.returncode == 0, result.stderr
        argv = (tmp_path / "stubs" / "gh_argv").read_text().splitlines()
        for expected in ("pr", "diff", "42", "--repo", "owner/repo"):
            assert expected in argv

    def test_a_gh_failure_fails_rather_than_reading_as_no_findings(self, tmp_path: Path) -> None:
        """A silent 'no findings' on a broken read would let exactly the class of change this
        script exists to catch slip through unflagged."""
        result = self._run(tmp_path, _UNRELATED_DIFF, gh_exit=1)
        assert result.returncode == 1
        assert "cannot classify" in result.stderr


