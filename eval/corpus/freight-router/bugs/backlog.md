# Backlog

## Policy

Anything that is not a release blocker lands here. S2 is scheduled within a
release; S3 is tracked but unscheduled. Severity is about customer impact, not
about how annoying the bug is to fix.

## Database / S2

The geocoding cache has no eviction, so the table grows without bound. It is
global rather than tenant-scoped, so the growth is slow, but it will need a TTL.

## Database / S3

Migrations are forward-only and there is no down path, which makes a bad migration
a restore-from-backup event rather than a rollback.

## Redis / S2

The rate-limit token bucket refill is computed in application code rather than in a
Lua script, so two gateway processes refilling concurrently can briefly exceed the
carrier budget.

## Infrastructure / S3

The tile server connects as a superuser role, which is how the tenant-isolation
blocker became possible. It needs its own least-privilege role.

## QA / testing / S2

The e2e suite boots real containers and takes four minutes, so developers skip it
locally and discover failures in CI instead.
