<p align="center">
  <img src="docs/assets/logo.svg" width="180" alt="TashevNet">
</p>

<h1 align="center">TashevNet</h1>

<p align="center">
  <strong>Network flight recorder · VPN watchdog · self-healing connectivity monitor</strong>
</p>

<p align="center">
  <a href="https://github.com/tashev11/tashevnet/actions"><img alt="CI" src="https://github.com/tashev11/tashevnet/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Status" src="https://img.shields.io/badge/status-MVP-orange">
</p>

TashevNet is a cross-platform local agent that continuously checks the whole connectivity chain — **device → router → ISP → DNS → Internet → VPN → target services** — records what happened, explains the likely cause and can try to recover automatically.

## Why

Most tools answer only one question: “is this host alive?” TashevNet correlates several signals and answers a more useful question:

> **What broke, when did it break, how long did it last, did VPN leak traffic, and did recovery work?**

## MVP features

- Internet health checks with multiple independent targets.
- DNS, TCP, HTTP and ICMP probes.
- Latency / degradation detection.
- VPN interface watchdog.
- Optional expected VPN public-IP check.
- VPN leak detection.
- Configurable VPN self-heal command.
- SQLite incident history (“network flight recorder”).
- Local FastAPI dashboard and JSON API.
- Telegram notifications.
- Telegram commands: `/status`, `/vpn`, `/events`, `/ping`.
- Docker image and Compose example.
- macOS / Windows / Linux architecture.
- CI tests and Ruff linting.

## Quick start

```bash
git clone https://github.com/tashev11/tashevnet.git
cd tashevnet
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml
tashevnet run
```

Open **http://127.0.0.1:8765**.

### Telegram in 60 seconds

1. Create a bot with **@BotFather**.
2. Send any message to your new bot.
3. Set two environment variables:

```bash
export TASHEVNET_TELEGRAM_BOT_TOKEN="123456:ABC..."
export TASHEVNET_TELEGRAM_CHAT_ID="123456789"
```

4. In `config.yaml` set `telegram.enabled: true`.
5. Restart TashevNet and send `/status` to the bot.

Full guide: [docs/TELEGRAM.md](docs/TELEGRAM.md).

## What TashevNet can diagnose

| Situation | Interpretation |
|---|---|
| Router unavailable | local network / gateway issue |
| Router OK, Internet probes fail | ISP / WAN outage |
| IP connectivity OK, DNS fails | DNS incident |
| DNS OK, HTTP fails | HTTP / service path problem |
| Internet OK, VPN interface missing | VPN disconnected |
| VPN interface exists, public IP unexpected | possible VPN leak |
| Latency exceeds threshold | degraded connection |
| Everything returns after incident | recovery event |

## Architecture

```mermaid
flowchart LR
  A[TashevNet Agent] --> R[Router probe]
  A --> I[Internet probes]
  A --> D[DNS probes]
  A --> H[HTTP probes]
  A --> V[VPN watchdog]
  A --> DB[(SQLite flight recorder)]
  A --> API[FastAPI dashboard]
  A --> TG[Telegram Bot]
  A --> SH[Self-heal runner]
```

The local agent is intentionally useful without a cloud account. A future optional Cloud Watcher will receive heartbeats so a remote service can detect a machine that lost Internet and therefore cannot notify Telegram itself.

## Configuration

Copy `config.example.yaml` to `config.yaml`. Secrets should be supplied via environment variables, never committed.

Important settings:

- `monitor.interval_seconds`
- `monitor.degraded_latency_ms`
- `monitor.gateway`
- `monitor.vpn_required`
- `monitor.vpn_expected_ip`
- `monitor.self_heal_vpn_command`
- `telegram.enabled`

## Roadmap

See [ROADMAP.md](ROADMAP.md). Near-term goals include packet-loss windows, native speed tests, route snapshots, auto-discovery of the default gateway, system tray apps, signed installers and the optional Cloud Watcher.

## Security

TashevNet does not need root privileges for normal monitoring. A self-heal command runs with the permissions of the TashevNet process, so treat it as trusted configuration. See [SECURITY.md](SECURITY.md).

## Contributing

Issues and pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © Rinat Tashev
