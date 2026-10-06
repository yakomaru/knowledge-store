# Engineer Onboarding

## What this product is, in one paragraph

A quoting and routing layer between a shipper's order flow and several carrier
APIs. It normalises rates and transit estimates so the shipper can rate-shop
rather than defaulting to whichever integration works today.

## Read these next, in order

`docs/architecture-tour.md` for the module map, `PLAN.md` for the strategy and the
carrier interface, `docs/local-dev-setup.md` when you want it running, and
`DESIGN.md` before you touch the operator console.

## Worth knowing before you start

Postgres runs on 5433 locally, not 5432. Redis holds the rate-limit token buckets
and the job queue, and its eviction policy matters in production. Migrations are
forward-only. The carrier sandboxes rate-limit per account, so use your own
credentials rather than a shared set.

## How pnpm check is structured

`pnpm check` chains typecheck, lint, unit tests, then the Playwright e2e suite,
stopping at the first failure. Use `pnpm check:unit` while iterating.

## Tenant isolation

Every tenant-scoped table has a row-level security policy. You should never write
an explicit tenant filter in application code — if you feel the need to, the
policy is wrong.

## When you submit a PR

Keep the planning docs honest: if a PR changes a decision recorded in `PLAN.md`,
update that document in the same PR rather than leaving the two to drift.

## Where to ask for context

Architecture questions in the engineering channel, product decisions in the
product channel. If a document and the code disagree, the code wins and the
document is a bug.
