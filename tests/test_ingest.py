"""Ingest: the splitter, and the code-fence trap in particular."""

from pathlib import Path

from knowledge_store.ingest import ingest, project_of, split_markdown

FENCED = """# Architecture Tour

Intro prose that is long enough to survive the minimum passage length filter here.

## Workspace layout

```
freight-router/
├── apps/
│   ├── api-gateway/        Fastify HTTP + worker logic
## this is not a heading, it is inside a fence
└── docs/                   This directory
```

pnpm workspaces. The root tsconfig is composite and tsc -b builds the graph.

## The four runtime processes

In v0 the platform is a single deployable, but the service boundaries are drawn
in code via packages/contracts so a future split is mechanical.
"""


def test_headings_inside_code_fences_are_not_split_points():
    passages = split_markdown(FENCED)
    assert len(passages) == 3, [p[:40] for p in passages]
    layout = next(p for p in passages if "Workspace layout" in p)
    assert "this is not a heading" in layout
    assert "pnpm workspaces" in layout, "the fence must not end the section early"


def test_passages_carry_their_heading_context():
    passages = split_markdown(FENCED)
    assert all(p.startswith("Architecture Tour") for p in passages)
    assert any("Architecture Tour > The four runtime processes" in p for p in passages)


def test_tilde_fences_are_handled():
    text = "# Doc\n\n## A\n\n~~~\n## not a heading inside tildes here\n~~~\n\nTrailing prose for the section body.\n"
    passages = split_markdown(text)
    assert len(passages) == 1
    assert "not a heading" in passages[0]


def test_documents_without_h2_stay_whole():
    text = "# Plain\n\n" + ("Some prose about the system that has no subheadings at all. " * 4)
    passages = split_markdown(text)
    assert len(passages) == 1


def test_stub_sections_are_dropped():
    text = "# Doc\n\n## Empty\n\n## Real\n\n" + ("Real content that is long enough to matter. " * 4)
    passages = split_markdown(text)
    assert len(passages) == 1
    assert "Real" in passages[0]


def test_project_comes_from_the_first_path_segment(tmp_path):
    root = tmp_path / "Documents"
    (root / "freight-router" / "docs").mkdir(parents=True)
    f = root / "freight-router" / "docs" / "tour.md"
    assert project_of(f, root) == "freight-router"


def test_ingest_end_to_end(tmp_path):
    root = tmp_path / "corpus"
    (root / "alpha" / "docs").mkdir(parents=True)
    (root / "beta").mkdir(parents=True)
    (root / "alpha" / "docs" / "tour.md").write_text(FENCED)
    (root / "beta" / "README.md").write_text(
        "# Beta\n\n## Setup\n\n" + ("Run docker compose up to start Postgres and Redis. " * 3))
    (root / "alpha" / "node_modules").mkdir()
    (root / "alpha" / "node_modules" / "junk.md").write_text("# Junk\n\n" + "noise " * 40)

    db = tmp_path / "eval.db"
    stats = ingest(root, db)
    assert stats["projects"] == {"alpha", "beta"}
    assert stats["files"] == 2, "node_modules must be skipped"

    from knowledge_store.store import Store
    s = Store(db)
    hits = s.search("Fastify worker logic", project="alpha").results
    assert hits
    assert hits[0].provenance == "sourced"
    assert hits[0].source == "docs/tour.md"


def test_bulk_ingest_is_not_blocked_by_the_dedupe_gate(tmp_path):
    """Two docs legitimately describing the same thing must both land."""
    root = tmp_path / "corpus"
    (root / "p").mkdir(parents=True)
    body = "# D\n\n## S\n\n" + ("The api gateway runs Fastify and owns the HTTP surface. " * 3)
    (root / "p" / "a.md").write_text(body)
    (root / "p" / "b.md").write_text(body)
    stats = ingest(root, tmp_path / "e.db")
    assert stats["passages"] == 2
    assert stats["refused"] == 0
