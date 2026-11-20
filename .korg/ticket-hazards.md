# Ticket hazards

Read before any ticket is queued for an unattended run. korg's workflows and scripts are what
review, gate and dispatch agents in every consuming project, so an agent must not change its own
judge.

- **Review and dispatch machinery**: refuse an unattended task that changes
  `.github/workflows/`, `.github/actions/`, `plugins/korg/hooks/`, `linear-agent-token`, the
  scripts that publish, finalize or route the `agent-review` check (`publish-review-check`,
  `review-check-finalize`, `verify-review-submitted`, `pr-touches-workflows`) or decide a fix
  round (`review-loop-gate`, `review-loop-escalate`), or what this repo's review judges by
  (`.korg.yml`, `.korg/review-checklist.md`, `.claude/rules/testing-signal.md`). These go
  through a human-driven PR.
- **Releases**: refuse a task that bumps the version, creates a tag or edits a consuming
  project's pin. A release is a human step (CLAUDE.md principle 9).
- **Public repo**: a ticket whose change adds a project name, ticket id, private path or
  hostname must say that none may land in the diff (CLAUDE.md principle 12).
