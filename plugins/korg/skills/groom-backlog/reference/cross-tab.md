# Label cross-tab

Read-only; feeds the report only. The counts span the whole open backlog of team `linear.team`,
not just the items groomed this pass. Address labels and states by name.

1. **Open tickets per area label**: for each area label in `planning.label_taxonomy`, count the
   open issues (state type backlog, unstarted or started) carrying it.
2. **Open `bug` count per area label**: the same, restricted to issues that also carry `bug`.
3. **`auto-filed` still open**: the total, and the count per state.
4. **Taxonomy drift**: list every label on the team and flag any name missing from
   `planning.label_taxonomy`. The file is the source of truth; a label that exists only in
   Linear came in through a side door and needs a decision: add it to the file, or retire it.

Report shape:

```
### Label cross-tab
Open by area: <label> N, <label> N
Bugs by area: <label> N
Auto-filed still open: N (N Backlog, N Todo, N Needs Human)
Labels in Linear missing from the taxonomy: none | name, name
```

Omit zero counts, and a line whose counts are all zero.
