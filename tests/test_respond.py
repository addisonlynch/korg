"""The respond run's own steps: resolving the PR (respond-resolve-pr), the pushless-round notice
(respond-flag-pushless) and the failure note (respond-note-failure)."""

import json
from pathlib import Path

from helpers import LOOP_GH_STUB, gh_calls, outputs, posted_comment, run, stub_dir

REPO = "owner/repo"

_CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$STUB_DIR/curl_argv"
echo "---" >> "$STUB_DIR/curl_argv"
[ "${STUB_CURL_EXIT:-0}" -eq 0 ] || exit "${STUB_CURL_EXIT}"
case "$*" in
  *"-X POST"*)
    prev=""
    for a in "$@"; do [ "$prev" = "-d" ] && printf '%s' "$a" > "$STUB_DIR/posted.json"; prev="$a"; done
    echo '{"id": 1}' ;;
  *--get*) printf '%s' "${STUB_PULLS:-[]}" ;;
  *)       printf '%s' "${STUB_PR:-}" ;;
esac
"""


def _pr(number: int = 77, ref: str = "agent/ABC-42", head_repo: str | None = REPO) -> dict:
    return {"number": number, "head": {"ref": ref, "repo": {"full_name": head_repo} if head_repo else None}}


class TestRespondResolvePr:
    def _run(self, tmp_path: Path, env: dict[str, str]) -> tuple[Path, object, dict[str, str]]:
        stubs = stub_dir(tmp_path, {"curl": _CURL_STUB})
        out = tmp_path / "github_output"
        base = {"GH_TOKEN": "tok", "GITHUB_REPOSITORY": REPO, "GITHUB_OUTPUT": str(out), "REPO_PRIVATE": "true"}
        result = run("respond-resolve-pr", [], stubs, base | env)
        return stubs, result, outputs(out)

    def test_a_public_repository_is_refused(self, tmp_path: Path) -> None:
        """Anyone can comment on a public repo's PRs, and the round acts on comments."""
        stubs, result, outs = self._run(
            tmp_path,
            {"REPO_PRIVATE": "false", "EVENT_NAME": "issue_comment", "EVENT_PR": "77", "STUB_PR": json.dumps(_pr())},
        )
        assert result.returncode == 1
        assert "not private" in result.stdout
        assert outs == {}

    def test_a_loop_trigger_resolves_the_open_pr_on_its_branch(self, tmp_path: Path) -> None:
        stubs, result, outs = self._run(
            tmp_path,
            {"EVENT_NAME": "workflow_run", "HEAD_BRANCH": "agent/ABC-42", "STUB_PULLS": json.dumps([_pr()])},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert outs == {"number": "77", "ref": "agent/ABC-42"}
        # Scoped to the repo owner's branch and to open PRs: a closed PR on a reused branch name
        # is not this run's PR.
        call = gh_calls(stubs, "curl_argv")[0]
        assert "head=owner:agent/ABC-42" in call and "state=open" in call

    def test_a_loop_trigger_whose_pr_closed_is_a_quiet_noop(self, tmp_path: Path) -> None:
        _, result, outs = self._run(
            tmp_path, {"EVENT_NAME": "workflow_run", "HEAD_BRANCH": "agent/ABC-42", "STUB_PULLS": "[]"}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert outs == {}

    def test_a_mention_resolves_the_payloads_pr(self, tmp_path: Path) -> None:
        _, result, outs = self._run(
            tmp_path, {"EVENT_NAME": "issue_comment", "EVENT_PR": "77", "STUB_PR": json.dumps(_pr())}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert outs == {"number": "77", "ref": "agent/ABC-42"}

    def test_a_fork_head_is_refused(self, tmp_path: Path) -> None:
        """The run holds a write token and executes the checkout's code."""
        _, result, outs = self._run(
            tmp_path,
            {"EVENT_NAME": "issue_comment", "EVENT_PR": "77", "STUB_PR": json.dumps(_pr(head_repo="someone/fork"))},
        )
        assert result.returncode == 1
        assert "fork" in result.stdout
        assert outs == {}

    def test_a_deleted_fork_head_is_refused(self, tmp_path: Path) -> None:
        _, result, outs = self._run(
            tmp_path, {"EVENT_NAME": "issue_comment", "EVENT_PR": "77", "STUB_PR": json.dumps(_pr(head_repo=None))}
        )
        assert result.returncode == 1
        assert outs == {}

    def test_an_api_failure_fails_rather_than_reading_as_no_pr(self, tmp_path: Path) -> None:
        _, result, outs = self._run(
            tmp_path, {"EVENT_NAME": "workflow_run", "HEAD_BRANCH": "agent/ABC-42", "STUB_CURL_EXIT": "22"}
        )
        assert result.returncode == 1
        assert outs == {}

    def test_an_unreadable_mentioned_pr_fails(self, tmp_path: Path) -> None:
        _, result, outs = self._run(tmp_path, {"EVENT_NAME": "issue_comment", "EVENT_PR": "77", "STUB_CURL_EXIT": "22"})
        assert result.returncode == 1
        assert outs == {}


# Delegates everything but the head read to LOOP_GH_STUB, so the real pr-comment-once runs against it.
_PUSHLESS_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  *git/ref/heads*)
    [ "${STUB_HEAD_EXIT:-0}" -eq 0 ] || exit "${STUB_HEAD_EXIT}"
    printf '%s\\n' "${STUB_HEAD:-}" ;;
  *) exec "$STUB_DIR/gh-loop" "$@" ;;
esac
"""


class TestRespondFlagPushless:
    def _run(self, tmp_path: Path, *, head: str, head_exit: int = 0) -> tuple[object, list[str]]:
        stubs = stub_dir(tmp_path, {"gh": _PUSHLESS_GH_STUB, "gh-loop": LOOP_GH_STUB})
        env = {
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": REPO,
            "STUB_HEAD": head,
            "STUB_HEAD_EXIT": str(head_exit),
            "STUB_GH_POST": '{"id": 1}',
        }
        result = run("respond-flag-pushless", ["77", "agent/ABC-42", "sha-before", "2"], stubs, env)
        return result, gh_calls(stubs)

    def test_a_round_that_pushed_posts_nothing(self, tmp_path: Path) -> None:
        result, calls = self._run(tmp_path, head="sha-after")
        assert result.returncode == 0, result.stdout + result.stderr
        assert not any("-X POST" in c for c in calls)

    def test_a_pushless_round_leaves_the_marker_the_gate_skips_on(self, tmp_path: Path) -> None:
        result, calls = self._run(tmp_path, head="sha-before")
        assert result.returncode == 0, result.stdout + result.stderr
        comment = posted_comment(calls)
        assert "round 2 ended without pushing" in comment
        assert "pushless-round:sha-before" in comment

    def test_an_unreadable_head_fails_rather_than_guessing(self, tmp_path: Path) -> None:
        result, calls = self._run(tmp_path, head="", head_exit=1)
        assert result.returncode == 1
        assert not any("-X POST" in c for c in calls)


class TestRespondNoteFailure:
    def _run(self, tmp_path: Path, env: dict[str, str]) -> tuple[object, dict | None]:
        stubs = stub_dir(tmp_path, {"curl": _CURL_STUB})
        result = run("respond-note-failure", [], stubs, {"GH_TOKEN": "tok", "GITHUB_REPOSITORY": REPO} | env)
        posted = stubs / "posted.json"
        return result, json.loads(posted.read_text()) if posted.exists() else None

    def test_a_failed_round_says_no_fix_was_pushed(self, tmp_path: Path) -> None:
        result, posted = self._run(tmp_path, {"PR": "77", "ACTION": "round"})
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No fix was pushed" in posted["body"]

    def test_a_failed_escalation_says_to_finish_the_surrender(self, tmp_path: Path) -> None:
        result, posted = self._run(tmp_path, {"PR": "77", "ACTION": "escalate"})
        assert result.returncode == 0, result.stdout + result.stderr
        assert "escalation failed partway" in posted["body"]

    def test_a_failure_before_the_pr_resolved_finds_it_by_branch(self, tmp_path: Path) -> None:
        result, posted = self._run(tmp_path, {"HEAD_BRANCH": "agent/ABC-42", "STUB_PULLS": json.dumps([_pr()])})
        assert result.returncode == 0, result.stdout + result.stderr
        assert posted is not None
        assert "noted the failure on PR #77" in result.stdout

    def test_a_failed_post_fails(self, tmp_path: Path) -> None:
        result, posted = self._run(tmp_path, {"PR": "77", "STUB_CURL_EXIT": "22"})
        assert result.returncode != 0
        assert posted is None

    def test_no_pr_to_find_posts_nothing(self, tmp_path: Path) -> None:
        result, posted = self._run(tmp_path, {"HEAD_BRANCH": "agent/ABC-42", "STUB_PULLS": "[]"})
        assert result.returncode == 0, result.stdout + result.stderr
        assert posted is None
