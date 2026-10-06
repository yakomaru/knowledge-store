# Release Blockers

## Policy

A blocker is anything that loses customer data, bills incorrectly, or exposes one
tenant's data to another. Severity S0 ships a fix same-day; S1 blocks the release
but not the branch.

## S0 — Operational visibility

The gateway emits no metric when the carrier rate-limit budget is exhausted, so a
throttled carrier looks identical to a healthy one until quotes start timing out.
Needs a counter and an alert before the next release.

## S1 — Tenant isolation in tile queries

The tile endpoint reads the tenant from a query parameter rather than the session,
so a crafted request can render another tenant's service-area polygons. The RLS
policy covers the table but the tile server connects as a superuser role.
