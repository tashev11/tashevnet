# Changelog

All notable changes to TashevNet are documented here.

## 0.1.1 — 2026-09-21

A reliability release: 0.1.0 could stop monitoring during the very outages it was meant to
record. Upgrading is recommended.

### Fixed
- **Monitoring no longer stops when the Internet drops.** With Telegram enabled, a failed
  alert used to crash the check loop at the first outage, leaving the dashboard stuck on
  DOWN while `/healthz` reported OK. Alerts are now queued and delivered after recovery,
  and background loops restart themselves if they fail.
- **Proxy-type VPN clients can no longer fake a working Internet.** TUN-mode VPN apps
  accept any TCP connection locally, so 0.1.0 reported "Internet UP" even with a dead
  tunnel. A canary address now detects local answers, and the Internet check counts only
  ping replies that can be trusted or real HTTPS answers.
- **No more alert storms.** High latency produced a new event and a Telegram message on
  every 5-second check because the latency value was part of the reason. Reasons are now
  stable, and incidents need 2 bad checks out of 3 to start and 3 clean checks to end.
- A router that ignores ping no longer marks a working connection as DOWN.
- Parallel checks ("Check now" during a scheduled check) no longer send duplicate alerts.
- A hanging self-heal command no longer freezes monitoring: it runs in the background and
  is stopped, with its child processes, after `self_heal_timeout_seconds`.
- History older than `retention_days` is pruned every hour, not only at start-up.
- A missing `--config` file, a directory in its place, a misspelled key or a wrong value
  type is now a clear error instead of silently running with defaults.
- An empty `TASHEVNET_TELEGRAM_*` variable (as docker compose passes) no longer wipes the
  token set in `config.yaml`.
- Docker: the dashboard was unreachable because it listened on the container's loopback;
  the image now includes `ping` and `ip`, runs as an unprivileged user, has a health check,
  and compose publishes the port on the host's `127.0.0.1` only.
- Telegram: stickers and photos no longer break command handling, commands sent while the
  agent was offline are skipped, times are shown in local time, and the bot token no
  longer appears in `telegram-id` errors.
- Starting TashevNet or running `tashevnet once` no longer records a fake incident or
  sends a message; `once` writes nothing at all.
- The speed sample no longer counts connection setup as transfer time.
- The router's latency no longer shows as the line latency during an outage.
- A VPN that drops with a kill switch is reported as a VPN problem, not an ISP outage.
- Windows: ping output is read in any language, "Destination host unreachable" is no
  longer a success, and VPN adapters are matched by description too (untested).
- SQLite connections are closed explicitly.

### Added
- A redesigned dashboard: the connection path from this computer to websites with the
  broken link highlighted, incident history with durations, light and dark themes
  (`?theme=dark`), phone layout and a hidden-by-default public IP.
- Recovery alerts and events carry the outage duration.
- `/healthz` returns `503` when checks have stopped.
- Settings `alert_after_checks`, `recover_after_checks`, `public_ip_interval_seconds`,
  `self_heal_timeout_seconds`; environment overrides `TASHEVNET_HOST`, `TASHEVNET_PORT`,
  `TASHEVNET_DB_PATH`.
- `tashevnet --version`; `--config` also works after the command.
- `tashevnet doctor` checks the database folder, the Telegram token shape and local tools.
- 84 tests (7 in 0.1.0).

### Changed
- The public IP is refreshed every 30 seconds and on VPN changes instead of every check,
  and HTTP checks reuse their connection: far less traffic.
- `POST /api/check` requires the `X-TashevNet: check` header.
- The CI workflow runs on demand.
- New logo that reads on light and dark backgrounds.

## 0.1.0 — 2026-09-21

Initial public MVP: WAN, router, DNS, HTTP and ICMP diagnostics; VPN interface watchdog
with expected-IP leak detection; VPN self-heal command with cooldown; periodic speed
sample; SQLite history; FastAPI dashboard and JSON API; Telegram alerts and commands;
`telegram-id` and `doctor`; Docker and auto-start examples.
