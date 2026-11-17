"""PR-scoped reads and gates: pr-ci-status, pr-touches-workflows, pr-comment-once,
pr-base-is-default."""

import json
from pathlib import Path

import pytest
from helpers import LOOP_GH_STUB, gh_calls, outputs, posted_comment, run, stub_dir

# `gh pr checks` stub: replays STUB_GH_OUT verbatim (tab-separated check rows, an error line, or
# both) and STUB_GH_EXIT.
_ROW = "backend\tpass\t4m2s\thttps://example/job\t"
_CHECKS_GH_STUB = """#!/usr/bin/env bash
echo "${GH_TOKEN:-}" > "$STUB_DIR/seen_token"
echo "$*" > "$STUB_DIR/seen_args"
printf '%s\\n' "${STUB_GH_OUT:-}"
exit "${STUB_GH_EXIT:-0}"
"""


class TestPrCiStatus:
    """The CI-status read wrapper: called bare by the reviewer; the token swap lives inside
    (a `GH_TOKEN=…` command prefix is refused by the reviewer's sandbox)."""

    def _run(self, tmp_path: Path, *, env_extra: dict[str, str]) -> tuple[Path, object]:
        stubs = stub_dir(tmp_path, {"gh": _CHECKS_GH_STUB})
        env = {"GITHUB_REPOSITORY": "owner/repo", "STUB_GH_OUT": _ROW} | env_extra
        return stubs, run("pr-ci-status", ["77"], stubs, env)

    def test_prefers_the_job_token_and_targets_the_pr(self, tmp_path: Path) -> None:
        stubs, result = self._run(tmp_path, env_extra={"GH_TOKEN": "app-token", "CI_STATUS_GH_TOKEN": "job-token"})
        assert result.returncode == 0, result.stderr
        assert (stubs / "seen_token").read_text().strip() == "job-token"
        assert (stubs / "seen_args").read_text().strip() == "pr checks 77 --repo owner/repo"

    def test_falls_back_to_the_ambient_token_when_the_job_token_is_unset(self, tmp_path: Path) -> None:
        """Local runs have no CI_STATUS_GH_TOKEN; the ambient gh auth reads checks fine."""
        stubs, result = self._run(tmp_path, env_extra={"GH_TOKEN": "ambient"})
        assert result.returncode == 0, result.stderr
        assert (stubs / "seen_token").read_text().strip() == "ambient"

    def test_rows_with_a_failing_exit_are_still_readable(self, tmp_path: Path) -> None:
        """`gh pr checks` exits non-zero on failing/pending/absent — that is the answer, not an
        error. Rows came back, so the reviewer can see CI and the verdict says so."""
        _, result = self._run(tmp_path, env_extra={"CI_STATUS_GH_TOKEN": "job-token", "STUB_GH_EXIT": "8"})
        assert result.returncode == 0, result.stderr
        assert result.stdout.rstrip().endswith("CI_STATUS: readable")

    def test_a_partial_graphql_error_alongside_rows_is_readable(self, tmp_path: Path) -> None:
        """`gh pr checks` can print every check row and THEN a 403 on one nested sub-field. Rows
        present means readable, and the rows must survive into the output."""
        out = _ROW + "\nGraphQL: Resource not accessible by integration (node.statusCheckRollup.nodes.0.commit)"
        _, result = self._run(
            tmp_path, env_extra={"CI_STATUS_GH_TOKEN": "job-token", "STUB_GH_OUT": out, "STUB_GH_EXIT": "1"}
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.rstrip().endswith("CI_STATUS: readable")
        assert "backend\tpass" in result.stdout

    def test_no_checks_yet_is_readable_not_blind(self, tmp_path: Path) -> None:
        """The review bot fires on the `needs-review` label at PR open, so it races CI and
        legitimately sees zero checks. Empty is not blind: calling it unreadable would force a
        failure verdict on every PR reviewed in that window."""
        _, result = self._run(
            tmp_path,
            env_extra={
                "CI_STATUS_GH_TOKEN": "job-token",
                "STUB_GH_OUT": "no checks reported on the 'agent/ABC-42' branch",
                "STUB_GH_EXIT": "1",
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.rstrip().endswith("CI_STATUS: readable")

    def test_an_error_with_no_rows_is_unreadable(self, tmp_path: Path) -> None:
        """The inverse: a real 403 returns no check rows at all, and THAT is the case the
        reviewer must treat as not-clean (absent never reads green)."""
        _, result = self._run(
            tmp_path,
            env_extra={
                "CI_STATUS_GH_TOKEN": "job-token",
                "STUB_GH_OUT": "GraphQL: Resource not accessible by integration",
                "STUB_GH_EXIT": "1",
            },
        )
        assert result.returncode == 1
        assert result.stdout.rstrip().endswith("CI_STATUS: unreadable")

    def test_an_unrecognized_error_with_no_rows_is_unreadable(self, tmp_path: Path) -> None:
        """The classifier must fail closed on wording it has never seen, not just the errors on
        its allowlist — a DNS/transport failure or a future `gh` message must not read as empty
        checks."""
        _, result = self._run(
            tmp_path,
            env_extra={
                "CI_STATUS_GH_TOKEN": "job-token",
                "STUB_GH_OUT": "dial tcp: lookup api.github.com: no such host",
                "STUB_GH_EXIT": "1",
            },
        )
        assert result.returncode == 1
        assert result.stdout.rstrip().endswith("CI_STATUS: unreadable")

    def test_a_skipped_review_is_flagged_as_not_a_reviewer(self, tmp_path: Path) -> None:
        """A review bot that skips bot-authored PRs still reports its check green; the reason is
        already in the description column, so no extra API read is needed."""
        rows = _ROW + "\nCodeRabbit\tpass\t3s\thttps://example/cr\tReview skipped: bot user not eligible for review"
        _, result = self._run(tmp_path, env_extra={"CI_STATUS_GH_TOKEN": "job-token", "STUB_GH_OUT": rows})
        assert result.returncode == 0, result.stderr
        assert "CI_NOTE: skipped review — CodeRabbit" in result.stdout
        assert "bot user not eligible for review" in result.stdout
        # The machine-readable verdict stays the last line; the reviewer reads that line
        # literally, so the note must not displace it.
        assert result.stdout.rstrip().endswith("CI_STATUS: readable")

    def test_any_vendor_is_covered(self, tmp_path: Path) -> None:
        """The rule is stated about the description, not the vendor, so the next reviewer bot
        that skips is covered without an edit to this script."""
        rows = _ROW + "\nsome-other-bot\tpass\t1s\thttps://example/x\tReview skipped (draft PR)"
        _, result = self._run(tmp_path, env_extra={"CI_STATUS_GH_TOKEN": "job-token", "STUB_GH_OUT": rows})
        assert result.returncode == 0, result.stderr
        assert "CI_NOTE: skipped review — some-other-bot" in result.stdout

    @pytest.mark.parametrize(
        "description",
        [
            pytest.param("3 actionable comments", id="reviewed-normally"),
            # The reason the match is the phrase and not a bare "skip": this one ran.
            pytest.param("skipped 3 files", id="skipped-some-files"),
        ],
    )
    def test_a_review_that_actually_ran_gets_no_note(self, tmp_path: Path, description: str) -> None:
        """The inverse: flagging a review that ran would teach the reviewer to discount the one
        independent signal it had."""
        rows = _ROW + f"\nCodeRabbit\tpass\t2m\thttps://example/cr\t{description}"
        _, result = self._run(tmp_path, env_extra={"CI_STATUS_GH_TOKEN": "job-token", "STUB_GH_OUT": rows})
        assert result.returncode == 0, result.stderr
        assert "CI_NOTE" not in result.stdout

    def test_with_neither_token_fails_before_calling_github(self, tmp_path: Path) -> None:
        stubs, result = self._run(tmp_path, env_extra={})
        assert result.returncode != 0
        assert not (stubs / "seen_token").exists()


class TestPrTouchesWorkflows:
    # Replays STUB_FILES (a PR files API page) through the caller's own --jq filter.
    _GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$STUB_DIR/gh_argv"
[ "${STUB_GH_EXIT:-0}" -eq 0 ] || exit "${STUB_GH_EXIT}"
jqf=""
prev=""
for a in "$@"; do
  [ "$prev" = "--jq" ] && jqf="$a"
  prev="$a"
done
printf '%s' "$STUB_FILES" | jq -r "$jqf"
"""

    def _run(self, tmp_path: Path, files: list[str], *, gh_exit: int = 0) -> tuple[object, dict[str, str]]:
        stubs = stub_dir(tmp_path, {"gh": self._GH_STUB})
        out = tmp_path / "github_output"
        env = {
            "STUB_FILES": json.dumps([{"filename": f} for f in files]),
            "STUB_GH_EXIT": str(gh_exit),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
        }
        return run("pr-touches-workflows", ["77"], stubs, env), outputs(out)

    @pytest.mark.parametrize(
        ("files", "expected"),
        [
            pytest.param([".github/workflows/ci.yml"], "true", id="workflow-file"),
            pytest.param(["bin/x.sh", ".github/workflows/ci.yml"], "true", id="workflow-among-others"),
            pytest.param(["bin/x.sh", "src/a.py"], "false", id="no-workflow-file"),
            pytest.param([], "false", id="empty-diff"),
            # The anchor matters: these must NOT count as workflow files.
            pytest.param(["docs/.github/workflows/x.yml"], "false", id="nested-lookalike-path"),
            pytest.param([".github/workflows-notes.md"], "false", id="prefix-lookalike-path"),
        ],
    )
    def test_classification(self, tmp_path: Path, files: list[str], expected: str) -> None:
        result, outs = self._run(tmp_path, files)
        assert result.returncode == 0, result.stderr
        assert outs == {"wf": expected}

    def test_reads_the_prs_own_paginated_file_list(self, tmp_path: Path) -> None:
        """The PR's own file list is merge-base correct, and paginating it survives a diff too
        large for `gh pr diff`."""
        result, _ = self._run(tmp_path, ["bin/x.sh"])
        assert result.returncode == 0, result.stderr
        argv = (tmp_path / "stubs" / "gh_argv").read_text().splitlines()
        assert "--paginate" in argv
        assert "repos/owner/repo/pulls/77/files" in argv

    def test_a_gh_failure_fails_rather_than_classifying_as_false(self, tmp_path: Path) -> None:
        """A silent false sends a workflow PR to a bot that cannot review it, and the human waits
        on a review that never arrives."""
        result, outs = self._run(tmp_path, [".github/workflows/ci.yml"], gh_exit=1)
        assert result.returncode == 1
        assert "cannot classify" in result.stderr
        assert outs == {}


class TestPrCommentOnce:
    """The duplicate-comment guard. What the marker is keyed on is the caller's choice; this
    script only has to honour it in both directions."""

    def _run(
        self, tmp_path: Path, *, comments: list[dict], marker: str = "thing:abc", gh_exit: int = 0
    ) -> tuple[object, list[str]]:
        stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB})
        env = {
            "STUB_GH_COMMENTS": json.dumps(comments),
            "STUB_GH_POST": '{"id": 1}',
            "STUB_GH_EXIT": str(gh_exit),
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": "owner/repo",
        }
        result = run("pr-comment-once", ["77", marker, "the notice"], stubs, env)
        return result, gh_calls(stubs)

    def test_posts_when_the_marker_is_absent_and_carries_it_in_the_body(self, tmp_path: Path) -> None:
        result, calls = self._run(tmp_path, comments=[{"body": "an unrelated comment"}])
        assert result.returncode == 0, result.stderr
        post = posted_comment(calls)
        assert "the notice" in post
        assert "<!-- repo:thing:abc -->" in post

    def test_skips_when_the_marker_is_already_there(self, tmp_path: Path) -> None:
        result, calls = self._run(tmp_path, comments=[{"body": "said it\n\n<!-- repo:thing:abc -->"}])
        assert result.returncode == 0, result.stderr
        assert not any("-X POST" in c for c in calls)

    @pytest.mark.parametrize(
        "existing",
        [
            pytest.param("<!-- repo:thing:different -->", id="different-marker"),
            pytest.param("<!-- other-repo:thing:abc -->", id="same-marker-another-repo"),
        ],
    )
    def test_a_near_miss_marker_is_not_a_match(self, tmp_path: Path, existing: str) -> None:
        """The inverse of the skip: keying is the caller's whole mechanism (per-PR for a static
        notice, per-SHA for a verdict), so a near-miss marker must still post."""
        result, calls = self._run(tmp_path, comments=[{"body": existing}])
        assert result.returncode == 0, result.stderr
        assert "the notice" in posted_comment(calls)

    def test_an_unreadable_comment_list_fails_instead_of_posting(self, tmp_path: Path) -> None:
        """Fail loudly, never fail open: a transport error read as 'no existing comment' would
        post exactly the duplicate this script exists to prevent."""
        result, calls = self._run(tmp_path, comments=[], gh_exit=1)
        assert result.returncode != 0
        assert not any("-X POST" in c for c in calls)


class TestPrBaseIsDefault:
    """The stacked-PR gate: every other gate is scoped to the default branch, so a PR based on an
    agent branch runs no job and matches no rule."""

    @staticmethod
    def _run(tmp_path: Path, base: str, default: str):
        return run("pr-base-is-default", [base, default], stub_dir(tmp_path))

    def test_a_pr_onto_the_default_branch_passes(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, "main", "main")
        assert result.returncode == 0, result.stderr

    def test_a_pr_stacked_on_an_agent_branch_fails(self, tmp_path: Path) -> None:
        """The inverse, and the whole point: an inverted comparison here would green every
        stacked PR and no other gate in the repo would notice."""
        result = self._run(tmp_path, "agent/ABC-7", "main")
        assert result.returncode == 1
        assert "agent/ABC-7" in result.stdout + result.stderr

    def test_the_default_branch_is_an_argument_not_hardcoded(self, tmp_path: Path) -> None:
        """A repo whose default is not `main` must not have every PR rejected."""
        assert self._run(tmp_path, "trunk", "trunk").returncode == 0
        assert self._run(tmp_path, "main", "trunk").returncode == 1
