# Knowledge store

A cross-project knowledge store is available through the `knowledge-store` MCP
server (`search` and `write`). It persists across sessions and projects, and it
is the only memory that survives this one.

**Search before re-deriving.** When a task turns on a past decision, a
non-obvious constraint, or a fact that would take real digging to re-establish,
search first. Pass `project` explicitly — the repo directory name. Use
`cross_project: true` when the question is general ("how do we usually handle
X") rather than about this repo.

**Write when a session produces something that outlives it:**
- a decision and the reasoning behind it ("chose X over Y because Z")
- a dead end ("tried X, it fails because Y") — high value, almost never recorded
- a fact that was expensive to establish
- a durable constraint that isn't obvious from the code

Do not write session progress, TODOs, anything re-derivable by reading the code,
or a restatement of something already stored. If something stored has become
wrong, write the correction with `supersedes=<id>` instead of adding a second
version — entries are never deleted, only superseded.

**Provenance is required, has no default, and must be honest:**
- `verified` — a test run or the user confirmed it
- `sourced` — from a file, doc, URL, or command output (requires `source`)
- `generated` — you concluded it; nothing has checked it

This is the part that matters. A wrong guess stored as fact reads identically to
a checked one, so future sessions treat both as ground truth and the error
compounds instead of evaporating. When unsure, `generated` is the honest answer.

Results carry dates and ages. A fact verified weeks ago may be false now — say
so rather than presenting a stale entry as current. When search returns entries
marked UNRECONCILED, both sides are shown deliberately: prefer the newer and
more-verified, and tell the user the disagreement exists rather than silently
picking one.
