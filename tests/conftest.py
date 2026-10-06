import pytest

from knowledge_store.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def facts(store):
    """A small realistic corpus."""
    store.write(
        content="The api-gateway process runs Fastify and owns the HTTP surface "
                "plus the background worker loop.",
        project="freight-router", provenance="sourced", source="docs/architecture-tour.md",
    )
    store.write(
        content="Territory polygons are stored in PostGIS; the tile server is Martin, "
                "run from docker-compose for local development.",
        project="freight-router", provenance="sourced", source="docs/local-dev-setup.md",
    )
    store.write(
        content="We chose Drizzle over Prisma for the database layer because RLS-aware "
                "queries were far easier to express and the generated SQL stays readable.",
        project="freight-router", provenance="verified",
    )
    return store


@pytest.fixture
def anyio_backend():
    return "asyncio"
