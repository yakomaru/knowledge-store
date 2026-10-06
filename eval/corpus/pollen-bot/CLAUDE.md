# Pollen Bot

## Before committing

Run `ruff check`, `ruff format`, and `pytest`. The suite is offline and fast;
there is no reason to skip it.

## Git workflow

Small commits, present-tense subjects. Never commit `.env` or the SQLite file.

## Discord conventions

Slash commands only, no prefix commands. Responses are ephemeral by default. New
commands register globally and can take an hour to appear — register to a single
test guild while developing.

## Deploy

Deploys run over systemd on the host; see `DEPLOY.md` for the unit file and the
first-time setup. Restarting is safe because the gateway connection closes
cleanly on SIGTERM.

## Caching

Forecast responses are cached per station per day. Never cache a forecast beyond
the day it describes.
