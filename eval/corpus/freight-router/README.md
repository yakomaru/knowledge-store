# freight-router

Multi-carrier freight quoting and routing.

## Repo layout

`apps/` holds the deployables, `packages/` the shared contracts and database
layer, `infra/` the local Postgres bootstrap. See `docs/architecture-tour.md`
before changing anything in `packages/contracts`.

## Prerequisites

Node 22, pnpm 9, Docker. Full walkthrough in `docs/local-dev-setup.md`.

## Running tests

`pnpm check` runs typecheck, lint, unit tests, and the Playwright e2e suite in
that order, stopping at the first failure. Run `pnpm check:unit` alone while
iterating — the e2e suite takes four minutes and boots real containers.

## Carrier sandbox setup

Each carrier needs a sandbox account before its adapter tests will run. The
credentials are per-developer, not shared, because the sandboxes rate-limit per
account and a shared one throttles everyone at once.
