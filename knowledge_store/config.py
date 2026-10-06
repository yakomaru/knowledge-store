"""Tunable constants and path resolution.

Every number that shapes retrieval lives here so the eval harness can move one
and measure what happened. Nothing in this module imports the rest of the package.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- storage -----------------------------------------------------------------

SCHEMA_VERSION = 1

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "knowledge-store" / "store.db"

#: Every Claude Code session spawns its own server process against one file.
#: WAL plus a real busy timeout is what makes that safe.
BUSY_TIMEOUT_MS = 5000


def db_path() -> Path:
    """Resolve the store location. ``KNOWLEDGE_STORE_DB`` overrides the default."""
    override = os.environ.get("KNOWLEDGE_STORE_DB")
    return Path(override).expanduser() if override else DEFAULT_DB_PATH


# --- provenance --------------------------------------------------------------

PROVENANCE_VALUES = ("sourced", "generated", "verified")

PROVENANCE_HELP = {
    "sourced": "derived from a file, doc, URL, or command output",
    "generated": "a model concluded it",
    "verified": "generated, then checked by a human or a test",
}

# --- ranking -----------------------------------------------------------------

#: Multiplicative trust boost. Applied on top of relevance so it acts as a
#: tiebreaker: it can reorder comparably-relevant entries but can never float an
#: irrelevant verified entry above a strongly matching generated one.
TRUST_WEIGHTS = {"verified": 1.30, "sourced": 1.15, "generated": 1.00}

#: Half-life decay in days, floored. The brief is explicit that the caller judges
#: staleness -- so age down-weights, it never buries.
RECENCY_HALF_LIFE_DAYS = 180.0
RECENCY_FLOOR = 0.5

#: Small nudge toward the caller's own project when searching across all of them.
SAME_PROJECT_BOOST = 1.10

#: Advisory only. Flags a result as old; never filters it out.
STALE_AFTER_DAYS = 90

DEFAULT_LIMIT = 10

# --- write gate --------------------------------------------------------------

#: Below this, a passage is too thin to retrieve or to mean anything later.
MIN_CONTENT_CHARS = 40

#: Refuse the write and point the caller at supersedes= instead.
DUPE_REFUSE_THRESHOLD = 0.85

#: Write succeeds, but say something.
DUPE_WARN_THRESHOLD = 0.60

#: How many BM25 candidates to pull before doing the (more expensive) Jaccard pass.
DUPE_CANDIDATE_POOL = 20

#: Topical-overlap threshold for surfacing two unreconciled entries as a conflict.
#: Deliberately lower than the dupe threshold: near-identical entries are
#: duplicates, while entries that merely cover the same ground may disagree.
CONFLICT_THRESHOLD = 0.40

#: Phrases that suggest session narration rather than durable knowledge.
CHATTER_MARKERS = (
    "let me ", "i'll ", "i will ", "trying to ", "let's ", "next step",
    "todo", "not sure", "maybe we", "i think we should", "going to try",
)
