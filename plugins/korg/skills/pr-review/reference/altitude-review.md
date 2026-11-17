# Altitude review rubric

## When this applies

One whole-branch boundary: the `pr-review` bot's altitude reviewer, every `needs-review` round.
Not `/korg:commit`, which stays incremental and line-level, and not `/korg:open-pr`, where the
pass would only buy a second opinion on the same diff minutes before the bot gives it.

## The six questions

1. **Couldn't this be simpler**: is this the simplest possible code change that solves the
   problem? Ask it of the problem, not of the ticket's wording.
2. **Does this code need to exist**: is it solving a problem that exists *now*, or a
   speculated future one?
3. **Does each new abstraction / component / fetch serve a real present caller**, or is it
   flexibility with no consumer?
4. **Is this the wrong abstraction**: bending shared code with params/conditionals where
   duplication would be cheaper?
5. **Is the work appropriate to the change's actual job?**
6. **Scrap-and-redo:** knowing the final shape, is there a materially simpler version?

## Hard scope (failure-mode guard)

An altitude reviewer asked "what's too complex" will always find something and start
*adding* ceremony. To prevent that:

- Flag **only** what affects correctness or the stated requirement.
- Propose **cuts, not additions**: never recommend a new abstraction, layer, or config.
- Stay **silent** when the change is already minimal. No finding is the expected outcome on a
  tight diff.
