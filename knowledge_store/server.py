"""MCP server exposing exactly two tools: search and write.

Nothing else is exposed until these are genuinely in use. Ingest and evaluation
are command-line scripts, deliberately not tools -- they are operator actions,
not things an agent should reach for mid-session.

The tool descriptions below are not documentation. They are the primary write
discipline mechanism: they are the only thing a calling agent reads before
deciding whether something is worth persisting. The checks in ``store.write``
are the backstop for when they are ignored.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import Context, MCPServer

from . import config as cfg
from .store import Store, WriteRefused

mcp = MCPServer(
    name="knowledge-store",
    instructions=(
        "A cross-project knowledge store that survives between sessions. "
        "Search it before re-deriving something that was probably already decided. "
        "Write to it when a session produces knowledge that outlives the session."
    ),
)

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


#: Directories that are never a project. Guessing one of these would silently
#: scope a search to nonsense, which is worse than not guessing at all.
_NOT_A_PROJECT = {"/", str(Path.home()), "/tmp", "/private/tmp", "/usr", "/etc", "/var"}


def _current_project() -> tuple[str | None, str]:
    """Best-effort guess at the caller's project, plus how it was derived.

    A globally-registered stdio server is not told which repo the session is in.
    The MCP roots capability would have answered this, but it was deprecated in
    SEP-2577 (2026-07-28) along with sampling and logging, so this uses the
    server process's working directory instead -- a stdio server is spawned by
    the client, so that is normally the directory the session was started in.

    Both signals are advisory. The tool description tells agents to pass
    ``project`` explicitly, and every response says which signal was used so a
    wrong guess is visible rather than silent.
    """
    override = os.environ.get("KNOWLEDGE_STORE_PROJECT", "").strip()
    if override:
        return override, "KNOWLEDGE_STORE_PROJECT"
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None, "unavailable"
    if str(cwd) in _NOT_A_PROJECT or not cwd.name:
        return None, "working directory is not a project"
    return cwd.name, "working directory"


def _format(resp, scope_note: str) -> str:
    if not resp.results:
        lines = ["No matches."]
        lines.extend(resp.notes)
        lines.append(
            "An empty store is the normal state early on -- it fills as sessions "
            "write to it, not from a bulk import."
        )
        return "\n".join(lines)

    out: list[str] = [scope_note, ""]
    out.extend(resp.notes)
    for i, r in enumerate(resp.results, 1):
        age = "today" if r.age_days == 0 else f"{r.age_days}d ago"
        flags = " [STALE]" if r.stale else ""
        head = f"{i}. [{r.id}] {r.project} | {r.provenance} | {r.created_at[:10]} ({age}){flags}"
        out.append(head)
        if r.source:
            out.append(f"   source: {r.source}")
        if r.supersedes:
            out.append(f"   supersedes: {r.supersedes}")
        out.append(f"   {r.content}")
        out.append("")

    if resp.conflicts:
        out.append("--- UNRECONCILED ---")
        out.append(
            "These cover the same ground and neither supersedes the other. "
            "Both are shown deliberately; the store will not pick for you."
        )
        for c in resp.conflicts:
            out.append(f"  * {c['note']}")
        out.append("")

    if any(r.stale for r in resp.results):
        out.append(
            f"Entries older than {cfg.STALE_AFTER_DAYS} days are flagged STALE. "
            "That is an age signal, not a correctness one -- re-check before relying on them."
        )
    return "\n".join(out).rstrip()


@mcp.tool(
    description="""Search stored knowledge from past sessions, across projects.

Use this BEFORE re-deriving something that may already have been decided or
checked: architecture decisions, why an approach was rejected, a fact that was
expensive to establish, a constraint that is not obvious from the code.

Every result carries its provenance, so weigh them differently:
  verified  - generated, then checked by a human or a test. Trust most.
  sourced   - derived from a file, doc, URL, or command output. The `source`
              field names what produced it, so you can re-check it.
  generated - a model concluded it. Nothing has verified it. Treat as a lead,
              not as ground truth.

Every result also carries a date and an age. A fact verified three weeks ago may
be false now; entries past ~90 days are flagged STALE. Judge for yourself rather
than assuming the store is current.

When two entries cover the same ground and neither supersedes the other, BOTH are
returned under UNRECONCILED. That is deliberate. Do not silently pick one --
prefer the newer and the more-verified, and say that the disagreement exists.

Args:
  query: Keywords. Keyword search (BM25), so concrete nouns beat prose.
  project: Which project to search. Pass the repo directory name. Defaults to the
    workspace root if the client reports one, otherwise searches everything.
  cross_project: Search every project, not just this one. Use when the question is
    general ("how do we usually handle X") rather than about this repo.
  limit: Max results, default 10.""",
)
async def search(
    ctx: Context,
    query: str,
    project: str | None = None,
    cross_project: bool = False,
    limit: int = cfg.DEFAULT_LIMIT,
) -> str:
    inferred_via = None
    resolved = project
    if resolved is None:
        resolved, inferred_via = _current_project()
    limit = max(1, min(int(limit), 50))
    resp = store().search(
        query=query, project=resolved, cross_project=cross_project, limit=limit
    )
    if cross_project:
        scope = f"Searched all projects (favouring {resolved})." if resolved \
            else "Searched all projects."
    elif resolved:
        scope = f"Searched project '{resolved}'."
    else:
        scope = "Searched all projects (no project resolved)."
    if project is None and resolved:
        scope += f" Project inferred from the {inferred_via}; pass project= to override."
    return _format(resp, scope)


@mcp.tool(
    description="""Persist knowledge that should outlive this session.

Most of what happens in a session must NOT be written here. Noise destroys
retrieval quality, and a bad entry outlives the session that created it.

WRITE when the session produced:
  - a decision and the reasoning behind it ("chose X over Y because Z")
  - a dead end ("tried X, it fails because Y") -- high value and almost never
    recorded anywhere, yet it stops the next session repeating the work
  - a fact that was expensive to establish (took real digging to confirm)
  - a durable constraint that is not obvious from reading the code

DO NOT WRITE:
  - anything re-derivable by reading the code or running the tests
  - session-local state: progress, TODOs, what you are about to try
  - a restatement of something already stored (search first; if it has changed,
    supersede it instead of adding a second version)
  - speculation, unless you mark it provenance='generated'

provenance is REQUIRED and has no default. Choose honestly -- the whole store
depends on it, because a wrong guess stored as fact reads identically to a
checked one and the error compounds instead of being forgotten:
  sourced   - derived from a file, doc, URL, or command output. REQUIRES `source`.
  generated - you concluded it. Nothing has checked it.
  verified  - generated, then confirmed by a test run or by the user.

Entries are never deleted. When something becomes wrong, write the correction and
pass supersedes= with the old id; the old entry stays as history and stops being
returned by search.

Args:
  content: The passage. Self-contained -- a session six months from now has none
    of your current context. State the claim and its reasoning.
  project: Repo/project this belongs to. Required, even with only one project.
  provenance: 'sourced' | 'generated' | 'verified'. Required, no default.
  source: Path, URL, or command that produced this. Required when sourced.
  supersedes: Id of the entry this replaces, if any.""",
)
async def write(
    ctx: Context,
    content: str,
    project: str,
    provenance: str,
    source: str | None = None,
    supersedes: str | None = None,
) -> str:
    try:
        out = store().write(
            content=content, project=project, provenance=provenance,
            source=source, supersedes=supersedes,
        )
    except WriteRefused as exc:
        return f"REFUSED: {exc}"

    lines = [f"Stored {out['id']} in '{project}' as {provenance}."]
    if out.get("superseded"):
        lines.append(f"Superseded {out['superseded']}; it stays as history.")
    for w in out.get("warnings", []):
        lines.append(f"note: {w}")
    return "\n".join(lines)


def main() -> None:
    if os.environ.get("KNOWLEDGE_STORE_SELFTEST"):
        s = store()
        print(f"ok: {s.path} ({s.count()} entries, projects: {s.projects() or 'none'})")
        return
    mcp.run()


if __name__ == "__main__":
    main()
