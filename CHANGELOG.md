# Changelog

All notable changes to TashevNet are documented here.

## 0.1.0 — 2026-09-21

Initial public MVP.

### Added
- Cross-platform WAN, gateway, DNS, HTTP and ICMP diagnostics.
- VPN route/interface watchdog and expected public-IP leak detection.
- Configurable VPN self-heal with cooldown.
- Bounded periodic download/upload speed sampling.
- SQLite network flight recorder with retention.
- Responsive FastAPI dashboard and JSON API.
- Telegram incident notifications and commands.
- `tashevnet telegram-id` and `tashevnet doctor`.
- Docker/Compose and auto-start examples for macOS, Linux and Windows.
- TashevOS continuity files, contribution templates, tests and CI workflow.

### Fixed during live validation
- Slow HTTP responses no longer create false line-latency alerts.
- macOS physical gateway is discovered even while a full-tunnel VPN owns the default route.
- macOS VPN detection prefers the actual routed `utun` interface.
- Speed sampling no longer blocks the primary health-check loop.
- Snapshot persistence is throttled to prevent unbounded 24/7 database growth.
