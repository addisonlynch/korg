"""The implement side of the agent loop: ticket selection and the claim write (agent-dispatch), the
implement job's setup (agent-pr-baseline, resolve-implement-model) and its classification
(agent-run-outcome)."""

import json
from pathlib import Path

import pytest
from helpers import KORG_CONFIG_STUB, NO_CONFIG_STUB, TEAM, outputs, run, stub_dir

# Records argv, then replays STUB_GH_JSON through the caller's own --jq filter (raw output, like
# gh) so the extraction is tested rather than bypassed.
_GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$STUB_DIR/gh_argv"
[ "${STUB_GH_EXIT:-0}" -eq 0 ] || exit "${STUB_GH_EXIT}"
jqf=""
prev=""
for a in "$@"; do
  [ "$prev" = "--jq" ] && jqf="$a"
  prev="$a"
done
printf '%s' "${STUB_GH_JSON:-[]}" | jq -r "$jqf"
"""


class TestAgentRunOutcome:
    def _run(
        self,
        tmp_path: Path,
        *,
        pr_number: str = "",
        pr_before: str = "",
        gh_exit: int = 0,
        linear_state: str | None = None,
        linear_exit: int = 0,
    ) -> tuple[Path, object, dict[str, str]]:
        state_json = json.dumps({"state": {"name": linear_state}} if linear_state else {})
        stubs = stub_dir(
            tmp_path,
            {
                "gh": _GH_STUB,
                "linear-issue": (
                    "#!/usr/bin/env bash\n"
                    'printf \'%s\\n\' "$@" > "$STUB_DIR/linear_argv"\n'
                    f"[ {linear_exit} -eq 0 ] || exit {linear_exit}\n"
                    f"printf '%s' '{state_json}'\n"
                ),
            },
        )
        out = tmp_path / "github_output"
        env = {
            "STUB_GH_JSON": json.dumps([{"number": int(pr_number)}]) if pr_number else "[]",
            "STUB_GH_EXIT": str(gh_exit),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
            "PR_BEFORE": pr_before,
        }
        result = run("agent-run-outcome", [f"{TEAM}-42"], stubs, env)
        return stubs, result, outputs(out)

    def test_new_pr_is_opened_and_emits_outputs(self, tmp_path: Path) -> None:
        stubs, result, outs = self._run(tmp_path, pr_number="123")
        assert result.returncode == 0, result.stdout
        assert outs == {"outcome": "opened", "pr_number": "123"}
        # --state all would read an abandoned closed PR as this run's work, and a wrong --repo or
        # --head would classify some other branch's PR.
        argv = (stubs / "gh_argv").read_text().splitlines()
        for expected in ("--repo", "owner/repo", "--head", f"agent/{TEAM}-42", "--state", "open"):
            assert expected in argv

    def test_new_pr_after_the_baseline_was_closed_is_opened(self, tmp_path: Path) -> None:
        """The baseline PR has closed since and this run opened another: a legitimate open."""
        _, result, outs = self._run(tmp_path, pr_number="123", pr_before="99")
        assert result.returncode == 0, result.stdout
        assert outs == {"outcome": "opened", "pr_number": "123"}

    def test_unchanged_pr_is_a_green_dedup_noop(self, tmp_path: Path) -> None:
        """The PR was already there, so this run opened nothing. The `Done` state proves the PR
        checks come first: a stale PR is a dedup, never a spike."""
        _, result, outs = self._run(tmp_path, pr_number="99", pr_before="99", linear_state="Done")
        assert result.returncode == 0, result.stdout
        assert outs == {"outcome": "dedup", "pr_number": ""}

    def test_baseline_pr_closed_mid_run_is_still_a_dedup_noop(self, tmp_path: Path) -> None:
        """No PR now, but one existed before: this run still opened nothing."""
        _, result, outs = self._run(tmp_path, pr_before="99")
        assert result.returncode == 0, result.stdout
        assert outs == {"outcome": "dedup", "pr_number": ""}

    def test_gh_failure_fails_rather_than_reading_as_no_pr(self, tmp_path: Path) -> None:
        """A gh error is not 'no PR': a revoked token must not classify as a stopped run."""
        _, result, outs = self._run(tmp_path, gh_exit=1)
        assert result.returncode == 1
        assert "gh pr list failed" in result.stdout
        assert outs == {}

    @pytest.mark.parametrize(
        ("state", "outcome"),
        [("Done", "spike"), ("Needs Human", "bail")],
        ids=["done-is-spike", "needs-human-is-bail"],
    )
    def test_no_pr_with_a_terminal_state_is_a_green_no_pr_exit(self, tmp_path: Path, state: str, outcome: str) -> None:
        _, result, outs = self._run(tmp_path, linear_state=state)
        assert result.returncode == 0, result.stdout
        assert outs == {"outcome": outcome, "pr_number": ""}

    def test_no_pr_without_a_terminal_state_fails(self, tmp_path: Path) -> None:
        """The inverse: a run that stopped early reaches no exit and must go red."""
        stubs, result, outs = self._run(tmp_path, linear_state="In Progress")
        assert result.returncode == 1
        assert "stopped early" in result.stdout
        assert "In Progress" in result.stdout
        assert outs == {}
        # Reading some other ticket's state would classify this run off the wrong evidence.
        assert (stubs / "linear_argv").read_text().splitlines() == [f"{TEAM}-42"]

    def test_no_pr_and_an_unreachable_linear_fails_naming_linear(self, tmp_path: Path) -> None:
        """An unreachable Linear is not a ticket that stopped early, and the error says which."""
        _, result, outs = self._run(tmp_path, linear_exit=1)
        assert result.returncode == 1
        assert "could not read" in result.stdout
        assert "stopped early" not in result.stdout
        assert outs == {}

    def test_no_pr_and_a_state_with_no_name_fails(self, tmp_path: Path) -> None:
        """A shape-changed Linear response is not a ticket that reached a terminal state."""
        _, result, outs = self._run(tmp_path)
        assert result.returncode == 1
        assert "'unknown'" in result.stdout
        assert outs == {}


# `run list` replays STUB_RUNS_JSON (the script pipes it through its own jq, so the capacity
# extraction is exercised); `workflow run` only records. Any other subcommand is a test bug and
# exits 99 rather than passing silently.
_DISPATCH_GH_STUB = """#!/usr/bin/env bash
case "$1 $2" in
  "run list")
    printf '%s\\n' "$@" > "$STUB_DIR/gh_run_argv"
    [ "${STUB_RUNLIST_EXIT:-0}" -eq 0 ] || exit "${STUB_RUNLIST_EXIT}"
    printf '%s' "${STUB_RUNS_JSON:-[]}"
    ;;
  "workflow run")
    printf '%s\\n' "$@" > "$STUB_DIR/gh_dispatch_argv"
    [ "${STUB_DISPATCH_EXIT:-0}" -eq 0 ] || exit "${STUB_DISPATCH_EXIT}"
    ;;
  *) echo "unexpected gh invocation: $*" >&2; exit 99 ;;
esac
"""

# The two Linear GraphQL calls, told apart by the request body like the real endpoint: replays
# issues_response.json for the issues query and strip_response.json for the issueRemoveLabel
# mutation. STUB_QUERY_EXIT mimics --fail on the query (an invalid key answers HTTP 401 there);
# the strip carries no --fail, so its failure mode is a GraphQL error body.
_DISPATCH_CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$STUB_DIR/curl_argv"
body=""
prev=""
for a in "$@"; do
  [ "$prev" = "-d" ] && body="$a"
  prev="$a"
done
case "$body" in
  *issueRemoveLabel*)
    printf '%s' "$body" > "$STUB_DIR/strip_body.json"
    cat "$STUB_DIR/strip_response.json"
    ;;
  *)
    printf '%s' "$body" > "$STUB_DIR/query_body.json"
    [ "${STUB_QUERY_EXIT:-0}" -eq 0 ] || exit "${STUB_QUERY_EXIT}"
    cat "$STUB_DIR/issues_response.json"
    ;;
esac
"""

# Dispatch addresses everything Linear-side by name, so the tests use the exact names the filter
# sends. Label ids exist only per issue, where the strip reads them off the fetched node.
READY = "agent-ready"
OPUS = "model:opus"
HAIKU = "model:haiku"
SONNET = "model:sonnet"
FABLE = "model:fable"


# Linear priority encoding: 0 none, 1 urgent, 2 high, 3 normal, 4 low.
def _issue(seq: int, *, labels=(READY,), priority=0, created="2026-01-01T00:00:00Z") -> dict:
    return {
        "id": f"uuid-{seq}",
        "identifier": f"{TEAM}-{seq}",
        "priority": priority,
        "createdAt": created,
        "labels": {"nodes": [{"id": f"lbl-{label}", "name": label} for label in labels]},
    }


# Every variable the script requires, at its passing value, so a test that drops one field
# cannot silently drop the others.
_DISPATCH_ENV = {"LINEAR_API_KEY": "test-token", "GH_TOKEN": "test-gh-token", "GITHUB_REPOSITORY": "owner/repo"}


class TestAgentDispatch:
    @pytest.fixture()
    def stubs(self, tmp_path: Path) -> Path:
        return stub_dir(
            tmp_path, {"curl": _DISPATCH_CURL_STUB, "gh": _DISPATCH_GH_STUB, "korg-config": KORG_CONFIG_STUB}
        )

    def _run(
        self,
        stubs: Path,
        issues: list[dict] | None,
        *,
        inflight: list[str] | None = None,
        inflight_status: str = "in_progress",
        max_concurrency: str = "1",
        model_override: str = "",
        runlist_exit: int = 0,
        dispatch_exit: int = 0,
        query_exit: int = 0,
        issues_response: dict | None = None,
        strip_response: dict | None = None,
    ) -> object:
        # issues=None with issues_response set replays a raw (e.g. error-shaped) body.
        if issues_response is None:
            issues_response = {"data": {"issues": {"nodes": issues or []}}}
        (stubs / "issues_response.json").write_text(json.dumps(issues_response))
        if strip_response is None:
            strip_response = {"data": {"issueRemoveLabel": {"success": True}}}
        (stubs / "strip_response.json").write_text(json.dumps(strip_response))
        runs = [{"displayTitle": f"implement {t}", "status": inflight_status} for t in (inflight or [])]
        env = _DISPATCH_ENV | {
            "STUB_RUNS_JSON": json.dumps(runs),
            "STUB_RUNLIST_EXIT": str(runlist_exit),
            "STUB_DISPATCH_EXIT": str(dispatch_exit),
            "STUB_QUERY_EXIT": str(query_exit),
            "MAX": max_concurrency,
            "MODEL_OVERRIDE": model_override,
        }
        return run("agent-dispatch", [], stubs, env)

    @staticmethod
    def _dispatched(stubs: Path) -> list[str]:
        path = stubs / "gh_dispatch_argv"
        return path.read_text().splitlines() if path.exists() else []

    @staticmethod
    def _stripped(stubs: Path) -> dict | None:
        """The issueRemoveLabel mutation's variables, or None if no strip was attempted."""
        path = stubs / "strip_body.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())["variables"]

    def test_dispatches_the_single_ready_ticket_and_consumes_the_claim(self, stubs: Path) -> None:
        result = self._run(stubs, [_issue(42)])
        assert result.returncode == 0, result.stderr
        argv = self._dispatched(stubs)
        assert "agent-implement.yml" in argv
        assert f"ticket={TEAM}-42" in argv
        assert "model=opusplan" in argv
        # A wrong --repo would dispatch into another repository entirely.
        assert "--repo" in argv and "owner/repo" in argv
        # The claim is consumed against the ticket's own issue id, with the label id read off the
        # fetched node rather than pinned anywhere.
        assert self._stripped(stubs) == {"id": "uuid-42", "label": f"lbl-{READY}"}

    def test_sends_the_server_side_filter(self, stubs: Path) -> None:
        """A wrong or dropped clause would dispatch untagged tickets, other teams' tickets, or
        tickets already past implement start."""
        result = self._run(stubs, [_issue(42)])
        assert result.returncode == 0, result.stderr
        body = json.loads((stubs / "query_body.json").read_text())
        assert body["variables"]["f"] == {
            "team": {"key": {"eq": TEAM}},
            "labels": {"name": {"eq": "agent-ready"}},
            "state": {"name": {"in": ["Backlog", "Todo"]}},
        }
        # --fail turns a 401 into a red tick instead of an empty queue, and the auth header scopes
        # the query to the workspace.
        curl_argv = (stubs / "curl_argv").read_text().splitlines()
        assert "https://api.linear.app/graphql" in curl_argv
        assert "--fail" in curl_argv
        assert "Authorization: test-token" in curl_argv

    def test_reads_the_implement_workflow_runs_for_capacity(self, stubs: Path) -> None:
        """Counting some other workflow's runs would let dispatch run past MAX."""
        result = self._run(stubs, [_issue(42)])
        assert result.returncode == 0, result.stderr
        argv = (stubs / "gh_run_argv").read_text().splitlines()
        # `status` is pinned too: without it the real gh omits the field and every run reads as
        # non-completed.
        for expected in (
            "--repo",
            "owner/repo",
            "--workflow",
            "agent-implement.yml",
            "--json",
            "displayTitle,status",
        ):
            assert expected in argv

    @pytest.mark.parametrize(
        ("issues", "expected"),
        [
            pytest.param(
                [_issue(1, priority=4), _issue(2, priority=1), _issue(3, priority=2)],
                f"ticket={TEAM}-2",
                id="urgent-outranks-high-and-low",
            ),
            pytest.param(
                [_issue(1, priority=0), _issue(2, priority=3)],
                f"ticket={TEAM}-2",
                id="normal-outranks-none",
            ),
            pytest.param(
                [
                    _issue(1, priority=2, created="2026-02-01T00:00:00Z"),
                    _issue(2, priority=2, created="2026-01-01T00:00:00Z"),
                ],
                f"ticket={TEAM}-2",
                id="equal-priority-breaks-oldest-first",
            ),
        ],
    )
    def test_priority_order(self, stubs: Path, issues, expected: str) -> None:
        result = self._run(stubs, issues)
        assert result.returncode == 0, result.stderr
        assert expected in self._dispatched(stubs)

    def test_a_fable_ticket_is_never_selected(self, stubs: Path) -> None:
        """Fable runs only in an interactive shell, so a fable-labelled ticket is never
        dispatched however it got labelled agent-ready, even alone in the queue."""
        result = self._run(stubs, [_issue(7, labels=[READY, FABLE], priority=1)])
        assert result.returncode == 0, result.stderr
        assert "no dispatchable tickets" in result.stdout
        assert self._dispatched(stubs) == []
        assert self._stripped(stubs) is None

    def test_a_fable_ticket_is_skipped_in_favor_of_the_next_candidate(self, stubs: Path) -> None:
        """The inverse: excluding fable must not starve the rest of the queue."""
        result = self._run(stubs, [_issue(7, labels=[READY, FABLE], priority=1), _issue(8, priority=4)])
        assert result.returncode == 0, result.stderr
        assert f"ticket={TEAM}-8" in self._dispatched(stubs)

    def test_an_empty_queue_is_a_green_noop(self, stubs: Path) -> None:
        """A clean empty queue exits 0 with the explicit no-work line, distinguishable from the
        API failures below, which exit non-zero."""
        result = self._run(stubs, [])
        assert result.returncode == 0, result.stderr
        assert "no dispatchable tickets" in result.stdout
        assert self._dispatched(stubs) == []
        assert self._stripped(stubs) is None

    def test_an_invalid_api_key_fails_the_tick(self, stubs: Path) -> None:
        """Linear answers 401 and --fail turns that into a non-zero curl exit: a revoked or
        invalid key must red the tick, never parse as an empty queue."""
        result = self._run(stubs, [_issue(42)], query_exit=22)
        assert result.returncode != 0
        assert self._dispatched(stubs) == []
        assert self._stripped(stubs) is None

    def test_a_graphql_error_body_fails_the_tick(self, stubs: Path) -> None:
        """GraphQL can answer 200 with an errors array; null nodes must red the tick rather than
        read as no candidates."""
        result = self._run(stubs, None, issues_response={"errors": [{"message": "boom"}], "data": None})
        assert result.returncode != 0
        assert "query failed" in result.stdout
        assert self._dispatched(stubs) == []

    def test_at_capacity_dispatches_nothing(self, stubs: Path) -> None:
        result = self._run(stubs, [_issue(42)], inflight=[f"{TEAM}-9"], max_concurrency="1")
        assert result.returncode == 0, result.stderr
        assert "at capacity" in result.stdout
        assert self._dispatched(stubs) == []
        assert self._stripped(stubs) is None

    def test_below_capacity_skips_the_in_flight_ticket_and_takes_the_next(self, stubs: Path) -> None:
        result = self._run(
            stubs, [_issue(1, priority=1), _issue(2, priority=2)], inflight=[f"{TEAM}-1"], max_concurrency="2"
        )
        assert result.returncode == 0, result.stderr
        assert f"ticket={TEAM}-2" in self._dispatched(stubs)

    @pytest.mark.parametrize("max_concurrency", ["two", "1.5"])
    def test_a_non_integer_max_refuses_rather_than_dropping_the_capacity_gate(
        self, stubs: Path, max_concurrency: str
    ) -> None:
        result = self._run(stubs, [_issue(42)], inflight=[f"{TEAM}-9"], max_concurrency=max_concurrency)
        assert result.returncode == 1
        assert "MAX" in result.stdout
        assert self._dispatched(stubs) == []

    def test_completed_runs_do_not_count_against_capacity(self, stubs: Path) -> None:
        """The inverse of the in-flight skip: a finished run frees its slot."""
        result = self._run(stubs, [_issue(42)], inflight=[f"{TEAM}-42"], inflight_status="completed")
        assert result.returncode == 0, result.stderr
        assert f"ticket={TEAM}-42" in self._dispatched(stubs)

    def test_gh_run_list_failure_fails_the_tick(self, stubs: Path) -> None:
        """An undercount would dispatch past MAX, so a gh error must not read as 'no matches'."""
        result = self._run(stubs, [_issue(42)], runlist_exit=1)
        assert result.returncode == 1
        assert "gh run list failed" in result.stdout
        assert self._dispatched(stubs) == []

    @pytest.mark.parametrize(
        ("labels", "model"),
        [
            pytest.param([READY, OPUS], "opusplan", id="opus-plans-then-executes"),
            pytest.param([READY, HAIKU], "haiku", id="haiku"),
            pytest.param([READY, SONNET], "sonnet", id="sonnet"),
            pytest.param([READY], "opusplan", id="unlabelled-defaults-to-opusplan"),
        ],
    )
    def test_model_routing_from_the_ticket_label(self, stubs: Path, labels, model: str) -> None:
        result = self._run(stubs, [_issue(42, labels=labels)])
        assert result.returncode == 0, result.stderr
        assert f"model={model}" in self._dispatched(stubs)

    def test_model_override_wins_over_the_ticket_label(self, stubs: Path) -> None:
        result = self._run(stubs, [_issue(42, labels=[READY, OPUS])], model_override="haiku")
        assert result.returncode == 0, result.stderr
        assert "model=haiku" in self._dispatched(stubs)

    def test_a_failed_dispatch_does_not_consume_the_claim(self, stubs: Path) -> None:
        """Stripping first would silently eat the ticket, which is why the strip runs last."""
        result = self._run(stubs, [_issue(42)], dispatch_exit=1)
        assert result.returncode != 0
        assert self._stripped(stubs) is None

    def test_a_failed_strip_fails_the_tick(self, stubs: Path) -> None:
        """A surviving agent-ready label re-dispatches the ticket forever, so it must go red."""
        result = self._run(
            stubs, [_issue(42)], strip_response={"errors": [{"message": "something broke"}], "data": None}
        )
        assert result.returncode != 0
        assert "failed to remove agent-ready" in result.stdout
        # The tick reds *after* the work was handed off, not on some earlier failure.
        assert f"ticket={TEAM}-42" in self._dispatched(stubs)
        assert self._stripped(stubs) == {"id": "uuid-42", "label": f"lbl-{READY}"}

    def test_a_strip_of_an_already_absent_label_is_an_idempotent_success(self, stubs: Path) -> None:
        """Linear rejects removing a label that is not on the issue. That is the raced or repeated
        strip: the claim is already consumed, so the tick stays green rather than red-looping."""
        result = self._run(
            stubs, [_issue(42)], strip_response={"errors": [{"message": "Label not on issue"}], "data": None}
        )
        assert result.returncode == 0, result.stderr
        assert "already consumed" in result.stdout
        assert f"ticket={TEAM}-42" in self._dispatched(stubs)

    def test_a_strip_reported_unsuccessful_fails_the_tick(self, stubs: Path) -> None:
        """success:false with no errors array is still a failed write, not a success."""
        result = self._run(stubs, [_issue(42)], strip_response={"data": {"issueRemoveLabel": {"success": False}}})
        assert result.returncode != 0
        assert "failed to remove agent-ready" in result.stdout

    @pytest.mark.parametrize(
        "missing",
        ["LINEAR_API_KEY", "GH_TOKEN", "GITHUB_REPOSITORY"],
        ids=lambda v: v.lower().replace("_", "-"),
    )
    def test_missing_required_env_refuses(self, stubs: Path, missing: str) -> None:
        env = {k: v for k, v in _DISPATCH_ENV.items() if k != missing}
        result = run("agent-dispatch", [], stubs, env)
        assert result.returncode != 0
        assert missing in result.stderr
        assert self._dispatched(stubs) == []

    def test_an_unset_team_refuses(self, tmp_path: Path) -> None:
        """Without a team key the filter and the in-flight match have nothing to key on."""
        stubs = stub_dir(
            tmp_path, {"curl": _DISPATCH_CURL_STUB, "gh": _DISPATCH_GH_STUB, "korg-config": NO_CONFIG_STUB}
        )
        result = run("agent-dispatch", [], stubs, _DISPATCH_ENV)
        assert result.returncode != 0
        assert "linear.team" in result.stdout
        assert not (stubs / "gh_dispatch_argv").exists()


# Records each `pr list` argv and replays the response matching the query flag, so the --head
# lookup and the --search fallback are told apart rather than conflated.
_BASELINE_GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$STUB_DIR/gh_argv"
[ "${STUB_GH_EXIT:-0}" -eq 0 ] || exit "${STUB_GH_EXIT}"
for a in "$@"; do
  case "$a" in
    --head) printf '%s' "${STUB_HEAD_PR:-}"; exit 0 ;;
    --search) printf '%s' "${STUB_SEARCH_PR:-}"; exit 0 ;;
  esac
done
echo "unexpected gh invocation: $*" >&2; exit 99
"""


class TestAgentPrBaseline:
    def _run(
        self,
        tmp_path: Path,
        ticket: str = f"{TEAM}-42",
        *,
        head_pr: str = "",
        search_pr: str = "",
        gh_exit: int = 0,
        korg_config: str = KORG_CONFIG_STUB,
    ) -> tuple[Path, object, dict[str, str]]:
        stubs = stub_dir(tmp_path, {"gh": _BASELINE_GH_STUB, "korg-config": korg_config})
        out = tmp_path / "github_output"
        env = {
            "STUB_HEAD_PR": head_pr,
            "STUB_SEARCH_PR": search_pr,
            "STUB_GH_EXIT": str(gh_exit),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
        }
        result = run("agent-pr-baseline", [ticket], stubs, env)
        return stubs, result, outputs(out)

    def test_a_pr_on_the_branch_is_the_baseline(self, tmp_path: Path) -> None:
        stubs, result, outs = self._run(tmp_path, head_pr="77")
        assert result.returncode == 0, result.stderr
        assert outs == {"number": "77"}
        assert f"agent/{TEAM}-42" in (stubs / "gh_argv").read_text().splitlines()

    def test_falls_back_to_the_cross_branch_search(self, tmp_path: Path) -> None:
        """A PR referencing the ticket from another branch bails the run just as hard."""
        stubs, result, outs = self._run(tmp_path, search_pr="88")
        assert result.returncode == 0, result.stderr
        assert outs == {"number": "88"}
        assert f"{TEAM}-42 in:title" in (stubs / "gh_argv").read_text().splitlines()

    def test_the_branch_hit_short_circuits_the_search(self, tmp_path: Path) -> None:
        """The inverse: a branch PR must not be overwritten by a different search result."""
        _, result, outs = self._run(tmp_path, head_pr="77", search_pr="88")
        assert result.returncode == 0, result.stderr
        assert outs == {"number": "77"}

    def test_no_pr_either_way_is_an_empty_baseline(self, tmp_path: Path) -> None:
        _, result, outs = self._run(tmp_path)
        assert result.returncode == 0, result.stderr
        assert outs == {"number": ""}

    def test_only_open_prs_count(self, tmp_path: Path) -> None:
        """--state all would read an abandoned closed PR as a live baseline."""
        stubs, result, _ = self._run(tmp_path, head_pr="77")
        assert result.returncode == 0, result.stderr
        argv = (stubs / "gh_argv").read_text().splitlines()
        # Adjacent, not merely both present: `--state all --json open` would satisfy a loose check.
        assert argv[argv.index("--state") : argv.index("--state") + 2] == ["--state", "open"]

    @pytest.mark.parametrize(
        "ticket",
        [
            pytest.param("42", id="bare-number"),
            pytest.param(f"{TEAM.lower()}-42", id="lowercase"),
            pytest.param(f"{TEAM}-", id="no-sequence-id"),
            pytest.param(f"{TEAM}-42x", id="trailing-junk"),
            pytest.param("XYZ-42", id="another-teams-prefix"),
        ],
    )
    def test_a_malformed_ticket_refuses(self, tmp_path: Path, ticket: str) -> None:
        """It would point the baseline and the later classification at different branches."""
        _, result, outs = self._run(tmp_path, ticket, head_pr="77")
        assert result.returncode == 1
        assert f"must be {TEAM}-N" in result.stdout + result.stderr
        assert outs == {}

    def test_an_unset_team_refuses(self, tmp_path: Path) -> None:
        _, result, outs = self._run(tmp_path, head_pr="77", korg_config=NO_CONFIG_STUB)
        assert result.returncode == 1
        assert "linear.team" in result.stdout
        assert outs == {}

    def test_gh_failure_fails_rather_than_reading_as_no_baseline(self, tmp_path: Path) -> None:
        """An empty baseline would let a pre-existing PR classify as this run's work."""
        _, result, outs = self._run(tmp_path, gh_exit=1)
        assert result.returncode == 1
        assert "cannot establish a PR baseline" in result.stderr
        assert outs == {}


class TestResolveImplementModel:
    def _run(
        self, tmp_path: Path, requested: str = "", *, family: str = "sonnet"
    ) -> tuple[Path, object, dict[str, str]]:
        stubs = stub_dir(
            tmp_path,
            {
                "resolve-ticket-model": (
                    f'#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$STUB_DIR/family_argv"\necho {family}\n'
                )
            },
        )
        out = tmp_path / "github_output"
        result = run("resolve-implement-model", [f"{TEAM}-42", requested], stubs, {"GITHUB_OUTPUT": str(out)})
        return stubs, result, outputs(out)

    @pytest.mark.parametrize(
        ("family", "expected"),
        [
            pytest.param("opus", "opusplan", id="opus-becomes-opusplan"),
            pytest.param("haiku", "haiku", id="haiku"),
            pytest.param("sonnet", "sonnet", id="sonnet"),
        ],
    )
    def test_falls_back_to_the_tickets_label(self, tmp_path: Path, family: str, expected: str) -> None:
        stubs, result, outs = self._run(tmp_path, family=family)
        assert result.returncode == 0, result.stderr
        assert outs == {"model": expected}
        assert (stubs / "family_argv").read_text().splitlines() == [f"{TEAM}-42"]

    def test_an_explicit_model_wins_over_the_tickets_label(self, tmp_path: Path) -> None:
        _, result, outs = self._run(tmp_path, "haiku", family="opus")
        assert result.returncode == 0, result.stderr
        assert outs == {"model": "haiku"}

    @pytest.mark.parametrize("requested", ["sonnet", "opus", "opusplan", "haiku"])
    def test_every_documented_alias_is_accepted(self, tmp_path: Path, requested: str) -> None:
        """The inverse of the guard below: the workflow input advertises these four."""
        _, result, outs = self._run(tmp_path, requested)
        assert result.returncode == 0, result.stderr
        assert outs == {"model": requested}

    @pytest.mark.parametrize(
        "requested",
        [
            pytest.param("sonnett", id="typo"),
            pytest.param("sonnet\nmodel=haiku", id="newline-injects-a-second-output"),
        ],
    )
    def test_an_unknown_model_refuses_before_writing_an_output(self, tmp_path: Path, requested: str) -> None:
        """It reaches $GITHUB_OUTPUT and then the action's claude_args, so a newline would inject
        a second step output and a typo would fail later at the action instead of here."""
        _, result, outs = self._run(tmp_path, requested)
        assert result.returncode != 0
        assert "model must be" in result.stderr
        assert outs == {}
