"""resolve-ticket-model and resolve-pr-model: the model each agent job runs, from the ticket's
model:* label, with the cross-model rule for review."""

import json
from pathlib import Path

import pytest
from helpers import KORG_CONFIG_STUB, TEAM, outputs, run, stub_dir

# Replays STUB_BODY as the response body; records each invocation's argv so the URL is asserted.
# STUB_CURL_EXIT drives the -sf failure path.
_PR_CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$STUB_DIR/curl_argv"
echo "---" >> "$STUB_DIR/curl_argv"
[ "${STUB_CURL_EXIT:-0}" -eq 0 ] || exit "${STUB_CURL_EXIT}"
printf '%s' "${STUB_BODY:-}"
"""


class TestResolveTicketModel:
    """The one script that owns ticket-id extraction + model resolution for its three callers."""

    def _run(
        self, tmp_path: Path, arg: str, *, labels: list[str] | None = None, linear_exit: int = 0
    ) -> tuple[Path, object]:
        payload = json.dumps({"labels": [{"name": n} for n in (labels or [])]})
        stubs = stub_dir(
            tmp_path,
            {
                "korg-config": KORG_CONFIG_STUB,
                "linear-issue": (
                    "#!/usr/bin/env bash\n"
                    'printf \'%s\\n\' "$@" > "$STUB_DIR/linear_argv"\n'
                    f"[ {linear_exit} -eq 0 ] || exit {linear_exit}\n"
                    f"printf '%s' '{payload}'\n"
                ),
            },
        )
        return stubs, run("resolve-ticket-model", [arg], stubs, {"LINEAR_API_KEY": "test-token"})

    @pytest.mark.parametrize(
        ("labels", "expected"),
        [
            pytest.param(["model:opus"], "opus", id="opus"),
            pytest.param(["model:haiku"], "haiku", id="haiku"),
            pytest.param(["model:sonnet"], "sonnet", id="sonnet"),
            pytest.param([], "opus", id="no-model-label-defaults-to-opus"),
            pytest.param(["model:fable"], "opus", id="fable-is-never-resolved"),
            pytest.param(["agent-loop", "model:sonnet"], "sonnet", id="sonnet-found-among-other-labels"),
            pytest.param(["agent-loop", "model:opus"], "opus", id="found-among-other-labels"),
            pytest.param(["model:sonnet", "model:opus"], "opus", id="opus-wins-over-sonnet"),
            pytest.param(["model:haiku", "model:opus"], "opus", id="opus-wins-over-haiku"),
        ],
    )
    def test_resolves_the_model_from_the_tickets_labels(self, tmp_path: Path, labels, expected: str) -> None:
        _, result = self._run(tmp_path, f"{TEAM}-42", labels=labels)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected

    @pytest.mark.parametrize(
        ("arg", "expected_seq"),
        [
            pytest.param(f"{TEAM}-42", f"{TEAM}-42", id="identifier"),
            pytest.param("42", "42", id="bare-sequence-id"),
            pytest.param(f"[{TEAM}-42] Fix the thing", f"{TEAM}-42", id="pr-title"),
            pytest.param(f"[{TEAM}-42] Supersede {TEAM}-99", f"{TEAM}-42", id="first-id-wins"),
        ],
    )
    def test_accepts_every_callers_argument_shape(self, tmp_path: Path, arg: str, expected_seq: str) -> None:
        """Implement passes an id; review and respond pass a PR title."""
        stubs, result = self._run(tmp_path, arg, labels=["model:opus"])
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "opus"
        assert (stubs / "linear_argv").read_text().splitlines() == [expected_seq]

    @pytest.mark.parametrize(
        "arg",
        [
            pytest.param("Bump the deps", id="unlinked-pr-title"),
            pytest.param("[XYZ-42] Fix", id="another-teams-ticket"),
            # respond and review build the title from a `curl | jq` that yields "" on any API
            # blip. Refusing here would kill the whole job over a transient read.
            pytest.param("", id="empty-title"),
        ],
    )
    def test_an_argument_with_no_ticket_defaults_without_calling_linear(self, tmp_path: Path, arg: str) -> None:
        """The inverse: no ticket in the argument must not fetch. Exit 2 tells the caller the opus
        it printed is a default, not a label."""
        stubs, result = self._run(tmp_path, arg, labels=["model:sonnet"])
        assert result.returncode == 2, result.stderr
        assert result.stdout.strip() == "opus"
        assert not (stubs / "linear_argv").exists()

    def test_an_unreachable_linear_defaults_to_opus(self, tmp_path: Path) -> None:
        """A wrong model is recoverable, a failed run is not."""
        _, result = self._run(tmp_path, f"{TEAM}-42", labels=["model:sonnet"], linear_exit=1)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "opus"


class TestResolvePrModel:
    """One script serves the model resolution for both the review and respond jobs: `review` mode
    never returns the author's model, `respond` mode always does (the fixer benefits from being
    the author's model; the judge must not be)."""

    def _run(
        self,
        tmp_path: Path,
        *,
        mode: str | None = "respond",
        title: str = f"[{TEAM}-42] Fix",
        family: str = "opus",
        family_exit: int = 0,
        curl_exit: int = 0,
    ) -> tuple[object, dict[str, str], list[str]]:
        stubs = stub_dir(
            tmp_path,
            {
                "resolve-ticket-model": (
                    f'#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$STUB_DIR/family_argv"\necho {family}\nexit {family_exit}\n'
                ),
                "curl": _PR_CURL_STUB,
            },
        )
        out = tmp_path / "github_output"
        env = {
            "STUB_BODY": json.dumps({"title": title}),
            "STUB_CURL_EXIT": str(curl_exit),
            "GH_TOKEN": "tok",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(out),
        }
        result = run("resolve-pr-model", ["77"] + ([mode] if mode is not None else []), stubs, env)
        argv_path = stubs / "family_argv"
        passed = argv_path.read_text().splitlines() if argv_path.exists() else []
        return result, outputs(out), passed

    def test_passes_the_pr_title_through_to_the_family_resolver(self, tmp_path: Path) -> None:
        result, outs, passed = self._run(tmp_path, title=f"[{TEAM}-42] Fix the thing")
        assert result.returncode == 0, result.stderr
        assert outs == {"model": "opus"}
        assert passed == [f"[{TEAM}-42] Fix the thing"]

    def test_reads_the_pr_endpoint_for_the_repo_it_was_given(self, tmp_path: Path) -> None:
        """A wrong URL would resolve some other repository's PR title."""
        result, _, _ = self._run(tmp_path)
        assert result.returncode == 0, result.stderr
        assert "https://api.github.com/repos/owner/repo/pulls/77" in (tmp_path / "stubs" / "curl_argv").read_text()

    @pytest.mark.parametrize(
        ("family", "expected"),
        [
            pytest.param("sonnet", "opus", id="sonnet-authored-gets-opus-reviewer"),
            pytest.param("opus", "sonnet", id="opus-authored-gets-sonnet-reviewer"),
            pytest.param("haiku", "sonnet", id="haiku-authored-gets-sonnet-reviewer"),
        ],
    )
    def test_review_mode_never_returns_the_authors_model(self, tmp_path: Path, family: str, expected: str) -> None:
        result, outs, _ = self._run(tmp_path, mode="review", family=family)
        assert result.returncode == 0, result.stderr
        assert outs == {"model": expected}
        assert outs["model"] != family

    @pytest.mark.parametrize("family", ["sonnet", "opus", "haiku"])
    def test_respond_mode_keeps_the_authors_model(self, tmp_path: Path, family: str) -> None:
        """The inverse of the review flip: author-model continuity is the respond contract."""
        result, outs, _ = self._run(tmp_path, mode="respond", family=family)
        assert result.returncode == 0, result.stderr
        assert outs == {"model": family}

    @pytest.mark.parametrize(
        "mode",
        [pytest.param(None, id="mode-missing"), pytest.param("reviews", id="mode-typo")],
    )
    def test_a_missing_or_unknown_mode_refuses_before_resolving(self, tmp_path: Path, mode: str | None) -> None:
        """Silently defaulting the mode could hand the review back to the author's model."""
        result, outs, passed = self._run(tmp_path, mode=mode)
        assert result.returncode != 0
        assert outs == {}
        assert passed == []

    @pytest.mark.parametrize(
        ("title", "curl_exit"),
        [
            pytest.param("", 0, id="empty-title"),
            pytest.param("null", 0, id="json-null-title"),
            pytest.param(f"[{TEAM}-42] Fix", 22, id="title-fetch-failed"),
        ],
    )
    def test_an_unreadable_title_still_resolves_rather_than_failing(
        self, tmp_path: Path, title: str, curl_exit: int
    ) -> None:
        """Picking the wrong model is recoverable; failing the whole round is not."""
        result, outs, _ = self._run(tmp_path, title=title, curl_exit=curl_exit, family="sonnet")
        assert result.returncode == 0, result.stderr
        assert outs == {"model": "sonnet"}

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            pytest.param("review", "opus", id="review-stays-on-opus"),
            pytest.param("respond", "opus", id="respond-runs-the-default"),
        ],
    )
    def test_a_pr_naming_no_ticket_has_an_unknown_author(self, tmp_path: Path, mode: str, expected: str) -> None:
        """resolve-ticket-model exits 2 on no ticket; review must not treat its opus default as
        an opus author and hand the PR to sonnet."""
        result, outs, _ = self._run(tmp_path, mode=mode, title="Bump the deps", family="opus", family_exit=2)
        assert result.returncode == 0, result.stderr
        assert outs == {"model": expected}
        assert "author=unknown" in result.stdout
