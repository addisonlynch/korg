"""Shared stubs for the plugin bin script tests.

The scripts run from plugins/korg/bin with a temp stub dir prepended to PATH, so a stub of `gh`,
`curl`, `korg-config`, or a sibling script shadows the real one. Stubs record their argv and
replay canned bodies through the caller's own `--jq` filter, so the extraction is exercised.
"""

import os
import stat
import subprocess
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "plugins" / "korg" / "bin"
TEAM = "ABC"
OWNER = "Project Owner"

KORG_CONFIG_STUB = f"""#!/usr/bin/env bash
case "$1" in
  linear.team) echo {TEAM} ;;
  linear.owner) echo "{OWNER}" ;;
esac
"""
# An unconfigured project: every key reads empty.
NO_CONFIG_STUB = "#!/usr/bin/env bash\n"

# Dispatching gh stub for scripts that hit several endpoints in one run: replays a different
# body per call shape, applies the caller's own --jq filter, and records every argv.
LOOP_GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$STUB_DIR/gh_argv"
echo "---" >> "$STUB_DIR/gh_argv"
[ "${STUB_GH_EXIT:-0}" -eq 0 ] || exit "${STUB_GH_EXIT}"
jqf=""
prev=""
for a in "$@"; do
  [ "$prev" = "--jq" ] && jqf="$a"
  prev="$a"
done
case "$*" in
  # First: a GraphQL query text can mention `comments` and must not fall through to the POST.
  *graphql*)     body="${STUB_GH_GRAPHQL-}" ;;
  *"pr view"*)   body="${STUB_GH_PR_VIEW-}" ;;
  *check-runs*)  body="${STUB_GH_CHECKS-}" ;;
  # --paginate marks the comments LIST read (pr-comment-once's dedup probe); the POST
  # that follows it has no such flag, and the two need different bodies.
  *--paginate*)  body="${STUB_GH_COMMENTS-}" ;;
  *comments*)    body="${STUB_GH_POST-}" ;;
  *)             body="" ;;
esac
# Separate assignment, not a brace default: bash 5 parses the "}" inside ${VAR:-{}} as the
# expansion's closer and appends a stray brace to the JSON.
[ -n "$body" ] || body="{}"
if [ -n "$jqf" ]; then printf '%s' "$body" | jq -r "$jqf"; else printf '%s' "$body"; fi
"""

# Records the token and args gh was invoked with, so token-preference tests can assert which
# credential the script exported.
TOKEN_RECORDING_GH_STUB = """#!/usr/bin/env bash
echo "${GH_TOKEN:-}" > "$STUB_DIR/seen_token"
echo "$*" > "$STUB_DIR/seen_args"
echo '{"id": 555}'
exit "${STUB_GH_EXIT:-0}"
"""


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def stub_dir(tmp_path: Path, stubs: dict[str, str] | None = None) -> Path:
    d = tmp_path / "stubs"
    d.mkdir(exist_ok=True)
    for name, body in (stubs or {}).items():
        write_executable(d / name, body)
    return d


# Never inherited: CI sets several of these, and a script must see only what the test gives it.
_HERMETIC = (
    "GH_TOKEN",
    "CI_STATUS_GH_TOKEN",
    "GITHUB_REPOSITORY",
    "GITHUB_OUTPUT",
    "GITHUB_ENV",
    "CHECK_RUN_ID",
    "BEFORE",
    "LINEAR_API_KEY",
    "LINEAR_CLIENT_ID",
    "LINEAR_CLIENT_SECRET",
)


def run(
    script: str, args: list[str], stubs: Path, env: dict[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    """Run a real bin script with `stubs` ahead of the bin dir on PATH."""
    base = {k: v for k, v in os.environ.items() if k not in _HERMETIC}
    full = base | {"PATH": f"{stubs}:{BIN}:{os.environ['PATH']}", "STUB_DIR": str(stubs)} | (env or {})
    return subprocess.run([str(BIN / script), *args], env=full, cwd=cwd, capture_output=True, text=True)


def outputs(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {k: v for k, _, v in (line.partition("=") for line in path.read_text().splitlines())}


def gh_calls(stubs: Path) -> list[str]:
    path = stubs / "gh_argv"
    if not path.exists():
        return []
    return [c.replace("\n", " ").strip() for c in path.read_text().split("---") if c.strip()]


def posted_comment(calls: list[str]) -> str:
    """The comment POST, not the dedup probe that precedes it: pr-comment-once reads the existing
    comments from the same URL first, so a plain URL match finds the wrong call."""
    return next(c for c in calls if "issues/" in c and "comments" in c and "-X POST" in c)
