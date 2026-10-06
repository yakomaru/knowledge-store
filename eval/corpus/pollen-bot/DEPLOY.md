# Deployment & Setup

## 1. Prerequisites

A small always-on host, Python 3.12, and a Discord application with the bot scope
and the message-content intent enabled.

## 2. Install

```bash
git clone <repo> && cd pollen-bot
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env     # fill in DISCORD_TOKEN and POLLEN_API_KEY
```

## 3. Create the Discord bot

In the developer portal create the application, add a bot user, enable the message
content intent, and invite it with `applications.commands` plus `bot`. Without the
message content intent the pollen alerts post fine but the text commands are
silently ignored.

## 4. Run as a service

```ini
[Unit]
Description=pollen-bot
After=network-online.target

[Service]
ExecStart=/opt/pollen-bot/.venv/bin/python -m pollen_bot
Restart=on-failure
RestartSec=5
User=pollen
```

Enable with `systemctl enable --now pollen-bot`. The unit sends SIGTERM on stop and
the bot closes the gateway connection cleanly, so a restart does not leave a ghost
session holding the shard.

## 5. Verifying the deploy

Watch for `connected, N guilds` in the journal and confirm the slash commands
appear in your server. Command registration is global and can take an hour to
propagate; register to a single guild during development to avoid the wait.
