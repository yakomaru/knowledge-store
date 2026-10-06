"""Retrieval: ranking, supersession, conflict, staleness."""

from datetime import datetime, timedelta, timezone

from knowledge_store import config as cfg


def _backdate(store, entry_id, days):
    ts = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    store.conn.execute("UPDATE entries SET created_at = ? WHERE id = ?", (ts, entry_id))


def test_finds_a_fact_by_keyword(facts):
    hits = facts.search("Fastify HTTP gateway", project="freight-router").results
    assert hits
    assert "Fastify" in hits[0].content


def test_results_carry_provenance_source_and_date(facts):
    top = facts.search("PostGIS tiles Martin", project="freight-router").results[0]
    assert top.provenance == "sourced"
    assert top.source == "docs/local-dev-setup.md"
    assert top.created_at and top.age_days == 0
    assert top.stale is False


def test_score_components_are_exposed(facts):
    top = facts.search("Drizzle Prisma RLS", project="freight-router").results[0]
    assert top.relevance > 0
    assert top.trust == cfg.TRUST_WEIGHTS["verified"]
    assert 0 < top.recency <= 1.0
    assert top.score == top.relevance * top.trust * top.recency


def test_verified_outranks_generated_at_equal_relevance(store):
    body = "The nightly sync window is 02:00-04:00 UTC and must not overlap the backup job."
    gen = store.write(content=body, project="p", provenance="generated")
    ver = store.write(content=body.replace("02:00-04:00", "01:00-03:00"),
                      project="p", provenance="verified", enforce=False)
    hits = store.search("nightly sync window UTC backup", project="p").results
    assert [h.id for h in hits][0] == ver["id"]
    assert gen["id"] in [h.id for h in hits]


def test_recency_breaks_ties_between_equal_provenance(store):
    body_a = "The connector refresh token rotates every 30 days on the vendor side."
    body_b = "The connector refresh token rotates every 14 days on the vendor side."
    old = store.write(content=body_a, project="p", provenance="generated")
    new = store.write(content=body_b, project="p", provenance="generated", enforce=False)
    _backdate(store, old["id"], 400)
    hits = store.search("connector refresh token rotates vendor", project="p").results
    assert hits[0].id == new["id"]
    assert hits[0].recency > [h for h in hits if h.id == old["id"]][0].recency


def test_recency_is_floored_so_old_entries_are_not_buried(store):
    e = store.write(content="The original territory import used a CSV bulk loader "
                            "and that path is still the fallback today.",
                    project="p", provenance="verified")
    _backdate(store, e["id"], 3650)
    hit = store.search("territory import CSV bulk loader", project="p").results[0]
    assert hit.recency == cfg.RECENCY_FLOOR
    assert hit.stale is True


def test_staleness_is_advisory_not_a_filter(store):
    e = store.write(content="Redis runs single-node in staging with no replica, which "
                            "is fine because the queue is rebuildable from Postgres.",
                    project="p", provenance="verified")
    _backdate(store, e["id"], cfg.STALE_AFTER_DAYS + 5)
    hits = store.search("Redis staging replica queue", project="p").results
    assert len(hits) == 1
    assert hits[0].stale is True


def test_superseded_entries_drop_out_of_search(facts):
    original = facts.search("Fastify HTTP gateway", project="freight-router").results[0]
    replacement = facts.write(
        content="The api-gateway runs Fastify for HTTP only; the worker loop was split "
                "into its own process during Phase 1b.",
        project="freight-router", provenance="verified", supersedes=original.id,
    )
    ids = [h.id for h in facts.search("Fastify HTTP gateway worker",
                                      project="freight-router").results]
    assert replacement["id"] in ids
    assert original.id not in ids
    # The superseded entry still exists; history is not destroyed.
    assert facts.get(original.id) is not None


def test_replacement_points_back_at_what_it_replaced(facts):
    original = facts.search("Fastify HTTP gateway", project="freight-router").results[0]
    facts.write(content="The api-gateway runs Fastify for HTTP only; the worker loop "
                        "was split out in Phase 1b.",
                project="freight-router", provenance="verified", supersedes=original.id)
    top = facts.search("Fastify HTTP gateway worker", project="freight-router").results[0]
    assert top.supersedes == original.id


def test_project_scoping(store):
    body = "Deploys go out through GitHub Actions on merge to main."
    store.write(content=body, project="alpha", provenance="sourced", source="DEPLOY.md")
    store.write(content=body, project="beta", provenance="sourced", source="DEPLOY.md")
    scoped = store.search("deploys GitHub Actions merge", project="alpha").results
    assert {h.project for h in scoped} == {"alpha"}
    everywhere = store.search("deploys GitHub Actions merge", project="alpha",
                              cross_project=True).results
    assert {h.project for h in everywhere} == {"alpha", "beta"}


def test_cross_project_prefers_the_callers_own_project(store):
    body = "Deploys go out through GitHub Actions on merge to main after the e2e suite."
    store.write(content=body, project="alpha", provenance="sourced", source="DEPLOY.md")
    store.write(content=body, project="beta", provenance="sourced", source="DEPLOY.md")
    hits = store.search("deploys GitHub Actions merge e2e", project="beta",
                        cross_project=True).results
    assert hits[0].project == "beta"


def test_omitting_project_searches_everything_and_says_so(store):
    store.write(content="Deploys go out through GitHub Actions on merge to main.",
                project="alpha", provenance="sourced", source="DEPLOY.md")
    resp = store.search("deploys GitHub Actions")
    assert resp.results
    assert any("every project" in n for n in resp.notes)


def test_conflict_surfaces_both_entries(store):
    store.write(content="The connector refresh token rotates every 30 days, so the "
                        "scheduler re-authenticates monthly against the vendor API.",
                project="p", provenance="generated")
    store.write(content="The connector refresh token rotates every 14 days; the vendor "
                        "shortened the window and the scheduler must re-auth fortnightly.",
                project="p", provenance="verified", enforce=False)
    resp = store.search("connector refresh token rotates scheduler", project="p")
    assert len(resp.results) == 2, "both sides of a disagreement must be returned"
    assert resp.conflicts, "the disagreement should be flagged, not silently resolved"
    flagged = set(resp.conflicts[0]["entries"])
    assert flagged == {r.id for r in resp.results}


def test_supersession_resolves_a_conflict(store):
    a = store.write(content="The connector refresh token rotates every 30 days, so the "
                            "scheduler re-authenticates monthly against the vendor API.",
                    project="p", provenance="generated")
    store.write(content="The connector refresh token rotates every 14 days; the vendor "
                        "shortened the window and the scheduler re-auths fortnightly.",
                project="p", provenance="verified", supersedes=a["id"])
    resp = store.search("connector refresh token rotates scheduler", project="p")
    assert not resp.conflicts
    assert len(resp.results) == 1


def test_entries_in_different_projects_do_not_conflict(store):
    body_a = "The refresh token rotates every 30 days and the scheduler re-auths monthly."
    body_b = "The refresh token rotates every 14 days and the scheduler re-auths fortnightly."
    store.write(content=body_a, project="alpha", provenance="generated")
    store.write(content=body_b, project="beta", provenance="generated")
    resp = store.search("refresh token rotates scheduler", project="alpha",
                        cross_project=True)
    assert len(resp.results) == 2
    assert not resp.conflicts


def test_limit_is_respected(store):
    for i in range(12):
        store.write(content=f"Rate limiting rule number {i}: the connector budget is "
                            f"{i * 100} requests per minute against the vendor API.",
                    project="p", provenance="sourced", source=f"docs/rule-{i}.md",
                    enforce=False)
    assert len(store.search("rate limiting connector budget", project="p", limit=5).results) == 5


def test_query_with_no_usable_terms(store):
    resp = store.search("the and of", project="p")
    assert resp.results == []
    assert resp.notes


def test_punctuation_in_query_does_not_break_fts(facts):
    for q in ['NEAR* "unbalanced', "rate-limit: redis^2", "a AND OR b", "*"]:
        facts.search(q, project="freight-router")  # must not raise


def test_fts_index_stays_in_sync_through_supersession(store):
    a = store.write(content="The tile server is Martin, started by docker compose.",
                    project="p", provenance="sourced", source="a.md")
    store.write(content="The tile server is Tegola now; Martin was dropped in Phase 2 "
                        "because of the projection handling.",
                project="p", provenance="verified", supersedes=a["id"])
    fts_rows = store.conn.execute("SELECT COUNT(*) c FROM entries_fts").fetchone()["c"]
    assert fts_rows == store.count()
    assert store.search("Tegola projection", project="p").results


def test_an_exact_score_tie_resolves_toward_the_newer_entry(store):
    """The brief's rule is prefer newest, including inside a single day.

    Identical content gives identical BM25, identical trust and identical recency,
    so the score ties exactly and only the tiebreak decides. Sorting created_at
    ascending here would hand back the oldest, which is backwards, and a day-
    granularity age cannot separate two entries written minutes apart.
    """
    body = "The queue drains oldest first and the worker count is fixed."
    first = store.write(content=body, project="p", provenance="generated")
    second = store.write(content=body, project="p", provenance="generated",
                         enforce=False)
    # Same day, minutes apart -- the realistic shape of a same-session correction.
    store.conn.execute("UPDATE entries SET created_at = ? WHERE id = ?",
                       ("2026-09-14T09:00:00+00:00", first["id"]))
    store.conn.execute("UPDATE entries SET created_at = ? WHERE id = ?",
                       ("2026-09-14T09:40:00+00:00", second["id"]))
    hits = store.search("queue drains oldest worker count fixed", project="p").results
    assert len(hits) == 2
    assert hits[0].score == hits[1].score, "pointless unless the scores tie exactly"
    assert hits[0].id == second["id"], "the newer entry must come first"
