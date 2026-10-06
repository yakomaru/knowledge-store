"""SQLite + FTS5 storage, ranking, and the write gate.

Design notes that are load-bearing:

* ``provenance`` is NOT NULL with no DEFAULT, and is checked in Python before it
  ever reaches SQL. A store that mixes model conclusions with sourced facts
  without marking which is which degrades on every write.
* Entries are never deleted. Correction happens through supersession, so the
  history of what was believed stays intact.
* Ranking components are returned alongside every result. Opaque ranking is
  untunable ranking.
"""

from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config as cfg
from .dedupe import fts_query_from, looks_like_chatter, similarity

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  id            TEXT PRIMARY KEY,
  project       TEXT NOT NULL,
  content       TEXT NOT NULL,
  provenance    TEXT NOT NULL CHECK(provenance IN ('sourced','generated','verified')),
  source        TEXT,
  created_at    TEXT NOT NULL,
  superseded_by TEXT REFERENCES entries(id),
  CHECK (provenance <> 'sourced' OR (source IS NOT NULL AND length(trim(source)) > 0))
);
CREATE INDEX IF NOT EXISTS idx_entries_project    ON entries(project);
CREATE INDEX IF NOT EXISTS idx_entries_superseded ON entries(superseded_by);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
  content,
  content='entries',
  content_rowid='rowid',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
  INSERT INTO entries_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, content) VALUES('delete', old.rowid, old.content);
  INSERT INTO entries_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class WriteRefused(Exception):
    """The write did not meet the bar. The message explains what to do instead."""


@dataclass
class Result:
    id: str
    project: str
    content: str
    provenance: str
    source: str | None
    created_at: str
    age_days: int
    stale: bool
    score: float
    relevance: float
    trust: float
    recency: float
    supersedes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Round only on the way out. BM25 magnitudes can sit near 1e-6, where
        # fixed-decimal rounding collapses genuinely different scores onto one
        # value and silently destroys the ordering.
        for key in ("score", "relevance"):
            d[key] = float(f"{d[key]:.6g}")
        d["recency"] = round(d["recency"], 4)
        return d


@dataclass
class SearchResponse:
    results: list[Result] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [r.as_dict() for r in self.results],
            "conflicts": self.conflicts,
            "notes": self.notes,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else cfg.db_path()
        if self.path.parent and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(f"PRAGMA busy_timeout={cfg.BUSY_TIMEOUT_MS}")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(cfg.SCHEMA_VERSION),),
        )

    def close(self) -> None:
        self.conn.close()

    # -- reading ---------------------------------------------------------------

    def get(self, entry_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()

    def projects(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT project FROM entries ORDER BY project"
        ).fetchall()
        return [r["project"] for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]

    def _candidates(
        self, match: str, project: str | None, limit: int
    ) -> list[sqlite3.Row]:
        """Top matches by BM25, excluding superseded entries."""
        if not match:
            return []
        sql = [
            "SELECT e.*, bm25(entries_fts) AS bm25,",
            "       (SELECT id FROM entries p WHERE p.superseded_by = e.id) AS supersedes",
            "FROM entries_fts JOIN entries e ON e.rowid = entries_fts.rowid",
            "WHERE entries_fts MATCH ? AND e.superseded_by IS NULL",
        ]
        params: list[Any] = [match]
        if project is not None:
            sql.append("AND e.project = ?")
            params.append(project)
        sql.append("ORDER BY bm25 LIMIT ?")
        params.append(limit)
        try:
            return self.conn.execute(" ".join(sql), params).fetchall()
        except sqlite3.OperationalError as exc:
            if "fts5: syntax error" in str(exc):
                return []
            raise

    def search(
        self,
        query: str,
        project: str | None = None,
        cross_project: bool = False,
        limit: int = cfg.DEFAULT_LIMIT,
    ) -> SearchResponse:
        resp = SearchResponse()
        match = fts_query_from(query, max_terms=32)
        if not match:
            resp.notes.append("Query had no searchable terms.")
            return resp

        scope = None if cross_project else project
        if not cross_project and project is None:
            resp.notes.append(
                "No project given, so this searched every project. "
                "Pass project= to scope it."
            )

        rows = self._candidates(match, scope, max(limit * 4, 40))
        now = _now()
        scored: list[Result] = []
        for row in rows:
            created = _parse_ts(row["created_at"])
            age_days = max(0, (now - created).days)
            relevance = -float(row["bm25"])
            trust = cfg.TRUST_WEIGHTS.get(row["provenance"], 1.0)
            recency = max(
                cfg.RECENCY_FLOOR, 0.5 ** (age_days / cfg.RECENCY_HALF_LIFE_DAYS)
            )
            boost = (
                cfg.SAME_PROJECT_BOOST
                if cross_project and project and row["project"] == project
                else 1.0
            )
            scored.append(
                Result(
                    id=row["id"],
                    project=row["project"],
                    content=row["content"],
                    provenance=row["provenance"],
                    source=row["source"],
                    created_at=row["created_at"],
                    age_days=age_days,
                    stale=age_days > cfg.STALE_AFTER_DAYS,
                    score=relevance * trust * recency * boost,
                    relevance=relevance,
                    trust=trust,
                    recency=recency,
                    supersedes=row["supersedes"],
                )
            )

        # Two passes, relying on sort stability. The pre-pass puts the newest
        # first so that entries whose scores tie resolve toward the newer one --
        # the brief's rule. Sorting created_at ascending in a single pass would
        # resolve ties toward the *oldest*, which is backwards, and age_days is
        # too coarse to separate two entries written on the same day.
        scored.sort(key=lambda r: r.created_at, reverse=True)
        scored.sort(key=lambda r: (-r.score, -r.trust))
        resp.results = scored[:limit]
        resp.conflicts = self._conflicts(resp.results)
        return resp

    def _conflicts(self, results: Iterable[Result]) -> list[dict[str, Any]]:
        """Pairs covering the same ground, in the same project, unreconciled.

        This is topical-overlap detection, not contradiction detection: it finds
        two entries that are about the same thing and not linked by supersession.
        Whether they actually disagree is the caller's call -- which is why both
        are returned and neither is dropped.
        """
        out: list[dict[str, Any]] = []
        items = list(results)
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a.project != b.project:
                    continue
                if a.supersedes == b.id or b.supersedes == a.id:
                    continue
                overlap = similarity(a.content, b.content)
                if overlap < cfg.CONFLICT_THRESHOLD:
                    continue
                if overlap >= cfg.DUPE_REFUSE_THRESHOLD:
                    continue  # effectively the same passage, not a disagreement
                newer, older = (a, b) if a.created_at >= b.created_at else (b, a)
                out.append(
                    {
                        "entries": [a.id, b.id],
                        "project": a.project,
                        "overlap": round(overlap, 3),
                        "note": (
                            f"{newer.id} ({newer.provenance}, {newer.created_at[:10]}) and "
                            f"{older.id} ({older.provenance}, {older.created_at[:10]}) cover "
                            "the same ground and neither supersedes the other. "
                            "Both are returned; decide which holds."
                        ),
                    }
                )
        return out

    # -- writing ---------------------------------------------------------------

    def write(
        self,
        content: str,
        project: str,
        provenance: str,
        source: str | None = None,
        supersedes: str | None = None,
        enforce: bool = True,
    ) -> dict[str, Any]:
        """Insert an entry. Raises WriteRefused when the write does not qualify."""
        content = (content or "").strip()
        project = (project or "").strip()
        source = (source or "").strip() or None
        warnings: list[str] = []

        # -- the brief's one hard rule, checked before anything else.
        if not provenance:
            raise WriteRefused(
                "provenance is required and has no default. Use one of: "
                + "; ".join(f"{k} ({v})" for k, v in cfg.PROVENANCE_HELP.items())
            )
        if provenance not in cfg.PROVENANCE_VALUES:
            raise WriteRefused(
                f"provenance must be one of {cfg.PROVENANCE_VALUES}, got {provenance!r}."
            )
        if provenance == "sourced" and not source:
            raise WriteRefused(
                "provenance='sourced' requires source: the path, URL, or command "
                "that produced this. Without it the claim cannot be re-checked."
            )
        if not project:
            raise WriteRefused("project is required, even while you only have one.")
        if not content:
            raise WriteRefused("content is empty.")

        if enforce:
            if len(content) < cfg.MIN_CONTENT_CHARS:
                raise WriteRefused(
                    f"content is {len(content)} chars; the minimum is "
                    f"{cfg.MIN_CONTENT_CHARS}. State the decision and its reason so "
                    "the entry means something in a session that lacks this context."
                )
            marker = looks_like_chatter(content, cfg.CHATTER_MARKERS)
            if marker:
                warnings.append(
                    f"Content reads like session narration (matched {marker!r}). "
                    "Durable knowledge outlives the session that produced it."
                )

        prior = self.get(supersedes) if supersedes else None
        if supersedes:
            if prior is None:
                raise WriteRefused(f"supersedes={supersedes!r} does not exist.")
            if prior["project"] != project:
                raise WriteRefused(
                    f"supersedes={supersedes!r} belongs to project "
                    f"{prior['project']!r}, not {project!r}."
                )
            if prior["superseded_by"]:
                raise WriteRefused(
                    f"{supersedes!r} was already superseded by "
                    f"{prior['superseded_by']!r}. Supersede that one instead."
                )

        if enforce:
            near = self._nearest(content, project, exclude=supersedes)
            if near:
                score, row = near
                if score >= cfg.DUPE_REFUSE_THRESHOLD and not supersedes:
                    raise WriteRefused(
                        f"Near-duplicate of entry {row['id']} "
                        f"({row['provenance']}, {row['created_at'][:10]}, "
                        f"{int(score * 100)}% similar):\n"
                        f"  {row['content'][:200]}\n"
                        f"If this replaces it, pass supersedes=\"{row['id']}\". "
                        "If it is genuinely new, rephrase to state what differs."
                    )
                if cfg.DUPE_WARN_THRESHOLD <= score < cfg.DUPE_REFUSE_THRESHOLD:
                    warnings.append(
                        f"{int(score * 100)}% similar to entry {row['id']}. "
                        "Consider supersedes= if this replaces it."
                    )

        if provenance == "generated":
            warnings.append(
                "Stored as 'generated' -- a model concluded it, nothing checked it. "
                "Once a test or a human confirms it, supersede it with provenance="
                "'verified' so later sessions can tell the difference."
            )

        entry_id = uuid.uuid4().hex[:8]
        created_at = _now().isoformat(timespec="seconds")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "INSERT INTO entries(id, project, content, provenance, source, "
                "created_at, superseded_by) VALUES(?,?,?,?,?,?,NULL)",
                (entry_id, project, content, provenance, source, created_at),
            )
            if supersedes:
                self.conn.execute(
                    "UPDATE entries SET superseded_by = ? WHERE id = ?",
                    (entry_id, supersedes),
                )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

        out: dict[str, Any] = {"id": entry_id, "created_at": created_at}
        if supersedes:
            out["superseded"] = supersedes
        if warnings:
            out["warnings"] = warnings
        return out

    def _nearest(
        self, content: str, project: str, exclude: str | None = None
    ) -> tuple[float, sqlite3.Row] | None:
        """Most similar live entry in the project, via BM25 shortlist then Jaccard."""
        rows = self._candidates(
            fts_query_from(content), project, cfg.DUPE_CANDIDATE_POOL
        )
        best: tuple[float, sqlite3.Row] | None = None
        for row in rows:
            if exclude and row["id"] == exclude:
                continue
            score = similarity(content, row["content"])
            if best is None or score > best[0]:
                best = (score, row)
        return best
