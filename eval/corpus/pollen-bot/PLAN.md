# Pollen Bot — Implementation Plan

## Context

A Discord bot that posts a daily pollen forecast and answers ad-hoc queries for a
handful of gardening servers. Small scope on purpose; the interesting part is the
caching, not the bot framework.

## Tech stack

discord.py, aiosqlite for local state, httpx for the upstream pollen API. No ORM —
the schema is four tables and raw SQL is clearer than a mapping layer here.

## Database schema

```sql
CREATE TABLE subscriptions (
  guild_id   INTEGER NOT NULL,
  channel_id INTEGER NOT NULL,
  station    TEXT    NOT NULL,
  hour_utc   INTEGER NOT NULL,
  PRIMARY KEY (guild_id, channel_id)
);
```

## Upstream API caching

The pollen API bills per request and updates once a day per station, so responses
are cached in SQLite keyed by `(station, date)`. The cache is checked before every
command and the daily job warms it for every subscribed station in one pass.

Station IDs are stable across seasons, so the station list is fetched once at
startup rather than per request. The forecast payload itself is not stable and
must not be cached beyond the day it describes.

## Rate limits

Discord's rate limit is per route and per guild. The daily broadcast fans out to
every subscribed channel, so it posts through a semaphore of four rather than all
at once, which keeps the bot well under the bucket even with a few hundred guilds.

## Slash command conventions

Every command is a slash command; there are no prefix commands. Responses are
ephemeral unless the user explicitly asks to post publicly, because the gardening
servers are chatty and nobody wants another bot filling the channel.
