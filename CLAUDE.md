# korg

korg is a Claude Code plugin and a set of reusable GitHub workflows that give a project an agent
harness: commit gates, ticket planning in Linear, PR review, and (to follow) an autonomous ticket
loop. `README.md` is the user-facing manual; this file is how korg itself is built.

## Layout

- `plugins/korg/skills/<name>/SKILL.md` (+ `reference/`): the `/korg:<name>` skills.
- `plugins/korg/bin/`: commands on PATH while the plugin is enabled; called by bare name from
  skills and by `<korg checkout>/plugins/korg/bin/<name>` from workflow steps.
- `plugins/korg/hooks/hooks.json`: plugin hooks.
- `.github/workflows/pr-review.yml`, `base-guard.yml`: reusable workflows projects call;
  `ci.yml`: korg's own CI. `.github/actions/`: composite actions for jobs that need the project's
  environment, which the project's own job calls. `docs/callers.md`: what a project adds.
- `tests/`: pytest for `bin/`, with stubbed `gh`/`curl`/`korg-config` on PATH.

## Principles

**Design**

1. **Project facts in config, machinery in korg.** No project name, path or ticket prefix in
   korg: each is a `.korg.yml` key. A skill stops when a key it needs is unset, so an
   unconfigured project gets a refusal, never a wrong-team ticket.
2. **Put a rule where the decision is made.** A constraint on a flag lives on that flag's
   definition and on the step that acts on it, not in a document the agent read earlier.
3. **Enforce with evidence in CI, not guards on tool calls.** No hook that infers intent from
   command text, and no side-channel state (marker files in `/tmp`) to authorize exceptions.
   Policy that cannot be checked from evidence stays an instruction.
4. **Trust what can be proven.** Decide trust from facts the platform guarantees (a same-repo
   branch was pushed by someone with write access), not from heuristics (who a PR's author is).
5. **Agents hold only the job's scoped token.** An agent may push its own branch and comment on
   its PR; anything that needs more (publishing to another branch, a deploy, a cross-repo write)
   runs in a deterministic workflow step that holds that credential.
6. **Fail loud.** An error surfaces as a non-zero exit or a refusal with the reason. Where a
   default is the safer outcome (a model, a best-effort comment), the fallback announces itself
   with a `::warning::`; it is never silent.
7. **The smallest construct that works.** Prefer deleting to adding. No new script, flag or
   step when an instruction or an existing step does the job.

**Change and release**

8. **Pin every upstream.** Actions and downloaded tools by commit SHA (with the version as a
   comment), packages by exact version, and korg's reusable workflows and CI clones by tag. An
   upgrade is a reviewed bump, never a floating ref.
9. **A release is one commit.** Bump `plugins/korg/.claude-plugin/plugin.json`, tag the same
   commit `vX.Y.Z`, and pin that tag in `docs/callers.md`. `v*` tags cannot be moved or deleted.
10. **Prove a change on a real consumer.** `bin/` gets deterministic tests here. Skills and
    workflows are proven by running them: locally with `--plugin-dir` against a project
    checkout, then on a throwaway ticket in a consuming project, through its review and a fix
    round. A change is not done until it has run where it will be used.
11. **Extract what two projects run.** A layer moves into korg once a second project runs it,
    taking the better side of each copy's drift; until then it stays in the project.

**Public repo**

12. **Everything merged is public at once.** No project names, ticket ids, private paths,
    hostnames or incident anecdotes. Comments state present-tense constraints; history and
    incidents belong in the PR description.

## Working on korg

- **Try a change**: in a consuming project's checkout, `claude --plugin-dir
  <this checkout>/plugins/korg`. Nothing needs committing or releasing.
- **Checks**: `.korg.yml` wires them into `/korg:commit`: `shellcheck`, `actionlint` and
  `claude plugin validate` for lint, `scripts/test` for tests (pytest, only when `bin/`, `tests/`
  or the gate itself changed). CI runs all but `claude plugin
  validate`, which needs the Claude CLI.
- **PRs and releases**: open PRs through `/korg:open-pr`; release per principle 9, then bump each
  consuming project's pin through its own PR.
