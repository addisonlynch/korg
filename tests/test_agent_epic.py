"""agent-epic: the epic's child order from Linear's blocking relations, the refusals that keep an
epic small and well-formed, and the completion check over the pushed branch's Ticket trailers."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from helpers import KORG_CONFIG_STUB, TEAM, run, stub_dir

PARENT = f"{TEAM}-10"
CURL_STUB = (
    "#!/usr/bin/env bash\n"
    'printf \'%s\\n\' "$@" > "$STUB_DIR/curl_argv"\n'
    '[ "${STUB_CURL_EXIT:-0}" -eq 0 ] || exit "${STUB_CURL_EXIT}"\n'
    "printf '%s' \"$STUB_CURL_JSON\"\n"
)
CRITERIA = "## What to build\nx\n\n## Acceptance criteria\n- a test passes\n"


def child(
    n: int,
    *,
    blocked_by: list[tuple[int, str]] = (),
    state: str = "unstarted",
    labels: list[str] = (),
    description: str = CRITERIA,
) -> dict:
    return {
        "identifier": f"{TEAM}-{n}",
        "number": n,
        "description": description,
        "state": {"type": state},
        "labels": {"nodes": [{"name": name} for name in labels]},
        "inverseRelations": {
            "nodes": [
                {"type": "blocks", "issue": {"identifier": f"{TEAM}-{b}", "state": {"type": s}}}
                for b, s in blocked_by
            ]
            + [{"type": "related", "issue": {"identifier": f"{TEAM}-99", "state": {"type": "backlog"}}}]
        },
    }


def linear(children: list[dict]) -> str:
    return json.dumps({"data": {"issue": {"children": {"nodes": children}}}})


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=os.environ, check=True, capture_output=True, text=True
    ).stdout


def _run(tmp_path: Path, mode: str, children: list[dict], *, cwd: Path | None = None, curl_exit: int = 0):
    stubs = stub_dir(tmp_path, {"curl": CURL_STUB, "korg-config": KORG_CONFIG_STUB})
    env = {"LINEAR_API_KEY": "k", "STUB_CURL_JSON": linear(children), "STUB_CURL_EXIT": str(curl_exit)}
    return run("agent-epic", [mode, PARENT], stubs, env, cwd=cwd)


CHAIN = [child(12, blocked_by=[(11, "unstarted")]), child(11), child(13, blocked_by=[(12, "unstarted")])]


class TestOrder:
    def test_blockers_come_first(self, tmp_path: Path) -> None:
        result = _run(tmp_path, "order", CHAIN)
        assert result.returncode == 0, result.stderr
        assert result.stdout.split() == [f"{TEAM}-11", f"{TEAM}-12", f"{TEAM}-13"]

    def test_queries_the_parents_children(self, tmp_path: Path) -> None:
        _run(tmp_path, "order", CHAIN)
        argv = (tmp_path / "stubs" / "curl_argv").read_text().splitlines()
        body = next(json.loads(a) for a in argv if a.startswith("{"))
        assert body["variables"] == {"id": PARENT}

    def test_unrelated_children_go_in_ticket_order(self, tmp_path: Path) -> None:
        result = _run(tmp_path, "order", [child(14), child(12), child(13, blocked_by=[(14, "unstarted")])])
        assert result.stdout.split() == [f"{TEAM}-12", f"{TEAM}-14", f"{TEAM}-13"]

    def test_closed_children_are_left_out_and_their_blocks_count_as_resolved(self, tmp_path: Path) -> None:
        children = [
            child(11, state="completed"),
            child(12, blocked_by=[(11, "completed")]),
            child(13, state="canceled"),
            child(14, state="duplicate"),
        ]
        result = _run(tmp_path, "order", children)
        assert result.returncode == 0, result.stderr
        assert result.stdout.split() == [f"{TEAM}-12"]

    def test_a_completed_outside_blocker_is_resolved(self, tmp_path: Path) -> None:
        result = _run(tmp_path, "order", [child(11, blocked_by=[(5, "completed")])])
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        ("children", "reason"),
        [
            pytest.param([child(n) for n in range(11, 16)], "at most 4", id="too-many-children"),
            pytest.param([child(11, description="## What to build\nx\n")], "no Acceptance criteria", id="no-criteria"),
            pytest.param([child(11, labels=["agent-ready"])], "only the parent carries agent-ready", id="queued-child"),
            pytest.param([child(11, labels=["Spike"])], "is a spike", id="spike-child"),
            pytest.param([child(11, labels=["model:fable"])], "never runs unattended", id="fable-child"),
            pytest.param([child(11, blocked_by=[(5, "started")])], "blocked by ABC-5, which is outside", id="open-outside-blocker"),
            pytest.param([child(11, blocked_by=[(5, "canceled")])], "blocked by ABC-5, which is outside", id="canceled-outside-blocker"),
            pytest.param(
                [child(11, blocked_by=[(12, "unstarted")]), child(12, blocked_by=[(11, "unstarted")])],
                "cycle among ABC-11, ABC-12",
                id="cycle",
            ),
        ],
    )
    def test_refusals(self, tmp_path: Path, children: list[dict], reason: str) -> None:
        result = _run(tmp_path, "order", children)
        assert result.returncode == 1
        assert result.stdout == ""
        assert reason in result.stderr

    def test_done_when_counts_as_criteria(self, tmp_path: Path) -> None:
        result = _run(tmp_path, "order", [child(11, description="**Done when**\n- x\n")])
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        "children",
        [[], [child(11, state="completed"), child(12, state="canceled"), child(13, state="duplicate")]],
        ids=["no-children", "all-closed"],
    )
    def test_a_ticket_without_open_children_is_not_an_epic(self, tmp_path: Path, children: list[dict]) -> None:
        result = _run(tmp_path, "order", children)
        assert result.returncode == 3
        assert result.stdout == ""

    def test_a_linear_failure_is_a_read_error_not_a_refusal(self, tmp_path: Path) -> None:
        assert _run(tmp_path, "order", CHAIN, curl_exit=22).returncode == 2

    def test_a_child_linear_returns_malformed_is_a_read_error(self, tmp_path: Path) -> None:
        malformed = {**child(11), "labels": None}
        result = _run(tmp_path, "order", [malformed])
        assert result.returncode == 2
        assert result.stdout == ""


class TestCheck:
    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        origin = tmp_path / "origin.git"
        _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        repo = tmp_path / "repo"
        _git(tmp_path, "clone", "-q", str(origin), str(repo))
        self._commit(repo, "base")
        _git(repo, "push", "-q", "origin", "main")
        _git(repo, "checkout", "-q", "-b", f"agent/{PARENT}")
        return repo

    @staticmethod
    def _commit(repo: Path, subject: str, *tickets: str, change: bool = False) -> None:
        if change:
            with (repo / "work.txt").open("a") as f:
                f.write(subject + "\n")
            _git(repo, "add", "work.txt")
        message = subject + ("\n\n" + "\n".join(f"Ticket: {t}" for t in tickets) if tickets else "")
        _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", message)

    def _check(self, tmp_path: Path, repo: Path):
        _git(repo, "push", "-q", "-f", "origin", f"agent/{PARENT}")
        return _run(tmp_path, "check", CHAIN, cwd=repo)

    def test_every_child_committed_in_order_is_complete(self, tmp_path: Path, repo: Path) -> None:
        for n in (11, 12, 13):
            self._commit(repo, f"{TEAM}-{n}: thing", f"{TEAM}-{n}")
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [f"{TEAM}-11 done", f"{TEAM}-12 done", f"{TEAM}-13 done"]

    def test_a_missing_child_is_incomplete(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "two", f"{TEAM}-12")
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert result.stdout.splitlines()[-1] == f"{TEAM}-13 todo"

    def test_only_reads_what_was_pushed(self, tmp_path: Path, repo: Path) -> None:
        """The PR holds the pushed branch, so an unpushed local commit is not done."""
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "two", f"{TEAM}-12")
        _git(repo, "push", "-q", "origin", f"agent/{PARENT}")
        self._commit(repo, "three", f"{TEAM}-13")
        result = _run(tmp_path, "check", CHAIN, cwd=repo)
        assert result.returncode == 1
        assert f"{TEAM}-13 todo" in result.stdout

    def test_a_bailed_child_stays_todo(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "WIP — bailed: stuck on the schema", change=True)
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert f"{TEAM}-12 todo" in result.stdout

    def test_ungated_wip_work_after_the_last_child_fails(self, tmp_path: Path, repo: Path) -> None:
        for n in (11, 12, 13):
            self._commit(repo, "x", f"{TEAM}-{n}")
        self._commit(repo, "WIP — bailed: half a fix", change=True)
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert result.stdout.splitlines() == [f"{TEAM}-11 done", f"{TEAM}-12 done", f"{TEAM}-13 done"]
        assert "changed files and no gated child commit follows it" in result.stderr

    def test_a_merge_after_ungated_wip_work_is_not_a_gated_commit(self, tmp_path: Path, repo: Path) -> None:
        """A resume merges the default branch in first; that merge must not clear the WIP work."""
        for n in (11, 12, 13):
            self._commit(repo, "x", f"{TEAM}-{n}")
        self._commit(repo, "WIP — bailed: half a fix", change=True)
        _git(repo, "push", "-q", "origin", f"agent/{PARENT}")
        _git(repo, "checkout", "-q", "main")
        self._commit(repo, "main moved")
        _git(repo, "push", "-q", "origin", "main")
        _git(repo, "checkout", "-q", f"agent/{PARENT}")
        _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "merge", "-q", "--no-edit", "main")
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert "changed files and no gated child commit follows it" in result.stderr

    def test_a_wip_line_in_a_child_commit_body_is_not_a_wip_commit(self, tmp_path: Path, repo: Path) -> None:
        for n in (11, 12):
            self._commit(repo, "x", f"{TEAM}-{n}")
        self._commit(repo, f"three\n\nWIP — bailed: an earlier attempt, now finished", f"{TEAM}-13", change=True)
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr

    def test_an_empty_bail_after_every_child_does_not_block_a_resume(self, tmp_path: Path, repo: Path) -> None:
        """A bail at parent acceptance has a clean tree; with every child done, the resumed run
        commits nothing new, so this empty WIP commit stays the tip and must not block the PR."""
        for n in (11, 12, 13):
            self._commit(repo, "x", f"{TEAM}-{n}")
        self._commit(repo, "WIP — bailed: parent acceptance gap")
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr

    def test_a_resumed_epic_is_complete_once_the_bailed_child_is_rebuilt(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "WIP — bailed: stuck", change=True)
        self._commit(repo, "two", f"{TEAM}-12")
        self._commit(repo, "three", f"{TEAM}-13")
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr

    def test_a_wip_commit_never_counts_a_child_as_done(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "WIP — bailed: stuck", f"{TEAM}-12")
        self._commit(repo, "three", f"{TEAM}-13")
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert f"{TEAM}-12 todo" in result.stdout

    def test_a_child_before_its_blocker_fails(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "two", f"{TEAM}-12")
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "three", f"{TEAM}-13")
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert f"{TEAM}-12 is committed before its blocker {TEAM}-11" in result.stderr

    def test_a_trailer_for_a_ticket_outside_the_epic_fails(self, tmp_path: Path, repo: Path) -> None:
        for n in (11, 12, 13):
            self._commit(repo, "x", f"{TEAM}-{n}")
        self._commit(repo, "stray", f"{TEAM}-50")
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert f"names {TEAM}-50" in result.stderr

    def test_a_resume_that_merged_main_in_is_complete(self, tmp_path: Path, repo: Path) -> None:
        """Step 2's resume merges the default branch into the bailed branch; the merge commit and
        main's own commits carry no trailer and must not disturb the check."""
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "WIP — bailed: stuck")
        _git(repo, "push", "-q", "origin", f"agent/{PARENT}")
        _git(repo, "checkout", "-q", "main")
        self._commit(repo, "someone else's change on main")
        _git(repo, "push", "-q", "origin", "main")
        _git(repo, "checkout", "-q", f"agent/{PARENT}")
        _git(repo, "-c", "user.email=a@b", "-c", "user.name=a", "merge", "-q", "--no-edit", "main")
        self._commit(repo, "two", f"{TEAM}-12")
        self._commit(repo, "three", f"{TEAM}-13")
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr

    def test_a_child_over_two_commits_counts_from_its_first(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "one", f"{TEAM}-11")
        self._commit(repo, "two", f"{TEAM}-12")
        self._commit(repo, "one again", f"{TEAM}-11")
        self._commit(repo, "three", f"{TEAM}-13")
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr

    def test_one_commit_may_carry_two_children(self, tmp_path: Path, repo: Path) -> None:
        self._commit(repo, "one and two", f"{TEAM}-11", f"{TEAM}-12")
        self._commit(repo, "three", f"{TEAM}-13")
        result = self._check(tmp_path, repo)
        assert result.returncode == 0, result.stderr

    def test_a_ticket_line_outside_the_trailer_block_does_not_count(self, tmp_path: Path, repo: Path) -> None:
        """/korg:commit appends Co-Authored-By; a Ticket line left in an earlier paragraph is prose,
        not a trailer, so the child must read as todo."""
        for n in (11, 12):
            self._commit(repo, "x", f"{TEAM}-{n}")
        self._commit(repo, f"three\n\nTicket: {TEAM}-13\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert f"{TEAM}-13 todo" in result.stdout

    def test_an_empty_branch_is_all_todo(self, tmp_path: Path, repo: Path) -> None:
        result = self._check(tmp_path, repo)
        assert result.returncode == 1
        assert result.stdout.split()[1::2] == ["todo", "todo", "todo"]

    def test_an_unpushed_branch_is_a_read_error(self, tmp_path: Path, repo: Path) -> None:
        assert _run(tmp_path, "check", CHAIN, cwd=repo).returncode == 2
