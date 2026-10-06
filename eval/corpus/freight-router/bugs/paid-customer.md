# Paid Customer

## Policy

Issues reported by a paying customer, tracked separately so they do not get lost
in the general backlog. Severity follows the same scale; the difference is that an
S1 here gets a written response to the customer regardless of fix timing.

## Billing / S1

A tenant that exceeds its quote-volume limit mid-cycle is throttled at the gateway
but still billed the metered component for the rejected quotes. The rejection and
the meter increment both happen, and only one of them should.

## Security / S1

Session tokens do not rotate on a password change, so a stolen token outlives the
credential it came from.
