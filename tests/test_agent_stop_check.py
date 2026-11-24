"""The implement run's Stop hook (agent-stop-check): refuses one early stop on an agent branch that
has neither a reviewable PR nor a bail commit, and is inert everywhere else."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from helpers import LOOP_GH_STUB, TEAM, gh_calls, run, stub_dir

BRANCH = f"agent/{TEAM}-42"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=os.environ, check=True, capture_output=True)


def _commit(repo: Path, subject: str) -> None:
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", subject)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".korg.yml").write_text(f"linear:\n  team: {TEAM}\n")
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", BRANCH)
    return repo


def _run(
    tmp_path: Path,
    repo: Path,
    *,
    mode: str = "implement",
    active: bool = False,
    prs: list[dict] | None = None,
    gh_exit: int = 0,
) -> tuple[Path, subprocess.CompletedProcess, dict | None]:
    stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB})
    env = {
        "KORG_AGENT_RUN": mode,
        "CLAUDE_PROJECT_DIR": str(repo),
        "STUB_GH_PR_LIST": json.dumps(prs or []),
        "STUB_GH_EXIT": str(gh_exit),
    }
    result = run("agent-stop-check", [], stubs, env, cwd=repo, stdin=json.dumps({"stop_hook_active": active}))
    decision = json.loads(result.stdout) if result.stdout.strip() else None
    return stubs, result, decision


def _pr(*labels: str, number: int = 7, fork: bool = False) -> dict:
    return {"number": number, "labels": [{"name": n} for n in labels], "isCrossRepository": fork}


def test_no_pr_and_no_bail_blocks_the_stop(tmp_path: Path, repo: Path) -> None:
    _, result, decision = _run(tmp_path, repo)
    assert result.returncode == 0, result.stderr
    assert decision is not None and decision["decision"] == "block"
    assert "no open PR" in decision["reason"] and BRANCH in decision["reason"]


def test_a_pr_without_needs_review_blocks_the_stop(tmp_path: Path, repo: Path) -> None:
    _, result, decision = _run(tmp_path, repo, prs=[_pr("bug")])
    assert result.returncode == 0, result.stderr
    assert decision is not None and decision["decision"] == "block"
    assert "PR #7" in decision["reason"] and "needs-review" in decision["reason"]


def test_a_pr_with_needs_review_lets_it_stop(tmp_path: Path, repo: Path) -> None:
    stubs, result, decision = _run(tmp_path, repo, prs=[_pr("bug", "needs-review")])
    assert result.returncode == 0, result.stderr
    assert decision is None
    assert f"--head {BRANCH} --state open" in gh_calls(stubs)[0]


def test_a_fork_pr_on_the_same_branch_name_is_not_the_runs(tmp_path: Path, repo: Path) -> None:
    """A fork can name its branch agent/<TEAM>-N; its PR must neither satisfy the hook nor be the
    one the agent is told to label."""
    _, result, decision = _run(tmp_path, repo, prs=[_pr("needs-review", number=9, fork=True), _pr("bug")])
    assert result.returncode == 0, result.stderr
    assert decision is not None and "PR #7" in decision["reason"]


def test_a_regex_in_the_team_key_is_matched_literally(tmp_path: Path, repo: Path) -> None:
    (repo / ".korg.yml").write_text("linear:\n  team: .*\n")
    _, result, decision = _run(tmp_path, repo)
    assert result.returncode == 0, result.stderr
    assert decision is None


def test_a_bail_commit_lets_it_stop(tmp_path: Path, repo: Path) -> None:
    _commit(repo, "WIP — bailed: x")
    _, result, decision = _run(tmp_path, repo)
    assert result.returncode == 0, result.stderr
    assert decision is None


def test_the_second_attempt_always_stops(tmp_path: Path, repo: Path) -> None:
    """One nudge, never a loop: the run's outcome stays the classifier's to judge."""
    _, result, decision = _run(tmp_path, repo, active=True)
    assert result.returncode == 0, result.stderr
    assert decision is None


@pytest.mark.parametrize("mode", ["", "respond"], ids=["unset", "respond"])
def test_inert_outside_an_implement_run(tmp_path: Path, repo: Path, mode: str) -> None:
    stubs, result, decision = _run(tmp_path, repo, mode=mode)
    assert result.returncode == 0, result.stderr
    assert decision is None
    assert gh_calls(stubs) == []


@pytest.mark.parametrize(
    "branch", ["main", "agent/XYZ-42", f"agent/{TEAM}-42-slug"], ids=["default", "other-team", "slug"]
)
def test_a_branch_that_is_not_this_tickets_lets_it_stop(tmp_path: Path, repo: Path, branch: str) -> None:
    """A spike or an early bail never leaves the default branch."""
    _git(repo, "checkout", "-q", "-B", branch)
    _, result, decision = _run(tmp_path, repo)
    assert result.returncode == 0, result.stderr
    assert decision is None


def test_an_unset_team_lets_it_stop_and_says_so(tmp_path: Path, repo: Path) -> None:
    (repo / ".korg.yml").write_text("linear: {}\n")
    stubs, result, decision = _run(tmp_path, repo)
    assert result.returncode == 0
    assert decision is None
    assert "linear.team" in result.stderr
    assert gh_calls(stubs) == []


def test_a_gh_failure_lets_it_stop_and_says_so(tmp_path: Path, repo: Path) -> None:
    _, result, decision = _run(tmp_path, repo, gh_exit=1)
    assert result.returncode == 0
    assert decision is None
    assert "gh pr list failed" in result.stderr
