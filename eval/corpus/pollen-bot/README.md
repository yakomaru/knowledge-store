# pollen-bot

A Discord bot posting daily pollen forecasts.

## Status

Running in three servers. Forecast and subscription commands are complete; the
historical-trend chart is not started.

## Setup

See `DEPLOY.md`. Short version: venv, `.env` with a Discord token and a pollen API
key, then `python -m pollen_bot`.

## Test

`pytest` with a fake upstream. The tests never hit the real pollen API — the
fixture serves recorded payloads, so the suite is offline and deterministic.

## Lint

`ruff check` and `ruff format --check`. Both run in CI.
