# Webhook Replay Runbook

## Scope

Covers replaying carrier status webhooks after an outage window where the gateway
was down and carriers got a non-2xx response.

## Before replaying

Confirm the outage window from the gateway access log, and confirm the carrier
actually retries — some do not, and for those the only recovery is a full
reconciliation poll rather than a replay.

## Replay steps

Run `pnpm webhook:replay --from <iso> --to <iso> --carrier <slug>`. The script
reads the dead-letter table, re-posts each payload to the live handler, and marks
rows replayed as it goes so a crash mid-run is resumable.

## Verification

Compare shipment status counts against the carrier's own report for the window.
A gap of more than a handful of shipments means the replay missed a page; re-run
with a narrower window rather than replaying the whole range twice.

## Idempotency

Replays are safe because the status handler keys on `(carrier, shipment_id,
status, occurred_at)`. Replaying the same payload twice is a no-op, which is why
replay is preferred over manual status edits.
