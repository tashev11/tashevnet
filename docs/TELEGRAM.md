# Telegram

TashevNet sends alerts to one Telegram chat and answers commands from that chat only.

## Setup

1. Open **@BotFather**, run `/newbot`, choose a name and copy the token.
2. Send any message to the new bot (or add it to a group and write there).
3. Put the token into your environment and look up the chat ID. Stop `tashevnet run`
   first if it is already polling the bot:

   ```bash
   export TASHEVNET_TELEGRAM_BOT_TOKEN="123456789:AA..."
   tashevnet telegram-id
   export TASHEVNET_TELEGRAM_CHAT_ID="123456789"
   ```

4. Enable Telegram in `config.yaml`:

   ```yaml
   telegram:
     enabled: true
     polling: true   # answer commands; false = alerts only
   ```

5. Run `tashevnet doctor`, then start `tashevnet run` from the same shell.

For a service that starts at login, put the two variables where the service manager can
read them: `EnvironmentVariables` in the launchd plist, the `EnvironmentFile` of the
systemd unit, or `.env` for docker compose.

## Alerts

An alert is sent when the confirmed state changes, never on every check:

- A problem becomes an incident once it shows up in 2 of the last 3 checks
  (`monitor.alert_after_checks`).
- The incident ends after 3 clean checks in a row (`monitor.recover_after_checks`), and the
  recovery message says how long it lasted.
- While the computer is offline, alerts wait in a queue (up to 50) and are delivered in
  order once Telegram is reachable again. That is also why an outage alert can arrive late:
  a computer without Internet cannot reach Telegram.

```text
🔴 TashevNet · DOWN
Internet/WAN probes are unreachable
Public IP: unknown
VPN: ON · utun4
Gateway: 192.168.1.1
Since 21.09 21:54:10 MSK

🟢 TashevNet · back to UP after 3 min 12 s
Was DOWN: Internet/WAN probes are unreachable
Public IP: 203.0.113.24
VPN: ON · utun4
Gateway: 192.168.1.1
Line latency: 41 ms
Since 21.09 21:57:22 MSK
```

Times are shown in the computer's time zone.

## Commands

| Command | Answer |
|---|---|
| `/status` | the latest check: state, public IP, VPN, router, latency, speed |
| `/vpn` | VPN interface, whether it carries Internet traffic, public IP |
| `/events` | the last 8 state changes with outage durations |
| `/ping` | proves the agent and the bot loop are alive |
| `/help` | the command list |

Messages from other chats, stickers and photos are ignored, and so are commands older
than two minutes, which the bot could not answer in time.

## Security

- Only the configured chat ID is served. In a group, every member of the group can use
  the commands.
- The token never appears in TashevNet's logs or error messages. Keep it in environment
  variables or a secret store, not in a committed file, and revoke it in @BotFather right
  away if it leaks.
