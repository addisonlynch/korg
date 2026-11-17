# Correctness & conventions reviewer checklist

The **correctness & conventions reviewer** (subagent #2, spawned per `reference/fan-out.md`)
walks every changed file applying the rules below and the project's stack-specific checklist
at `review.checklist` (its language, framework, database, pipeline and frontend rules) where
relevant; for other files, it uses judgment. Stay **diff-scoped** per the diff-scoped
constraint in `reference/fan-out.md`, and return `[fix here]` / `[follow-up]` / `[nit]`
findings to the orchestrator (label definitions are in `reference/posting.md`).

Contents:
- [Test integrity & CI](#test-integrity--ci)
- [Comments](#comments)
- [Security](#security)
- The project checklist at `review.checklist`

## Test integrity & CI

Run it once, exactly as written, with no env prefix for THIS command: `GH_TOKEN` and
`GITHUB_REPOSITORY` are already in the environment, and a prefixed command only matches the
run's permission allowlist when an entry names that exact prefixed form (the CI-status read in
`posting.md` step 5 has such an entry; this script does not):

```
pr-test-integrity-flag <pr-number>
```

It deterministically flags a deleted test file, a net drop in test assertions, or a neutered
test recipe (a removed test-runner line). (A `.github/workflows/` touch is not flagged: those
PRs route to a human before this reviewer runs, so the script never sees one.) This is computed
by script, not model judgment: post each line it outputs as its own `[fix here]` finding, quoted
verbatim, rather than re-deriving the check by eyeballing the diff. Empty output counts as "no
findings" **only from a call that exited 0**; do not invent one.

**A call that did not run is not "no findings".** If the invocation is denied, errors, or exits
non-zero, its empty stdout says nothing about the diff, and treating it as clean is the fail-open
this check exists to prevent. Return a `[fix here]` finding saying the test-integrity check could
not run, naming the error.

The script is a heuristic and can occasionally fire on a benign change (e.g. collapsing several
asserts into one parametrized test, or tweaking a test runner's flags in a recipe that still
runs the suite). When you can show from the diff that a flagged line is a false positive,
downgrade it to a `[nit]` that names why it is benign instead of posting `[fix here]`: a
`[fix here]` fails the `agent-review` check, so a provably-benign line must not go out as one.
This is not a licence to wave through a genuine test weakening: the default stays verbatim
`[fix here]`.

## Comments

Apply the project's comment rules (in `CLAUDE.md` or `.claude/rules/`) to every comment the
branch added, changed, or deleted. Also check untouched comments next to changed lines: that is
how comments go stale.

A comment that is false of the code, or a still-true comment deleted from code the branch did
not otherwise touch, is a correctness finding. Everything else is `[nit]`.

## Security

- Flag hardcoded API keys, tokens, connection strings, proxy credentials, or passwords anywhere
  in source, migrations, fixtures or recorded responses. Secrets come from the environment.
- Flag secrets exposed to a client bundle (an env var the frontend build inlines).
- Flag routes that take a resource ID without verifying the caller owns that resource (IDOR).
  Authentication is not authorization: check for the ownership assertion after resolving the
  object.
- Flag input schemas that include server-managed fields (`is_admin`, `role`, `tenant_id`,
  `created_by`): mass assignment.
- Flag SQL built by interpolating variables (f-strings, `%`, concatenation) rather than bound
  parameters, in migrations and application code alike.
- Flag a request URL built from user-supplied or stored input without hostname validation:
  potential SSRF.
