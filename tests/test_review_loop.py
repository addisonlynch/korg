"""The review loop: whether a respond run fixes, escalates or does nothing (review-loop-gate), the
round counter (review-loop-record), and the surrender (review-loop-escalate)."""

import json
import os
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from helpers import (
    KORG_CONFIG_STUB,
    LOOP_GH_STUB,
    NO_CONFIG_STUB,
    OWNER,
    TEAM,
    gh_calls,
    outputs,
    posted_comment,
    run,
    stub_dir,
)

BRANCH = f"agent/{TEAM}-42"

_BOT_EMAIL = "41898282+claude[bot]@users.noreply.github.com"
_HUMAN_EMAIL = "dev@example.com"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, env=os.environ, capture_output=True, text=True)
    assert result.returncode == 0, f"git {args}: {result.stderr}"
    return result.stdout.strip()


def _commit(cwd: Path, subject: str, *, email: str, trailer: int | None = None) -> None:
    msg = subject if trailer is None else f"{subject}\n\nAuto-Fix-Round: {trailer}"
    _git(cwd, "-c", f"user.email={email}", "-c", "user.name=someone", "commit", "--allow-empty", "-m", msg)


def _check_json(status: str, conclusion: str | None = None, external_id: str = "") -> str:
    check: dict = {"id": 9, "status": status, "external_id": external_id}
    if conclusion is not None:
        check["conclusion"] = conclusion
    return json.dumps({"check_runs": [check]})


# Fails only the PR comments read; every other call goes to the dispatching stub.
_COMMENTS_READ_FAILS_GH_STUB = """#!/usr/bin/env bash
case "$*" in *--paginate*) exit 1 ;; esac
exec "$STUB_DIR/gh-loop" "$@"
"""


class TestReviewLoopGate:
    """The round budget is reconstructed from Auto-Fix-Round trailers, never stored; every guard
    keys off the PR's current state so duplicate triggers self-neutralize."""

    _FINDINGS_CHECK = _check_json("completed", "failure")

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        """A real repo on the agent branch with origin/main resolvable (the remote is the repo
        itself: `git fetch origin main` only needs the ref to exist)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _commit(repo, "base", email=_HUMAN_EMAIL)
        _git(repo, "checkout", "-q", "-b", BRANCH)
        _git(repo, "remote", "add", "origin", str(repo))
        return repo

    def _view(self, repo: Path, **patch) -> dict:
        head = _git(repo, "rev-parse", "HEAD")
        return {"state": "OPEN", "baseRefName": "main", "headRefName": BRANCH, "headRefOid": head, "labels": []} | patch

    def _run(
        self,
        repo: Path,
        tmp_path: Path,
        *,
        source: str = "loop",
        pr_view: dict | None = None,
        checks: str | None = None,
        comments: list[dict] | None = None,
        gh_exit: int = 0,
        stubs: dict[str, str] | None = None,
    ) -> tuple[object, dict[str, str], list[str]]:
        stub_path = stub_dir(tmp_path, stubs or {"gh": LOOP_GH_STUB, "korg-config": KORG_CONFIG_STUB})
        out = tmp_path / "github_output"
        env = {
            "STUB_GH_PR_VIEW": json.dumps(pr_view or self._view(repo)),
            "STUB_GH_CHECKS": checks if checks is not None else self._FINDINGS_CHECK,
            "STUB_GH_COMMENTS": json.dumps(comments or []),
            "STUB_GH_EXIT": str(gh_exit),
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
        }
        result = run("review-loop-gate", ["77", source], stub_path, env, cwd=repo)
        return result, outputs(out), gh_calls(stub_path)

    def test_a_human_round_is_never_counted_or_capped(self, repo: Path, tmp_path: Path) -> None:
        for n in (1, 2, 3):
            _commit(repo, f"round {n}", email=_BOT_EMAIL, trailer=n)
        result, outs, _ = self._run(repo, tmp_path, source="human")
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "0"}

    def test_an_unknown_source_refuses(self, repo: Path, tmp_path: Path) -> None:
        result, outs, _ = self._run(repo, tmp_path, source="auto")
        assert result.returncode == 1
        assert outs == {}

    def test_a_fresh_red_verdict_is_round_one(self, repo: Path, tmp_path: Path) -> None:
        _commit(repo, "fix", email=_BOT_EMAIL)
        result, outs, _ = self._run(repo, tmp_path)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "1"}

    def test_only_trailer_commits_count_as_rounds(self, repo: Path, tmp_path: Path) -> None:
        _commit(repo, "round 1", email=_BOT_EMAIL, trailer=1)
        _commit(repo, "fix a", email=_BOT_EMAIL)
        _commit(repo, "round 2", email=_BOT_EMAIL, trailer=2)
        _commit(repo, "fix b", email=_BOT_EMAIL)
        result, outs, _ = self._run(repo, tmp_path)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "3"}

    def test_the_budget_spent_escalates(self, repo: Path, tmp_path: Path) -> None:
        for n in (1, 2, 3):
            _commit(repo, f"round {n}", email=_BOT_EMAIL, trailer=n)
        result, outs, _ = self._run(repo, tmp_path)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "escalate"}

    def test_a_human_commit_resets_the_budget(self, repo: Path, tmp_path: Path) -> None:
        """The inverse of the cap: three spent rounds followed by a human touch is a fresh budget,
        not an escalation."""
        for n in (1, 2, 3):
            _commit(repo, f"round {n}", email=_BOT_EMAIL, trailer=n)
        _commit(repo, "human tweak", email=_HUMAN_EMAIL)
        result, outs, _ = self._run(repo, tmp_path)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "1"}

    def test_trailers_above_the_human_commit_still_count(self, repo: Path, tmp_path: Path) -> None:
        _commit(repo, "human tweak", email=_HUMAN_EMAIL)
        _commit(repo, "round 1", email=_BOT_EMAIL, trailer=1)
        result, outs, _ = self._run(repo, tmp_path)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "2"}

    @pytest.mark.parametrize(
        ("view_patch", "checks"),
        [
            pytest.param({"state": "MERGED"}, None, id="merged-pr"),
            pytest.param({"headRefName": "fix/manual"}, None, id="human-branch"),
            pytest.param({"headRefName": "agent/XYZ-42"}, None, id="another-teams-agent-branch"),
            pytest.param({}, '{"check_runs": []}', id="no-check-on-head"),
            pytest.param({}, _check_json("completed", "success"), id="green-verdict"),
            pytest.param({}, _check_json("in_progress"), id="fresh-review-in-flight"),
            pytest.param(
                {},
                _check_json("completed", "failure", external_id="forced"),
                id="crashed-review-has-no-findings",
            ),
            pytest.param(
                {"labels": [{"name": "needs-review"}, {"name": "no-auto-review"}]}, None, id="no-auto-review-skips"
            ),
        ],
    )
    def test_stale_or_unactionable_state_skips(
        self, repo: Path, tmp_path: Path, view_patch: dict, checks: str | None
    ) -> None:
        result, outs, _ = self._run(repo, tmp_path, pr_view=self._view(repo, **view_patch), checks=checks)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "skip"}

    def test_other_labels_do_not_trip_the_kill_switch(self, repo: Path, tmp_path: Path) -> None:
        """The inverse of the no-auto-review skip: an unrelated label still rounds."""
        view = self._view(repo, labels=[{"name": "needs-review"}])
        result, outs, _ = self._run(repo, tmp_path, pr_view=view)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "1"}

    def test_a_human_round_ignores_the_kill_switch(self, repo: Path, tmp_path: Path) -> None:
        """@claude is an explicit human action; no-auto-review only stops the autonomous loop."""
        view = self._view(repo, labels=[{"name": "no-auto-review"}])
        result, outs, _ = self._run(repo, tmp_path, source="human", pr_view=view)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "0"}

    def test_the_newest_check_run_wins(self, repo: Path, tmp_path: Path) -> None:
        """A retried review leaves its predecessor on the same SHA; the verdict is the newest run,
        not the first match."""
        checks = json.dumps(
            {
                "check_runs": [
                    {"id": 8, "status": "completed", "conclusion": "failure", "external_id": "forced"},
                    {"id": 9, "status": "completed", "conclusion": "failure", "external_id": ""},
                ]
            }
        )
        result, outs, _ = self._run(repo, tmp_path, checks=checks)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "1"}

    def test_a_pushless_round_on_this_head_skips(self, repo: Path, tmp_path: Path) -> None:
        """Without a push the round never reaches the trailer count, so a duplicate trigger would
        rerun a round that already found nothing it could change."""
        head = _git(repo, "rev-parse", "HEAD")
        comments = [{"body": f"nothing to push\n\n<!-- repo:pushless-round:{head} -->"}]
        result, outs, calls = self._run(repo, tmp_path, comments=comments)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "skip"}
        assert any("--paginate" in c and "repos/owner/repo/issues/77/comments" in c for c in calls)

    def test_a_pushless_round_on_an_older_head_does_not_skip(self, repo: Path, tmp_path: Path) -> None:
        """The inverse: a push since the pushless round is new work, and its red verdict rounds."""
        older = _git(repo, "rev-parse", "HEAD")
        _commit(repo, "fix", email=_BOT_EMAIL)
        comments = [{"body": f"nothing to push\n\n<!-- repo:pushless-round:{older} -->"}]
        result, outs, _ = self._run(repo, tmp_path, comments=comments)
        assert result.returncode == 0, result.stderr
        assert outs == {"action": "round", "round": "1"}

    def test_an_unreadable_comment_list_fails_rather_than_guessing_a_round(self, repo: Path, tmp_path: Path) -> None:
        result, outs, _ = self._run(
            repo,
            tmp_path,
            stubs={"gh": _COMMENTS_READ_FAILS_GH_STUB, "gh-loop": LOOP_GH_STUB, "korg-config": KORG_CONFIG_STUB},
        )
        assert result.returncode == 1
        assert "could not read comments" in result.stdout
        assert outs == {}

    def test_an_unreadable_pr_fails_rather_than_guessing_a_round(self, repo: Path, tmp_path: Path) -> None:
        result, outs, _ = self._run(repo, tmp_path, gh_exit=1)
        assert result.returncode == 1
        assert outs == {}

    def test_an_unset_team_refuses_a_loop_round(self, repo: Path, tmp_path: Path) -> None:
        """Without a team key there is no agent-branch prefix to match."""
        result, outs, _ = self._run(repo, tmp_path, stubs={"gh": LOOP_GH_STUB, "korg-config": NO_CONFIG_STUB})
        assert result.returncode == 1
        assert "linear.team" in result.stdout
        assert outs == {}


class TestReviewLoopRecord:
    """The trailer commit IS the round counter. It is committed, never pushed: the agent's own fix
    push carries it, so a round that produces nothing leaves the remote head (and its checks)
    untouched."""

    @pytest.fixture()
    def clone(self, tmp_path: Path) -> Path:
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, capture_output=True)
        _git(clone, "checkout", "-q", "-b", BRANCH)
        _commit(clone, "base", email=_HUMAN_EMAIL)
        _git(clone, "push", "-q", "-u", "origin", BRANCH)
        return clone

    def test_records_an_inert_bot_authored_trailer_commit_locally(self, tmp_path: Path, clone: Path) -> None:
        remote_before = _git(clone, "ls-remote", "origin", BRANCH).split()[0]
        result = run("review-loop-record", ["2"], stub_dir(tmp_path), cwd=clone)
        assert result.returncode == 0, result.stderr
        assert _git(clone, "log", "-1", "--format=%(trailers:key=Auto-Fix-Round,valueonly)") == "2"
        # GitHub honours `[skip ci]` for pull_request too: as the head of a pushless round it
        # would suppress every trigger on the PR.
        assert "[skip ci]" not in _git(clone, "log", "-1", "--format=%B")
        # The gate tells bot commits from human ones by this suffix.
        assert "[bot]" in _git(clone, "log", "-1", "--format=%ae")
        # Not pushed: the remote head is untouched until the agent's own push.
        remote_after = _git(clone, "ls-remote", "origin", BRANCH).split()[0]
        assert remote_after == remote_before
        assert remote_after != _git(clone, "rev-parse", "HEAD")


# Sequenced curl stub for escalate's Linear calls: call N replays $STUB_CURL_BODY_N, so the read and
# each mutation get their own response.
_SEQ_CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$STUB_DIR/curl_argv"
echo "---" >> "$STUB_DIR/curl_argv"
n=$(( $(cat "$STUB_DIR/curl_n" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STUB_DIR/curl_n"
[ "${STUB_CURL_EXIT:-0}" -eq 0 ] || exit "${STUB_CURL_EXIT}"
eval "printf '%s' \\"\\${STUB_CURL_BODY_$n:-}\\""
"""

# A success body for every Linear mutation escalate makes; replayed for whichever call index a test
# does not pin to something else.
_LINEAR_OK = json.dumps(
    {
        "data": {
            "issueUpdate": {"success": True, "issue": {"assignee": {"id": "user-owner"}}},
            "issueRemoveLabel": {"success": True},
            "commentCreate": {"success": True},
        }
    }
)


def _issue_read(
    *,
    labels: list[dict] | None = None,
    states: tuple[str, ...] = ("Needs Human", "Todo"),
    users: tuple[str, ...] = ("user-owner",),
    comments: tuple[str, ...] = (),
) -> dict:
    issue: dict = {
        "id": "issue-1",
        "labels": {"nodes": [{"id": "lbl-ready", "name": "agent-ready"}] if labels is None else labels},
        "team": {"states": {"nodes": [{"id": f"st-{s}", "name": s} for s in states]}},
        "comments": {"nodes": [{"body": b} for b in comments]},
    }
    return {"data": {"issue": issue, "users": {"nodes": [{"id": u} for u in users]}}}


class TestReviewLoopEscalate:
    """Surrender semantics: Needs Human + assignee + agent-ready strip + the findings verbatim, and
    any Linear failure is loud."""

    _THREADS: ClassVar[dict] = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [{"body": "[fix here] broken thing", "path": "a.py", "line": 12}]
                                },
                            },
                            {
                                "isResolved": True,
                                "comments": {"nodes": [{"body": "[nit] fixed already", "path": "b.py", "line": 3}]},
                            },
                        ]
                    }
                }
            }
        }
    }

    # A completed, unforced failure on the current head: the only state that escalates.
    _RED_CHECK: ClassVar[dict] = {
        "check_runs": [{"id": 9, "status": "completed", "conclusion": "failure", "external_id": "review"}]
    }

    def _run(
        self,
        tmp_path: Path,
        *,
        issue: dict | None = None,
        head_ref: str = BRANCH,
        bodies: dict[int, str] | None = None,
        threads: dict | None = None,
        check: dict | None = None,
        comments: list[dict] | None = None,
        korg_config: str = KORG_CONFIG_STUB,
    ) -> tuple[object, list[str], list[str]]:
        # pr-comment-once is the real one from the bin dir: it is the PR-side dedup under test.
        stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB, "curl": _SEQ_CURL_STUB, "korg-config": korg_config})
        default_bodies = {1: json.dumps(issue or _issue_read()), 2: _LINEAR_OK, 3: _LINEAR_OK, 4: _LINEAR_OK}
        env = {
            "STUB_GH_PR_VIEW": json.dumps({"headRefName": head_ref, "headRefOid": "sha-head"}),
            "STUB_GH_GRAPHQL": json.dumps(threads or self._THREADS),
            "STUB_GH_CHECKS": json.dumps(self._RED_CHECK if check is None else check),
            "STUB_GH_COMMENTS": json.dumps(comments or []),
            "STUB_GH_POST": '{"id": 1}',
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": "owner/repo",
            "LINEAR_API_KEY": "lin",
        }
        for n, body in (bodies or default_bodies).items():
            env[f"STUB_CURL_BODY_{n}"] = body
        result = run("review-loop-escalate", ["77"], stubs, env)
        curl_path = stubs / "curl_argv"
        curls = (
            [c.replace("\n", " ") for c in curl_path.read_text().split("---") if c.strip()]
            if curl_path.exists()
            else []
        )
        return result, gh_calls(stubs), curls

    def test_the_full_surrender_lands(self, tmp_path: Path) -> None:
        result, gh, curls = self._run(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout
        # The PR gets the record, carrying the unresolved finding verbatim (never the resolved one),
        # tagged with the per-head marker pr-comment-once writes.
        pr_comment = posted_comment(gh)
        assert "[fix here] broken thing" in pr_comment
        assert "a.py:12" in pr_comment
        assert "[nit] fixed already" not in pr_comment
        assert "<!-- repo:review-loop-escalated:sha-head -->" in pr_comment
        # The assignee is resolved BY NAME: under CI's token `viewer` is the app actor, and
        # assigning it would move the state while notifying nobody.
        read = curls[0].replace(" ", "")
        assert f'"owner":"{OWNER.replace(" ", "")}"' in read
        # Linear: state + assignee in one mutation, claim consumed, findings recorded with the
        # bare head marker.
        update = next(c for c in curls if "issueUpdate" in c)
        assert '"state":"st-Needs Human"' in update and '"assignee":"user-owner"' in update
        assert '"label":"lbl-ready"' in next(c for c in curls if "issueRemoveLabel" in c)
        record = next(c for c in curls if "commentCreate" in c)
        assert "[fix here] broken thing" in record
        assert "<!-- review-loop-escalated:sha-head -->" in record

    def test_without_the_claim_label_the_strip_is_skipped(self, tmp_path: Path) -> None:
        issue = _issue_read(labels=[])
        result, _, curls = self._run(tmp_path, bodies={1: json.dumps(issue), 2: _LINEAR_OK, 3: _LINEAR_OK})
        assert result.returncode == 0, result.stderr + result.stdout
        assert not any("issueRemoveLabel" in c for c in curls)

    def test_a_non_agent_branch_has_no_ticket_and_fails(self, tmp_path: Path) -> None:
        result, gh, curls = self._run(tmp_path, head_ref="fix/manual")
        assert result.returncode == 1
        assert not any("comments" in c for c in gh)
        assert curls == []

    def test_runaway_findings_are_truncated_not_fatal(self, tmp_path: Path) -> None:
        """GitHub's comment limit is 65536 chars; a huge review round must not make the surrender
        itself fail on body size."""
        huge = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {"nodes": [{"body": "x" * 40000, "path": "a.py", "line": 1}]},
                                }
                            ]
                        }
                    }
                }
            }
        }
        result, gh, _ = self._run(tmp_path, threads=huge)
        assert result.returncode == 0, result.stderr + result.stdout
        pr_comment = posted_comment(gh)
        assert "truncated" in pr_comment
        assert len(pr_comment) < 35000

    @pytest.mark.parametrize(
        "check",
        [
            pytest.param({"check_runs": [{"id": 9, "status": "completed", "conclusion": "success"}]}, id="now-green"),
            pytest.param({"check_runs": [{"id": 9, "status": "in_progress", "conclusion": None}]}, id="still-running"),
            pytest.param(
                {"check_runs": [{"id": 9, "status": "completed", "conclusion": "failure", "external_id": "forced"}]},
                id="forced-failure",
            ),
            pytest.param({"check_runs": []}, id="no-check"),
        ],
    )
    def test_a_verdict_that_is_no_longer_red_does_not_escalate(self, tmp_path: Path, check: dict) -> None:
        """The gate's read and the reviewer's write are in different concurrency domains, so the
        verdict is re-read against the current head before surrendering."""
        result, gh, curls = self._run(tmp_path, check=check)
        assert result.returncode == 0, result.stderr + result.stdout
        assert not any("-X POST" in c for c in gh)
        assert curls == []

    def test_a_second_dispatch_on_the_same_head_posts_no_second_comment(self, tmp_path: Path) -> None:
        """The per-PR concurrency group serializes duplicate dispatches without deduping them."""
        marker = "<!-- repo:review-loop-escalated:sha-head -->"
        result, gh, _ = self._run(tmp_path, comments=[{"body": f"already said this\n\n{marker}"}])
        assert result.returncode == 0, result.stderr + result.stdout
        assert not any("-X POST" in c for c in gh)

    def test_an_escalation_on_a_different_head_still_speaks_up(self, tmp_path: Path) -> None:
        """The inverse, and the reason the marker is keyed on the SHA: a fresh push plus another
        red verdict is exactly the moment to re-notify."""
        stale = "<!-- repo:review-loop-escalated:sha-older -->"
        result, gh, _ = self._run(tmp_path, comments=[{"body": f"an earlier head\n\n{stale}"}])
        assert result.returncode == 0, result.stderr + result.stdout
        assert "[fix here] broken thing" in posted_comment(gh)

    def test_a_second_dispatch_leaves_no_second_linear_comment(self, tmp_path: Path) -> None:
        """The state writes are idempotent; commentCreate is not. It dedupes on the same head
        marker, off the comments the issue read already carries."""
        issue = _issue_read(comments=("said this\n\n<!-- review-loop-escalated:sha-head -->",))
        result, _, curls = self._run(tmp_path, bodies={1: json.dumps(issue), 2: _LINEAR_OK, 3: _LINEAR_OK})
        assert result.returncode == 0, result.stderr + result.stdout
        assert not any("commentCreate" in c for c in curls)
        # The surrender itself still lands: the ticket ends up Needs Human either way.
        assert any("issueUpdate" in c for c in curls)

    def test_a_linear_record_from_an_earlier_head_does_not_suppress_this_one(self, tmp_path: Path) -> None:
        """The inverse: a prior surrender on an older commit is not this one's record."""
        issue = _issue_read(comments=("older\n\n<!-- review-loop-escalated:sha-older -->",))
        result, _, curls = self._run(tmp_path, issue=issue)
        assert result.returncode == 0, result.stderr + result.stdout
        assert any("commentCreate" in c for c in curls)

    def test_a_slug_suffixed_branch_still_resolves_the_ticket(self, tmp_path: Path) -> None:
        """Suffix stripping would send Linear the whole tail and the escalation would 404."""
        result, _, curls = self._run(tmp_path, head_ref=f"{BRANCH}-fix-thing")
        assert result.returncode == 0, result.stderr + result.stdout
        assert f'"id":"{TEAM}-42"' in curls[0].replace(" ", "")

    @pytest.mark.parametrize(
        "bodies",
        [
            pytest.param({1: '{"data": {"issue": null}}'}, id="unknown-ticket"),
            pytest.param({1: json.dumps(_issue_read(labels=[], states=("Todo",)))}, id="missing-needs-human-state"),
            pytest.param(
                {1: json.dumps(_issue_read()), 2: '{"data": {"issueUpdate": {"success": false}}}'},
                id="issue-update-failed",
            ),
            pytest.param({1: json.dumps(_issue_read(labels=[], users=()))}, id="no-such-owner"),
            pytest.param(
                {1: json.dumps(_issue_read(labels=[], users=("user-owner", "user-owner-2")))}, id="duplicate-owner-name"
            ),
            pytest.param(
                {
                    1: json.dumps(_issue_read()),
                    2: '{"data": {"issueUpdate": {"success": true, "issue": {"assignee": null}}}}',
                },
                id="assignment-silently-dropped",
            ),
        ],
    )
    def test_any_linear_failure_is_loud_and_leaves_no_pr_record(self, tmp_path: Path, bodies: dict) -> None:
        """A half-landed surrender goes red, and the PR carries no record claiming it happened: that
        record would also dedupe away the rerun."""
        result, gh, _ = self._run(tmp_path, bodies=bodies)
        assert result.returncode == 1
        assert not any("-X POST" in c for c in gh)

    @pytest.mark.parametrize(
        ("korg_config", "key"),
        [
            pytest.param(NO_CONFIG_STUB, "linear.team", id="no-team"),
            pytest.param(
                f'#!/usr/bin/env bash\ncase "$1" in linear.team) echo {TEAM} ;; esac\n', "linear.owner", id="no-owner"
            ),
        ],
    )
    def test_an_unset_config_key_refuses_before_any_write(self, tmp_path: Path, korg_config: str, key: str) -> None:
        """Without a team there is no ticket to resolve; without an owner nobody would be notified."""
        result, gh, curls = self._run(tmp_path, korg_config=korg_config)
        assert result.returncode == 1
        assert key in result.stdout
        assert gh == []
        assert curls == []
