# Cross-Project Knowledge Store

An MCP server giving any Claude Code session a searchable store of project
knowledge that survives across sessions and across projects. One store, many
projects, with `project` as metadata rather than one database per repo.

Agents start every session blank. Decisions, dead ends and verified facts live in
transcripts that are gone by the next session, or in markdown nobody greps.

## Why provenance is the whole design

A store that persists model conclusions next to sourced facts, without marking
which is which, degrades every time it is written to. Confidently wrong output
reads identically to verified output, so future retrievals treat both as ground
truth and the error compounds instead of evaporating at session end.

Every entry carries one of:

| provenance  | meaning                                            |
|-------------|----------------------------------------------------|
| `sourced`   | derived from a file, doc, URL, or command output. Requires `source`. |
| `generated` | a model concluded it. Nothing checked it.          |
| `verified`  | generated, then checked by a human or a test.      |

`write()` refuses a call with no provenance, and there is no default. It is
enforced in the tool schema, in Python, and by a SQL constraint.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
claude mcp add -s user knowledge-store -- \
  "$PWD/.venv/bin/python" -m knowledge_store.server
```

`-s user` registers it globally, so every project gets it. The store lives at
`~/.local/share/knowledge-store/store.db` (override with `KNOWLEDGE_STORE_DB`).

It starts **empty** and fills from `write()` as sessions happen. There is no bulk
import step — the ingest script below exists only to build evaluation fixtures.

### Make sessions actually use it

Registering the server makes the tools available; it does not make a session
reach for them. `global-CLAUDE.md` in this repo is the instruction set that does
— search before re-deriving, write decisions and dead ends at the end, state
provenance honestly. Install it globally:

```bash
cp global-CLAUDE.md ~/.claude/CLAUDE.md
```

It loads into every session, so keep it lean; anything repo-specific belongs in
that repo's own `CLAUDE.md` instead.

## The two tools

```
search(query, project=None, cross_project=False, limit=10)
write(content, project, provenance, source=None, supersedes=None)
```

That is the entire interface, deliberately. Nothing else is added until these are
genuinely in use.

### What earns a write

The `write()` tool description is the real write-discipline mechanism — it is the
only thing a calling agent reads before deciding to persist something. Most of
what happens in a session should **not** persist; noise collapses retrieval
quality and a bad entry outlives the session that created it.

Write a decision and its reasoning, a dead end (`tried X, fails because Y` — high
value and almost never recorded), a fact that was expensive to establish, or a
durable constraint. Do not write anything re-derivable from the code, session
progress, TODOs, or a restatement of something already stored.

Mechanical backstops, for when that is ignored: missing provenance, a `sourced`
entry with no `source`, content under 40 characters, and near-duplicates are all
refused. A duplicate refusal names the entry to supersede, so it redirects rather
than blocks.

### Conflict, supersession and staleness

Entries are never deleted. A correction is a new entry with `supersedes=<id>`;
the old one stays as history and stops being returned.

When two entries cover the same ground and neither supersedes the other, **both**
are returned under `UNRECONCILED`. The store does not pick for you. This is
topical-overlap detection, not contradiction detection — it finds entries about
the same thing, and leaves the judgement to the caller.

Every result carries its date and age, and is flagged `STALE` past 90 days. That
is an age signal, not a correctness one.

### Ranking

```
score = relevance(BM25) * trust(provenance) * recency(180d half-life, floored)
```

Multiplicative on top of relevance, so trust and recency reorder comparably
relevant entries without floating an irrelevant `verified` entry above a strongly
matching `generated` one. Every component is returned with each result — opaque
ranking is untunable ranking. The constants live in `knowledge_store/config.py`.

## Measuring retrieval

Bad recall produces bad agent output, which is the failure this exists to
prevent, so it is measured rather than assumed.

```bash
python -m knowledge_store.ingest eval/corpus --db eval/fixtures/synthetic.db
python eval/run_eval.py                  # --failures shows only misses
```

`eval/corpus/` is a synthetic corpus committed to this repo, so the numbers below
are reproducible by anyone who clones it. It is deliberately awkward: projects
share vocabulary, one planning document is duplicated across two projects, and
several documents cover the same subsystem from different angles. A corpus of
unrelated documents scores a perfect 1.00 and measures nothing.

```
108 passages, 20 files, 6 projects
hit@1 0.92   hit@5 1.00   recall@10 1.00   MRR 0.962
```

Ingest is a command-line script rather than an MCP tool, and it refuses to write
into a database that already has entries — re-running it would append a second
copy of every passage and skew the measurement. Pass `--reset` to rebuild.

To measure against your own notes instead, point ingest at them and keep a
private golden set in `eval/queries.local.yaml` (gitignored):

```bash
python -m knowledge_store.ingest ~/notes --db eval/fixtures/local.db
python eval/run_eval.py --local
```

### What the eval does and does not cover

It measures BM25 retrieval: query/passage matching, the heading splitter, and the
cross-project boost. Two floors gate it — recall catches retrieval collapsing,
MRR catches ranking drift that recall@10 is blind to, since an entry sliding from
rank 1 to rank 9 leaves recall untouched.

It is **structurally blind to the trust and recency weights.** An ingested corpus
is uniformly `sourced` with a single timestamp, so both are constant multipliers
across every entry and cannot reorder anything. Provenance ordering, recency
tiebreaks, staleness, conflict detection and supersession are covered by the test
suite instead, not by these numbers.

The harness also gates the embeddings decision. Keyword search stays until a
specific query can be shown to fail on it; `run_eval.py` lists exactly those
queries. There are none at this baseline, so there is no case for a vector index
yet. When there is, the move is hybrid BM25 + vector blended, not one replacing
the other.

## Notes

`project` is required from day one even with a single project — retrofitting it
later is a migration you do not want.

A globally registered stdio server is not told which repo the session is in. MCP
roots would have answered this but were deprecated in SEP-2577 (2026-07-28), so
`project` falls back to `KNOWLEDGE_STORE_PROJECT`, then the server's working
directory, and every response states which signal it used. Passing `project`
explicitly is always better than relying on the guess.

Every session runs its own server process against one SQLite file, so the store
opens WAL with a busy timeout and supersession runs in a transaction.

```bash
.venv/bin/python -m pytest      # 52 tests
```

The suite covers the write gate (provenance refusals, duplicate redirection,
supersession chains), ranking order, conflict surfacing, staleness flags, the
code-fence trap in the splitter, and the two tools end-to-end over a real MCP
client session.
