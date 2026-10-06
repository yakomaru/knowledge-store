# Redis Operational Safety

## Current posture

Redis backs the rate-limit token buckets and the job queue. It runs single-node
in staging with no replica, which is acceptable because every key is rebuildable
from Postgres.

## Production rule

Production Redis must never be configured with an eviction policy that can drop
queue keys. Set `maxmemory-policy noeviction` and alert on memory pressure
instead. An evicted job key is a silently dropped shipment booking, which is the
one failure mode customers notice immediately.

## Validation

`pnpm check:redis` asserts the eviction policy and the absence of `FLUSHALL` in
any migration script. It runs in CI and will fail the build.
