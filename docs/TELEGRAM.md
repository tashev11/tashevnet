# Telegram integration

TashevNet can both push alerts and answer commands from one authorized Telegram chat.

## Setup

1. Open **@BotFather** in Telegram.
2. Run `/newbot`, choose a name and username, and copy the bot token.
3. Send any message to the new bot.
4. Export the token locally:

```bash
export TASHEVNET_TELEGRAM_BOT_TOKEN="123456:ABC..."
```

5. Discover your chat ID:

```bash
tashevnet telegram-id
```

6. Export the returned ID:

```bash
export TASHEVNET_TELEGRAM_CHAT_ID="123456789"
```

7. Enable Telegram in `config.yaml`:

```yaml
telegram:
  enabled: true
  polling: true
```

8. Run `tashevnet doctor`, then restart `tashevnet run`.

## Commands

- `/status` — current Internet/VPN/public-IP/speed state.
- `/vpn` — VPN interface and public IP.
- `/events` — recent state-changing incidents.
- `/ping` — confirms that the agent and bot loop are alive.
- `/help` — command list.

## Alerts

The bot sends a message only when health/reason changes, rather than on every probe cycle. This prevents notification spam.

Typical alert:

```text
🔴 TashevNet · DOWN
VPN is required but no active VPN interface was detected
Public IP: 198.51.100.7
VPN: OFF
Gateway: 192.168.1.1
2026-09-21T18:40:12+00:00
```

## Security

The bot ignores commands from every chat except the configured `CHAT_ID`. Keep the bot token in an environment variable or secret manager and rotate it immediately if it is exposed.
