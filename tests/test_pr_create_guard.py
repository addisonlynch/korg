"""korg-pr-create-guard: blocks PR creation outside /korg:open-pr, and nothing else."""

import json
import os
import subprocess
import time

import pytest

from helpers import BIN

GUARD = BIN / "korg-pr-create-guard"


@pytest.fixture
def repo(tmp_path):
    # A branch per test, so its sentinel is unique and no real one is touched.
    branch = f"agent/T-{tmp_path.name}"
    subprocess.run(["git", "init", "-q", "-b", branch, str(tmp_path)], check=True)
    sentinel = "/tmp/open-pr-active-" + branch.replace("/", "_")
    yield tmp_path, sentinel
    if os.path.exists(sentinel):
        os.remove(sentinel)


def guard(repo, command, env=None):
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run([str(GUARD)], input=payload, cwd=repo[0], capture_output=True, text=True, env=env)


BLOCKED = [
    "gh pr create --title x --body y",
    "gh pr new --fill",
    "gh pr -R o/r create --fill",
    "cd sub && gh pr create",
    "git push -u origin HEAD; gh pr create --fill",
    "git push -u origin HEAD\ngh pr create --fill",
    "GH_TOKEN=abc gh pr create",
    "command gh pr create",
    "timeout 60 gh pr create --fill",
    "/opt/homebrew/bin/gh pr create",
    "if true; then gh pr create; fi",
    "echo $(gh pr create --fill)",
    'url="$(gh pr create --fill)"',
    "echo `gh pr create --fill`",
    "git log --grep=a#b; gh pr create",
    "echo don't && cd x&&gh pr create",
    "gh api --method POST repos/o/r/pulls -f title=x",
    "gh api repos/o/r/pulls -X POST -f title=x",
    "gh api repos/o/r/pulls -X post",
    "gh api repos/o/r/pulls -XPOST",
    "gh api repos/o/r/pulls -X=POST",
    "gh api repos/o/r/pulls --method=POST",
    "gh api repos/o/r/pulls -X \"$METHOD\"",
    "gh api /repos/o/r/pulls -f title=x",
    "gh api repos/{owner}/{repo}/pulls -f title=x",
    "gh api https://api.github.com/repos/o/r/pulls -f title=x",
    "gh api 'repos/o/r/pulls?x=1' -f title=x",
    "gh api repos/o/r/pulls -Ftitle=x",
    "gh api repos/o/r/pulls --raw-field=title=x",
    "gh api repos/o/r/pulls --input body.json",
    "gh api graphql -f query='mutation{createPullRequest(input:{}){pullRequest{url}}}'",
]

ALLOWED = [
    "gh pr view 5",
    "gh pr list --state open",
    "gh pr -R o/r view 5",
    "gh api repos/o/r/pulls",
    "gh api repos/o/r/pulls -X GET -f state=open",
    "gh api repos/o/r/pulls/5/comments -f body=hi",
    "gh api --method POST repos/o/r/issues/5/labels -f 'labels[]=needs-review'",
    "gh api graphql -f query='{viewer{login}}'",
    "grep -e 'gh pr create' notes.md",
    "grep -e 'a\\|gh pr create' notes.md",
    'echo "run gh pr create later"',
    "# gh pr create",
    "ls -la",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocks_pr_creation_without_a_sentinel(repo, command):
    result = guard(repo, command)
    assert result.returncode == 2
    assert "/korg:open-pr" in result.stderr


@pytest.mark.parametrize("command", ALLOWED)
def test_lets_everything_else_through(repo, command):
    assert guard(repo, command).returncode == 0


def test_a_fresh_sentinel_for_this_branch_allows_creation(repo):
    open(repo[1], "w").close()
    assert guard(repo, "gh pr create --fill").returncode == 0


def test_a_stale_sentinel_is_ignored(repo):
    open(repo[1], "w").close()
    old = time.time() - 20 * 60
    os.utime(repo[1], (old, old))
    assert guard(repo, "gh pr create --fill").returncode == 2


def test_another_branchs_sentinel_does_not_count(repo, tmp_path_factory):
    other = "/tmp/open-pr-active-agent_T-other-" + tmp_path_factory.mktemp("o").name
    open(other, "w").close()
    try:
        assert guard(repo, "gh pr create --fill").returncode == 2
    finally:
        os.remove(other)


@pytest.fixture
def broken_python(tmp_path):
    stub = tmp_path / "stubbin"
    stub.mkdir()
    py = stub / "python3"
    py.write_text("#!/bin/sh\nexit 1\n")
    py.chmod(0o755)
    return {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"}


def test_a_failed_parser_still_blocks_pr_creation(repo, broken_python):
    result = guard(repo, "gh pr create --fill", env=broken_python)
    assert result.returncode == 2
    assert "parser failed" in result.stderr


def test_a_failed_parser_lets_unrelated_commands_through(repo, broken_python):
    assert guard(repo, "ls -la", env=broken_python).returncode == 0
