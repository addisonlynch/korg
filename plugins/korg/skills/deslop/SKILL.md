---
name: deslop
description: Run a three-agent adversarial review on the current diff (skeptic, slop detector, diff-aware rules cop), then apply the worthwhile fixes.
---

# Deslop

Run three focused agents in parallel on the current diff. Do not run lint (`/korg:commit`
Gate 1 owns that).

Scope: `git diff HEAD`, **plus every untracked file** (`git ls-files --others
--exclude-standard`). `git diff HEAD` shows no new file until it is staged, so a change whose
substance is new files would otherwise be reviewed as empty.

## Context bundle

Collect before spawning agents. Pass the same bundle to all three; subagents see nothing of
your context that is not in their prompt.

- `git diff HEAD`
- The full contents of every untracked file
- `CLAUDE.md` at the repo root
- The korg comment rules: `${CLAUDE_SKILL_DIR}/comments.md`
- Any project skill files relevant to the changed areas
- Any design doc directly referenced by the changed code
- The full content of changed files where the diff alone does not show enough context to judge
  structure

Skip anything that does not exist.

## Agents

Launch all three as parallel general-purpose subagents immediately, each receiving the full
bundle. Do not inline these reviews or self-assess the diff: the adversarial separation is the
point.

Every agent's prompt opens with: "You are a reviewer in the deslop fan-out. Report findings with
file, line, and why; change nothing. Judge against the diff and the repo only; call no MCP
tools." You are the only writer: fixes are applied in Synthesis.

---

### Agent 1: Skeptic

> You are a senior engineer reviewing a diff written by an AI. You are skeptical. Your job is to find the things that are embarrassing: not style, not formatting, but logic and structure that a thoughtful engineer would find ridiculous. AI code tends to implement a bloated, brittle construction where a fraction of the code would do; the reviewer's job is to be the one who says "couldn't you just do this instead?" and watch it collapse to a tenth the size. Read every changed line. If something makes you think "why does this exist" or "this is doing nothing" or "this is ten lines when it should be one", flag it. Specifically hunt for: abstractions with a single caller, dead code left behind after a change, defensive handling for cases that can't happen, and 1000-line solutions to 100-line problems. If you can't find anything wrong, look harder. Be specific: file, line, what's wrong, why it's wrong.

No checklist. No categories. Read the diff like someone looking for reasons to reject it.

---

### Agent 2: Slop detector

Read the diff for AI-generated filler. For each finding, give the fix: the exact replacement,
or "delete".

**Flag:**
- Any comment or docstring that fails the comment rules in your bundle (`comments.md`, plus any
  comment rules in `CLAUDE.md`, which win on conflict). Run the delete-and-ask test on every
  comment in the diff; where a constraint survives, keep that sentence and drop the rest.
- Apologetic hedges (`// This might need refactoring`, `// TODO: improve this`)
- `console.log("Starting...")` / `print("Done!")` with no diagnostic value
- Try/except or try/catch that re-raises with a worse message
- Defensive null checks on values that cannot be null given the types
- Wrapper functions that add no logic: one call site, no transformation
- Single-use "utility" functions that wrap a language primitive
- Ternaries whose branches produce the same result
- Dead code: variables never read, unreachable branches, conditions always true or false
- Copy-pasted blocks across files in the same diff that should be one function

**Keep:**
- Docstrings on public APIs that add non-derivable information: the why, constraints,
  invariants, units, edge cases, or a usage example. Being exported is not itself a reason to
  keep one that restates the name and type.
- Lint and type-checker suppression directives
- License headers
- Comments referencing a spec, RFC, or external link by a path or URL the reader can open. A
  bare section number or a codename from a design doc is not a reference.
- Comments above regex, bitwise ops, or non-obvious algorithms
- A `TODO(<ticket id>)` or authored TODO on genuinely incomplete work
- "Why" comments explaining a non-obvious constraint, workaround, or invariant, provided the
  condition is already reasonably named. If extracting it into a well-named function or
  variable would make the comment mostly unnecessary, flag that instead.

---

### Agent 3: Rules cop

Discover the rule set from the repo, not from a list here.

1. `git diff --name-only HEAD`: the changed paths.
2. `ls .claude/rules/*.md`: every rule file the repo defines.
3. Read each one's YAML frontmatter:
   - **`paths:` present**: load it if any changed path matches any of its globs.
   - **No `paths:` or no frontmatter**: unscoped, load it.
4. Always load `CLAUDE.md` at the repo root.

Apply every loaded rule against the diff. Report only violations actually present in it. If
`.claude/rules/` does not exist, `CLAUDE.md` is the whole rule set.

---

## Synthesis

After all three agents return:

1. Merge findings. Discard anything speculative, subjective, or out of scope.
2. Apply fixes that are clearly correct and local.
3. Re-run `commands.lint` from `.korg.yml` to confirm nothing broke.
4. Report what was fixed (file:line) and what was flagged but not fixed, with why.
5. **Deferred findings**: list every finding that was valid but out of scope for this commit
   (wrong abstraction boundary, needs untouched files), one sentence each. When
   `/korg:roadmap` is available, ask whether to queue any of them and invoke it for each one
   confirmed.

## Stop rules

- Do not refactor code outside the diff.
- Do not apply a fix the agents disagree on.
- A finding that needs untouched files is a note, not an edit.
- Synthesize and apply judgment; do not apply every suggestion blindly.
