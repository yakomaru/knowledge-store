# Project: Multi-Carrier Freight Quoting & Routing Platform

## What this is

A quoting and routing layer that sits between a shipper's order flow and several
carrier APIs, normalising rates and transit estimates so the shipper can pick on
price and service level rather than on whichever integration happens to work.

## Strategic positioning

The incumbents are either carrier-specific portals or heavyweight TMS suites. The
wedge is the middle: shippers with enough volume to care about rate shopping but
not enough to run a TMS implementation project.

## Multi-tenancy and the data model

Every tenant-scoped table carries `tenant_id` and is protected by a row-level
security policy keyed to the session role. Application code never filters by
tenant explicitly — if a query returns another tenant's rows, the policy is wrong
and that is a release blocker rather than a bug to patch at the call site.

Shipments, quotes, and service areas are tenant-scoped. Carrier metadata and the
geocoding cache are global, because they contain nothing tenant-specific and the
duplication would be wasteful.

## The carrier interface

Every carrier adapter implements the same four calls: `quote`, `book`,
`track`, and `cancel`. The interface is deliberately narrow — anything
carrier-specific is expressed as capability flags rather than as extra methods,
so the router can ask what a carrier supports without knowing which carrier it is.

```ts
interface CarrierAdapter {
  readonly slug: string;
  readonly capabilities: CarrierCapabilities;
  quote(req: QuoteRequest): Promise<QuoteResult>;
  book(req: BookRequest): Promise<BookResult>;
  track(id: ShipmentId): Promise<TrackResult>;
  cancel(id: ShipmentId): Promise<void>;
}
```

Rate limits are the hard part. Each carrier publishes a different budget, some
per-account and some per-endpoint, and exceeding one gets the whole account
throttled rather than the single request rejected. The runtime holds a shared
token bucket in Redis per carrier account, and adapters wait on it rather than
retrying blindly.

## Tech stack

Postgres with PostGIS for service areas, Redis for rate limits and the job queue,
Fastify for the HTTP surface, React with Vite for the operator console. Drizzle
over Prisma for the database layer, because the RLS-aware queries were far easier
to express and the generated SQL stays readable.

## Billing and provisioning

Per-seat pricing with a metered component on booked shipments. Provisioning
creates the tenant, its RLS role, and a sandbox carrier account in one
transaction, so a half-provisioned tenant cannot exist.

## Pricing and limits

Three tiers. The quote-volume limit is enforced at the gateway rather than in
billing, because a tenant that blows through its limit should get a clear error
rather than a surprise invoice.
