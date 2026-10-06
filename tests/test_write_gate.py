"""The write gate. Most of what happens in a session should not persist."""

import pytest

from knowledge_store import config as cfg
from knowledge_store.store import Store, WriteRefused

GOOD = ("Redis is the rate-limit backend; connector retries read the token bucket "
        "from it rather than tracking state per process.")


def test_provenance_is_required_and_has_no_default(store):
    """The brief's one hard rule."""
    with pytest.raises(WriteRefused, match="provenance is required"):
        store.write(content=GOOD, project="p", provenance="")
    with pytest.raises(WriteRefused, match="provenance is required"):
        store.write(content=GOOD, project="p", provenance=None)


def test_provenance_must_be_in_the_enum(store):
    with pytest.raises(WriteRefused, match="must be one of"):
        store.write(content=GOOD, project="p", provenance="probably")


def test_sourced_requires_a_source(store):
    with pytest.raises(WriteRefused, match="requires source"):
        store.write(content=GOOD, project="p", provenance="sourced")
    # ...and succeeds once given one.
    assert store.write(
        content=GOOD, project="p", provenance="sourced", source="docs/redis.md"
    )["id"]


def test_sql_enforces_sourced_source_independently_of_python(store):
    """Defense in depth: the table CHECK holds even if the gate is bypassed."""
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO entries(id, project, content, provenance, source, created_at) "
            "VALUES('x','p','some content','sourced',NULL,'2026-01-01T00:00:00+00:00')"
        )


def test_project_is_required(store):
    with pytest.raises(WriteRefused, match="project is required"):
        store.write(content=GOOD, project="  ", provenance="generated")


def test_thin_content_is_refused(store):
    with pytest.raises(WriteRefused, match="minimum"):
        store.write(content="use redis", project="p", provenance="generated")


def test_near_duplicate_is_refused_and_names_the_entry(store):
    first = store.write(
        content="The api-gateway runs Fastify and owns the HTTP surface and worker loop.",
        project="p", provenance="sourced", source="docs/tour.md",
    )
    with pytest.raises(WriteRefused) as exc:
        store.write(
            content="api-gateway runs Fastify, owning the HTTP surface plus the worker loop.",
            project="p", provenance="generated",
        )
    msg = str(exc.value)
    assert first["id"] in msg
    assert "supersedes=" in msg


def test_near_duplicate_is_allowed_through_supersedes(facts):
    """The refusal is a redirect, not a wall."""
    original = facts.search("Fastify api-gateway HTTP", project="freight-router").results[0]
    out = facts.write(
        content="The api-gateway process runs Fastify and owns the HTTP surface; the "
                "worker loop moved out to its own process in the Phase 1b split.",
        project="freight-router", provenance="verified", supersedes=original.id,
    )
    assert out["superseded"] == original.id
    assert facts.get(original.id)["superseded_by"] == out["id"]


def test_duplicate_in_another_project_is_not_a_duplicate(store):
    """Same words, different project, is a legitimate separate fact."""
    body = "The deploy runs through GitHub Actions on merge to main, gated on the e2e suite."
    store.write(content=body, project="alpha", provenance="sourced", source="DEPLOY.md")
    assert store.write(
        content=body, project="beta", provenance="sourced", source="DEPLOY.md"
    )["id"]


def test_moderate_similarity_warns_but_writes(store):
    store.write(
        content="Territory polygons live in PostGIS and are served as vector tiles by Martin.",
        project="p", provenance="sourced", source="docs/a.md",
    )
    out = store.write(
        content="PostGIS holds the territory geometry; Martin serves tiles, and the "
                "overlay API reprojects them to WGS84 before the client draws anything.",
        project="p", provenance="sourced", source="docs/b.md",
    )
    assert out["id"]
    assert any("similar" in w for w in out.get("warnings", []))


def test_generated_writes_carry_a_promotion_note(store):
    out = store.write(content=GOOD, project="p", provenance="generated")
    assert any("verified" in w for w in out["warnings"])


def test_chatter_is_flagged(store):
    out = store.write(
        content="Let me try switching the connector to exponential backoff and see "
                "whether the rate limiter stops tripping during the nightly sync.",
        project="p", provenance="generated",
    )
    assert any("narration" in w for w in out["warnings"])


def test_supersedes_must_exist_and_match_project(facts):
    with pytest.raises(WriteRefused, match="does not exist"):
        facts.write(content="x" * 60, project="freight-router",
                    provenance="generated", supersedes="deadbeef")
    other = facts.write(content="An unrelated fact about a different project entirely, "
                                "long enough to pass the gate.",
                        project="other", provenance="generated")
    with pytest.raises(WriteRefused, match="belongs to project"):
        facts.write(content="y" * 60, project="freight-router",
                    provenance="generated", supersedes=other["id"])


def test_cannot_supersede_an_already_superseded_entry(store):
    a = store.write(content="A" + "a" * 60, project="p", provenance="generated")
    b = store.write(content="B" + "b" * 60, project="p", provenance="generated",
                    supersedes=a["id"])
    with pytest.raises(WriteRefused, match="already superseded"):
        store.write(content="C" + "c" * 60, project="p", provenance="generated",
                    supersedes=a["id"])
    assert b["superseded"] == a["id"]


def test_enforce_false_bypasses_the_gate_for_bulk_load(store):
    """Ingest loads known-good documents; it must not fight the dedupe gate."""
    body = "A short one."
    assert store.write(content=body, project="p", provenance="sourced",
                       source="a.md", enforce=False)["id"]
    assert store.write(content=body, project="p", provenance="sourced",
                       source="b.md", enforce=False)["id"]
