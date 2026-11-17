"""linear-agent-token (the CI app-actor token mint) and linear-issue (one issue by identifier)."""

import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from helpers import KORG_CONFIG_STUB, TEAM, run, stub_dir


class TestLinearAgentToken:
    """Mints the CI app-actor token via client_credentials and exports it as LINEAR_API_KEY
    through $GITHUB_ENV, masked from the log."""

    _CURL_STUB = (
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$@" > "$STUB_DIR/curl_argv"\n'
        'cat > "$STUB_DIR/curl_stdin"\n'
        '[ "${STUB_CURL_EXIT:-0}" -eq 0 ] || exit "${STUB_CURL_EXIT}"\n'
        "printf '%s' \"$STUB_CURL_JSON\"\n"
    )

    def _run(
        self,
        tmp_path: Path,
        curl_json: str = '{"access_token": "tok-123", "expires_in": 2592000}',
        curl_exit: int = 0,
        omit: str | None = None,
    ) -> tuple[Path, object, str]:
        stubs = stub_dir(tmp_path, {"curl": self._CURL_STUB})
        github_env = tmp_path / "github_env"
        github_env.touch()
        env = {
            "STUB_CURL_JSON": curl_json,
            "STUB_CURL_EXIT": str(curl_exit),
            "LINEAR_CLIENT_ID": "cid",
            "LINEAR_CLIENT_SECRET": "csecret",
            "GITHUB_ENV": str(github_env),
        }
        if omit:
            env.pop(omit)
        result = run("linear-agent-token", [], stubs, env)
        return stubs, result, github_env.read_text()

    def test_exports_the_token_masked(self, tmp_path: Path) -> None:
        _, result, github_env = self._run(tmp_path)
        assert result.returncode == 0, result.stderr
        assert "LINEAR_API_KEY=tok-123" in github_env
        assert "::add-mask::tok-123" in result.stdout

    def test_requests_the_pinned_grant_and_scope(self, tmp_path: Path) -> None:
        """The scope string is an invariant: a mint with a different scope revokes every
        outstanding app token (Linear client_credentials semantics)."""
        stubs, _, _ = self._run(tmp_path)
        body = parse_qs((stubs / "curl_stdin").read_text())
        assert body["grant_type"] == ["client_credentials"]
        assert body["scope"] == ["read,write,app:assignable,app:mentionable"]

    def test_the_client_secret_never_appears_in_curl_argv(self, tmp_path: Path) -> None:
        """The form body goes over stdin precisely so the secret is invisible to ps//proc on a
        shared runner; a regression back to -d argv must fail here."""
        stubs, _, _ = self._run(tmp_path)
        assert "csecret" not in (stubs / "curl_argv").read_text()
        assert parse_qs((stubs / "curl_stdin").read_text())["client_secret"] == ["csecret"]

    def test_curl_failure_exports_nothing_and_fails(self, tmp_path: Path) -> None:
        _, result, github_env = self._run(tmp_path, curl_exit=22)
        assert result.returncode != 0
        assert github_env == ""

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param('{"error": "unauthorized_client"}', id="oauth-error-body"),
            pytest.param("not json", id="non-json-body"),
            pytest.param('{"access_token": null}', id="null-token-must-not-export-the-string-None"),
            pytest.param('{"access_token": ""}', id="empty-token"),
        ],
    )
    def test_a_body_without_a_token_exports_nothing_and_fails(self, tmp_path: Path, body: str) -> None:
        _, result, github_env = self._run(tmp_path, curl_json=body)
        assert result.returncode != 0
        assert github_env == ""

    @pytest.mark.parametrize("missing", ["LINEAR_CLIENT_ID", "LINEAR_CLIENT_SECRET", "GITHUB_ENV"])
    def test_missing_required_env_refuses_before_any_call(self, tmp_path: Path, missing: str) -> None:
        stubs, result, _ = self._run(tmp_path, omit=missing)
        assert result.returncode != 0
        assert not (stubs / "curl_argv").exists()


class TestLinearIssue:
    """The identifier is rebuilt from the configured team key, so a bare number and a full id
    fetch the same issue."""

    _CURL_STUB = (
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$@" > "$STUB_DIR/curl_argv"\n'
        "printf '%s' \"$STUB_CURL_JSON\"\n"
    )
    _ISSUE = json.dumps({"data": {"issue": {"identifier": f"{TEAM}-42", "labels": {"nodes": [{"name": "x"}]}}}})

    def _run(self, tmp_path: Path, arg: str, *, team: bool = True) -> tuple[object, dict]:
        stubs = stub_dir(
            tmp_path,
            {"curl": self._CURL_STUB, "korg-config": KORG_CONFIG_STUB if team else "#!/usr/bin/env bash\n"},
        )
        result = run("linear-issue", [arg], stubs, {"LINEAR_API_KEY": "k", "STUB_CURL_JSON": self._ISSUE})
        argv = (stubs / "curl_argv").read_text().splitlines() if (stubs / "curl_argv").exists() else []
        body = next((json.loads(a) for a in argv if a.startswith("{")), {})
        return result, body

    @pytest.mark.parametrize("arg", [f"{TEAM}-42", "42"])
    def test_queries_the_configured_teams_identifier(self, tmp_path: Path, arg: str) -> None:
        result, body = self._run(tmp_path, arg)
        assert result.returncode == 0, result.stderr
        assert body["variables"] == {"id": f"{TEAM}-42"}
        assert json.loads(result.stdout)["labels"] == [{"name": "x"}]

    def test_an_unset_team_refuses_before_any_call(self, tmp_path: Path) -> None:
        result, body = self._run(tmp_path, "42", team=False)
        assert result.returncode != 0
        assert "linear.team" in result.stderr
        assert body == {}
