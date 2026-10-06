"""End-to-end over a real MCP client session, including roots negotiation."""

import pytest
from mcp import Client

from knowledge_store import server as srv
from knowledge_store.store import Store


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_store", Store(tmp_path / "srv.db"))
    return srv._store


def text_of(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


@pytest.mark.anyio
async def test_tools_are_exactly_search_and_write(wired):
    async with Client(srv.mcp) as client:
        names = sorted(t.name for t in (await client.list_tools()).tools)
    assert names == ["search", "write"]


@pytest.mark.anyio
async def test_write_then_search_round_trip(wired):
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("write", {
            "content": "We chose Drizzle over Prisma for the DB layer because RLS-aware "
                       "queries were far easier to express and the SQL stays readable.",
            "project": "freight-router",
            "provenance": "verified",
        }))
        assert "Stored" in out

        hit = text_of(await client.call_tool("search", {
            "query": "Drizzle Prisma database layer choice",
            "project": "freight-router",
        }))
    assert "Drizzle" in hit
    assert "verified" in hit
    assert "freight-router" in hit


@pytest.mark.anyio
async def test_write_without_provenance_is_refused_by_the_schema(wired):
    """The brief's hard rule, enforced at the protocol boundary."""
    async with Client(srv.mcp) as client:
        schema = next(t for t in (await client.list_tools()).tools if t.name == "write")
        assert "provenance" in schema.input_schema["required"]
        assert "default" not in schema.input_schema["properties"]["provenance"]

        result = await client.call_tool("write", {
            "content": "Some claim about the system that is long enough to pass the gate.",
            "project": "p",
        })
    assert result.is_error


@pytest.mark.anyio
async def test_sourced_without_source_is_refused(wired):
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("write", {
            "content": "The tile server is Martin, started from docker-compose locally.",
            "project": "p", "provenance": "sourced",
        }))
    assert out.startswith("REFUSED")
    assert "requires source" in out


@pytest.mark.anyio
async def test_duplicate_write_is_refused_with_the_id_to_supersede(wired):
    body = ("The connector refresh token rotates every 30 days, so the scheduler "
            "re-authenticates monthly against the vendor API.")
    async with Client(srv.mcp) as client:
        first = text_of(await client.call_tool("write", {
            "content": body, "project": "p", "provenance": "verified"}))
        entry_id = first.split()[1]

        dupe = text_of(await client.call_tool("write", {
            "content": "The connector refresh token rotates every 30 days; the scheduler "
                       "re-auths monthly against the vendor API.",
            "project": "p", "provenance": "generated"}))
        assert dupe.startswith("REFUSED")
        assert entry_id in dupe

        fixed = text_of(await client.call_tool("write", {
            "content": "The connector refresh token now rotates every 14 days; the vendor "
                       "shortened the window, so the scheduler re-auths fortnightly.",
            "project": "p", "provenance": "verified", "supersedes": entry_id}))
    assert "Superseded" in fixed


@pytest.mark.anyio
async def test_conflicting_entries_are_both_surfaced(wired):
    wired.write(content="The nightly sync window is 02:00-04:00 UTC and must not "
                        "overlap the database backup job.",
                project="p", provenance="generated")
    wired.write(content="The nightly sync window is 01:00-03:00 UTC; it was moved "
                        "so the database backup job could start earlier.",
                project="p", provenance="verified", enforce=False)
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("search", {
            "query": "nightly sync window UTC backup", "project": "p"}))
    assert "UNRECONCILED" in out
    assert "02:00-04:00" in out and "01:00-03:00" in out


@pytest.mark.anyio
async def test_empty_store_explains_itself(wired):
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("search", {"query": "anything", "project": "p"}))
    assert "No matches" in out


@pytest.mark.anyio
async def test_project_is_inferred_when_not_passed(wired, monkeypatch):
    """Resolves 'project=current' without the deprecated roots capability."""
    monkeypatch.setenv("KNOWLEDGE_STORE_PROJECT", "pollen-bot")
    wired.write(content="Pollen station IDs are stable across seasons, so the bot can "
                        "cache the station list at startup instead of per request.",
                project="pollen-bot", provenance="verified")
    wired.write(content="Service area polygons live in PostGIS and Martin serves the tiles.",
                project="freight-router", provenance="sourced", source="docs/setup.md")
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("search", {"query": "station IDs startup fetch"}))
    assert "pollen-bot" in out
    assert "inferred from the" in out
    assert "PostGIS" not in out, "inference must scope the search, not just label it"


@pytest.mark.anyio
async def test_a_nonsense_working_directory_is_not_guessed_at(wired, monkeypatch):
    """Guessing a wrong project silently mis-scopes every search."""
    monkeypatch.delenv("KNOWLEDGE_STORE_PROJECT", raising=False)
    monkeypatch.chdir("/")
    wired.write(content="Service area polygons live in PostGIS and Martin serves the tiles.",
                project="freight-router", provenance="sourced", source="docs/setup.md")
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("search", {"query": "PostGIS Martin tiles"}))
    assert "PostGIS" in out, "it must fall back to searching everything"


@pytest.mark.anyio
async def test_search_without_project_or_roots_says_it_searched_everything(wired, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_STORE_PROJECT", raising=False)
    monkeypatch.chdir("/")
    wired.write(content="Service area polygons live in PostGIS and Martin serves the tiles.",
                project="freight-router", provenance="sourced", source="docs/setup.md")
    async with Client(srv.mcp) as client:
        out = text_of(await client.call_tool("search", {"query": "PostGIS Martin tiles"}))
    assert "every project" in out or "all projects" in out
