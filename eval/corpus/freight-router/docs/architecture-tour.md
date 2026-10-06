# Architecture Tour

A ten-minute walk through the codebase so you can read it top-down instead of
stumbling into each module. Treat this as a map; the load-bearing detail lives in
`PLAN.md`.

## Workspace layout

```
freight-router/
├── apps/
│   ├── api-gateway/        Fastify HTTP surface + job dispatch
│   ├── carrier-service/    Carrier adapters, rate limits, auth refresh
│   ├── web/                React 19 + Vite SPA
│   └── web-e2e/            Playwright suite against the Vite app
├── packages/
│   ├── contracts/          Carrier-agnostic interfaces (load-bearing)
│   └── db/                 Drizzle schema, migrations, RLS-aware layer
├── infra/postgres/init/    PostGIS bootstrap SQL
└── docs/                   Ops and onboarding docs
```

pnpm workspaces. The root `tsconfig.json` is composite, so `tsc -b` walks the
dependency graph rather than rebuilding everything.

## The three runtime processes

In v0 the platform ships as a single deployable, but the service boundaries are
drawn in code through `packages/contracts` so splitting them later is mechanical.
Today the processes are the gateway, the carrier worker, and the tile server.

## The contracts boundary

Nothing in `apps/` may import from another app. Shared types live in
`packages/contracts`, and a carrier adapter that needs a new field adds it to the
interface first. This is the rule that keeps the carrier adapters swappable.

## api-gateway responsibilities

Terminates HTTP, authenticates the request, resolves the tenant, and either
answers from Postgres or enqueues a job. It never talks to a carrier API
directly — that is the carrier-service's job, and keeping the split means rate
limiting lives in exactly one place.

## carrier-service responsibilities

Owns every outbound call to a carrier: token refresh, retry, backoff, and the
shared rate-limit budget. Adapters are thin translations between the carrier's
payload shape and `packages/contracts`.

## Where to start reading by task

For a routing bug start at `apps/api-gateway/src/routes/quote.ts`. For a carrier
integration start at `packages/contracts/src/carrier.ts`, then the adapter. For a
map rendering problem start at `apps/web/src/map/overlay.tsx`.
