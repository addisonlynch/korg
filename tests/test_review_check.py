"""The agent-review check run and the review-submitted guard: publish-review-check,
review-check-finalize, pr-review-count, verify-review-submitted."""

import json
from pathlib import Path

import pytest
from helpers import LOOP_GH_STUB, TOKEN_RECORDING_GH_STUB, gh_calls, outputs, run, stub_dir


class TestPublishReviewCheck:
    """The agent-review check run is the review verdict."""

    def _run(
        self,
        tmp_path: Path,
        args: list[str],
        *,
        gh_json: str = '{"id": 555}',
        gh_exit: int = 0,
        check_run_id: str | None = "555",
    ) -> tuple[object, dict[str, str], list[str]]:
        stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB})
        out = tmp_path / "github_output"
        env = {
            "STUB_GH_CHECKS": gh_json,
            "STUB_GH_EXIT": str(gh_exit),
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
        }
        if check_run_id is not None:
            env["CHECK_RUN_ID"] = check_run_id
        result = run("publish-review-check", args, stubs, env)
        return result, outputs(out), gh_calls(stubs)

    def test_open_creates_a_pending_run_on_the_head_sha_and_emits_its_id(self, tmp_path: Path) -> None:
        result, outs, calls = self._run(tmp_path, ["open", "77", "abc123"])
        assert result.returncode == 0, result.stderr
        assert outs == {"check_run_id": "555"}
        (call,) = calls
        for expected in (
            "repos/owner/repo/check-runs",
            "POST",
            "name=agent-review",
            "head_sha=abc123",
            "status=in_progress",
        ):
            assert expected in call

    def test_open_with_no_id_in_the_response_fails(self, tmp_path: Path) -> None:
        """An unopened check with a green step would let the finalize step silently no-op."""
        result, outs, _ = self._run(tmp_path, ["open", "77", "abc123"], gh_json="{}")
        assert result.returncode == 1
        assert outs == {}

    @pytest.mark.parametrize("conclusion", ["success", "failure"])
    def test_close_completes_the_run_with_the_verdict(self, tmp_path: Path, conclusion: str) -> None:
        """The run id comes from CHECK_RUN_ID in the environment, never an argument: the
        reviewer's sandbox refuses any command carrying a `$` expansion, so the agent must
        be able to invoke close with literals only."""
        result, _, calls = self._run(tmp_path, ["close", conclusion, "Title", "Summary"])
        assert result.returncode == 0, result.stderr
        (call,) = calls
        for expected in (
            "repos/owner/repo/check-runs/555",
            "PATCH",
            "status=completed",
            f"conclusion={conclusion}",
            "output[title]=Title",
        ):
            assert expected in call

    def test_close_without_a_check_run_id_is_a_local_run_noop(self, tmp_path: Path) -> None:
        """No CHECK_RUN_ID means a local/interactive review with no check open: the agent
        always calls close, and the script is what knows there is nothing to close."""
        result, _, calls = self._run(tmp_path, ["close", "success", "Title"], check_run_id=None)
        assert result.returncode == 0, result.stderr
        assert calls == []
        assert "nothing to close" in result.stdout

    @pytest.mark.parametrize(
        "conclusion",
        [pytest.param("clean", id="made-up-verdict"), pytest.param("neutral", id="no-neutral-caller")],
    )
    def test_close_refuses_an_unknown_conclusion_before_calling_github(self, tmp_path: Path, conclusion: str) -> None:
        """`cancelled` etc. would 422 server-side; and `neutral` has no caller — the
        workflow-file route opens no check at all, so a third verdict is a bug."""
        result, _, calls = self._run(tmp_path, ["close", conclusion, "Title"])
        assert result.returncode == 1
        assert calls == []

    def test_an_api_failure_fails_the_step(self, tmp_path: Path) -> None:
        result, _, _ = self._run(tmp_path, ["open", "77", "abc123"], gh_exit=1)
        assert result.returncode == 1

    def test_close_prefers_the_job_token_over_the_ambient_app_token(self, tmp_path: Path) -> None:
        """The agent sandbox refuses a `GH_TOKEN=…` command prefix, so the reviewer calls
        close bare and the script swaps in CI_STATUS_GH_TOKEN itself — the ambient App
        token cannot write checks."""
        stubs = stub_dir(tmp_path, {"gh": TOKEN_RECORDING_GH_STUB})
        env = {
            "GH_TOKEN": "app-token",
            "CI_STATUS_GH_TOKEN": "job-token",
            "CHECK_RUN_ID": "555",
            "GITHUB_REPOSITORY": "owner/repo",
        }
        result = run("publish-review-check", ["close", "success", "Title", "Summary"], stubs, env)
        assert result.returncode == 0, result.stderr
        assert (stubs / "seen_token").read_text().strip() == "job-token"

    def test_close_with_neither_token_fails_before_calling_github(self, tmp_path: Path) -> None:
        stubs = stub_dir(tmp_path, {"gh": TOKEN_RECORDING_GH_STUB})
        env = {"CHECK_RUN_ID": "555", "GITHUB_REPOSITORY": "owner/repo"}
        result = run("publish-review-check", ["close", "success", "Title"], stubs, env)
        assert result.returncode != 0
        assert not (stubs / "seen_token").exists()


class TestReviewCheckFinalize:
    """Absent-never-green for the check itself: a reviewer that never answered is a failure,
    but a `forced` one that must not dispatch a fix round."""

    def _run(self, tmp_path: Path, *, check: dict, gh_exit: int = 0) -> tuple[object, dict[str, str], list[str]]:
        stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB})
        out = tmp_path / "github_output"
        env = {
            "STUB_GH_CHECKS": json.dumps(check),
            "STUB_GH_EXIT": str(gh_exit),
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
        }
        result = run("review-check-finalize", ["555"], stubs, env)
        return result, outputs(out), gh_calls(stubs)

    @pytest.mark.parametrize("conclusion", ["success", "failure"])
    def test_a_completed_check_passes_through_unforced(self, tmp_path: Path, conclusion: str) -> None:
        result, outs, calls = self._run(tmp_path, check={"status": "completed", "conclusion": conclusion})
        assert result.returncode == 0, result.stderr
        assert outs == {"conclusion": conclusion, "forced": "false"}
        assert not any("PATCH" in c for c in calls)

    def test_a_still_open_check_is_forced_to_failure(self, tmp_path: Path) -> None:
        result, outs, calls = self._run(tmp_path, check={"status": "in_progress"})
        assert result.returncode == 0, result.stderr
        assert outs == {"conclusion": "failure", "forced": "true"}
        patch = next(c for c in calls if "PATCH" in c)
        assert "conclusion=failure" in patch
        # The machine flag that tells a crash from a findings verdict.
        assert "external_id=forced" in patch

    def test_an_unreadable_check_fails_rather_than_guessing(self, tmp_path: Path) -> None:
        result, outs, _ = self._run(tmp_path, check={}, gh_exit=1)
        assert result.returncode == 1
        assert outs == {}


class TestPrReviewCountAndVerify:
    def _stubs(self, tmp_path: Path, *, count: str, gh_exit: int = 0) -> Path:
        gh = (
            "#!/usr/bin/env bash\n"
            'printf \'%s\\n\' "$@" >> "$STUB_DIR/gh_argv"\n'
            'echo "---" >> "$STUB_DIR/gh_argv"\n'
            'case "$2" in comment) exit 0 ;; esac\n'
            f"[ {gh_exit} -eq 0 ] || exit {gh_exit}\n"
            f"printf '%s' '{count}'\n"
        )
        return stub_dir(tmp_path, {"gh": gh})

    def _env(self, out: Path, before: str | None = None) -> dict[str, str]:
        env = {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_OUTPUT": str(out)}
        if before is not None:
            env["BEFORE"] = before
        return env

    def test_counts_the_reviews(self, tmp_path: Path) -> None:
        stubs = self._stubs(tmp_path, count="3")
        out = tmp_path / "o"
        result = run("pr-review-count", ["77"], stubs, self._env(out))
        assert result.returncode == 0, result.stderr
        assert outputs(out) == {"count": "3"}

    def test_an_unreadable_count_is_empty_not_a_failure(self, tmp_path: Path) -> None:
        """It runs before the reviewer; going red here would block the review it measures."""
        stubs = self._stubs(tmp_path, count="3", gh_exit=1)
        out = tmp_path / "o"
        result = run("pr-review-count", ["77"], stubs, self._env(out))
        assert result.returncode == 0, result.stderr
        assert outputs(out) == {"count": ""}

    def test_a_new_review_passes(self, tmp_path: Path) -> None:
        stubs = self._stubs(tmp_path, count="4")
        result = run("verify-review-submitted", ["77"], stubs, self._env(tmp_path / "o", before="3"))
        assert result.returncode == 0, result.stderr
        assert "3 -> 4" in result.stdout

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            pytest.param("3", "3", id="count-unchanged-silent-noop"),
            pytest.param("3", "2", id="count-went-down"),
            pytest.param("", "4", id="before-unknown"),
            pytest.param("3", "", id="after-unreadable"),
        ],
    )
    def test_fails_closed_and_says_so_on_the_pr(self, tmp_path: Path, before: str, after: str) -> None:
        """The action reports success even when the orchestrator posted nothing, so a green review
        step is not proof of a review."""
        stubs = self._stubs(tmp_path, count=after)
        result = run("verify-review-submitted", ["77"], stubs, self._env(tmp_path / "o", before=before))
        assert result.returncode == 1
        assert "failing so needs-review stays" in result.stdout
        assert "pr comment" in (stubs / "gh_argv").read_text().replace("\n", " ")
