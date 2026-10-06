# Local Dev Setup — End to End

## Prerequisites

Node 22, pnpm 9, Docker Desktop. On Apple silicon the PostGIS image needs
Rosetta disabled or tile queries return empty geometry.

## One-time setup

```bash
pnpm install
docker compose up -d        # Postgres + PostGIS, Redis, tile server
cp .env.example .env
pnpm db:migrate && pnpm db:seed
```

## Step 1 — local infrastructure

`docker compose up -d` starts Postgres with PostGIS, Redis, and the Martin tile
server. Postgres listens on 5433 deliberately, so it will not collide with a
system Postgres on the default port.

## Step 2 — environment secrets

Carrier sandbox credentials go in `.env`. Without them the carrier-service boots
but every adapter reports unconfigured, and quote requests fall back to the
static rate table.

## Step 3 — migrate and seed

`pnpm db:migrate` is forward-only; there are no down migrations. To reset, drop
the volume with `docker compose down -v` and start again.

## Daily dev

`pnpm dev` runs the gateway, the carrier worker, and the Vite dev server together
with restart-on-change.
