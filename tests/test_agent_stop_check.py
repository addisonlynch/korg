"""The implement run's Stop hook (agent-stop-check): refuses one early stop on an agent branch that
has neither an open PR nor a bail commit, and is inert everywhere else."""

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
    epic_exit: int = 3,
) -> tuple[list[str], dict | None]:
    epic_stub = f'#!/usr/bin/env bash\necho "$*" > "$STUB_DIR/epic_argv"\necho "{TEAM}-12 todo"\nexit {epic_exit}\n'
    stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB, "agent-epic": epic_stub})
    env = {"KORG_AGENT_RUN": mode, "STUB_GH_PR_LIST": json.dumps(prs or [])}
    result = run("agent-stop-check", [], stubs, env, cwd=repo, stdin=json.dumps({"stop_hook_active": active}))
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout) if result.stdout.strip() else None
    return gh_calls(stubs), decision


def test_no_pr_and_no_bail_blocks_the_stop(tmp_path: Path, repo: Path) -> None:
    _, decision = _run(tmp_path, repo)
    assert decision is not None and decision["decision"] == "block"
    assert "no open PR" in decision["reason"] and BRANCH in decision["reason"]


@pytest.mark.parametrize(("labels", "blocks"), [(["bug"], True), (["bug", "needs-review"], False)])
def test_an_open_pr_must_carry_needs_review(tmp_path: Path, repo: Path, labels: list[str], blocks: bool) -> None:
    _, decision = _run(tmp_path, repo, prs=[{"number": 7, "labels": [{"name": n} for n in labels]}])
    assert (decision is not None and "PR #7" in decision["reason"]) is blocks


def test_a_bail_commit_lets_it_stop(tmp_path: Path, repo: Path) -> None:
    _commit(repo, "WIP — bailed: x")
    _, decision = _run(tmp_path, repo)
    assert decision is None


def test_the_second_attempt_always_stops(tmp_path: Path, repo: Path) -> None:
    _, decision = _run(tmp_path, repo, active=True)
    assert decision is None


def test_inert_outside_an_implement_run(tmp_path: Path, repo: Path) -> None:
    calls, decision = _run(tmp_path, repo, mode="")
    assert decision is None
    assert calls == []


def test_off_an_agent_branch_it_lets_it_stop(tmp_path: Path, repo: Path) -> None:
    _git(repo, "checkout", "-q", "main")
    _, decision = _run(tmp_path, repo)
    assert decision is None


LABELLED = [{"number": 7, "labels": [{"name": "needs-review"}]}]


def test_an_incomplete_epic_pr_blocks_the_stop(tmp_path: Path, repo: Path) -> None:
    _, decision = _run(tmp_path, repo, prs=LABELLED, epic_exit=1)
    assert decision is not None and "epic is not complete" in decision["reason"]
    assert f"{TEAM}-12 todo" in decision["reason"]
    assert (tmp_path / "stubs" / "epic_argv").read_text().split() == ["check", f"{TEAM}-42"]


@pytest.mark.parametrize("epic_exit", [0, 3], ids=["complete-epic", "not-an-epic"])
def test_a_complete_epic_or_a_plain_ticket_lets_it_stop(tmp_path: Path, repo: Path, epic_exit: int) -> None:
    _, decision = _run(tmp_path, repo, prs=LABELLED, epic_exit=epic_exit)
    assert decision is None


def test_an_unreadable_epic_lets_it_stop_and_says_so(tmp_path: Path, repo: Path) -> None:
    stubs = stub_dir(tmp_path, {"gh": LOOP_GH_STUB, "agent-epic": "#!/usr/bin/env bash\necho boom >&2\nexit 2\n"})
    env = {"KORG_AGENT_RUN": "implement", "STUB_GH_PR_LIST": json.dumps(LABELLED)}
    result = run("agent-stop-check", [], stubs, env, cwd=repo, stdin=json.dumps({"stop_hook_active": False}))
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert "could not check" in result.stderr and "boom" in result.stderr
