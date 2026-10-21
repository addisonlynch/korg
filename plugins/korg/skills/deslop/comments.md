# Comment rules

Code says what it does. A comment says what it cannot: why it is this way, what must stay true,
a workaround and what it works around, a constraint from outside the file, units, or what
`None` means. The default is no comment; write one only where a reader would otherwise get it
wrong or undo the choice.

- Describe the code as it stands. No narration of the edit ("now handles", "no longer"), no
  commented-out code.
- No ticket ids: they go in the commit message or PR description. The one exception is
  `TODO(<ticket id>)` on genuinely incomplete work. Link context with a path or URL the reader
  can open.
- No banner comments, no restating the next line.
- The test for any comment: delete it and ask what a reader loses that they cannot get back from
  the code beneath it, the field or type it names, or a path they can open. Nothing: remove it.
  A constraint: keep that sentence only. Something reachable nowhere: rewrite history as the
  present-tense constraint, and a codename or section number as a path or URL. Three shapes
  that fail it:
  - A docblock that walks the code beneath it. Section order, layout, branch lists, and column
    lists are read from the code.
  - The same fact on more than one layer of one diff (model, schema, client types). It lives
    once, on the layer that enforces it. Test docstrings are exempt.
  - Design history. What was tried, what it cost, and what replaced it go in the PR
    description; the constraint it left behind stays, in the present tense.
- A docstring covers what the signature cannot: side effects, raised exceptions, invariants on
  the return value, ordering guarantees. One that restates the signature is not written.
- Update a comment in the same edit as the code it describes. Delete a comment only when it is
  false, or when you are touching the code it describes and it fails these rules.

Good:

```python
# The upstream API rate-limits a second request inside two seconds, and the limit sticks to the
# client IP for the rest of the run.
await asyncio.sleep(REQUEST_DELAY_SECONDS)
```

Bad:

```python
# ----- retry handling (PROJ-123) -----
# Sleep for the request delay before the next request.
await asyncio.sleep(REQUEST_DELAY_SECONDS)

# Now uses REQUEST_DELAY_SECONDS instead of a hardcoded 2.
await asyncio.sleep(REQUEST_DELAY_SECONDS)
```
