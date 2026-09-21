# Current state

Updated: 2026-09-21

## Completed
- Public GitHub repository created: `tashev11/tashevnet`.
- Core WAN/DNS/HTTP/physical-gateway probes.
- macOS physical gateway detection behind a full-tunnel VPN.
- VPN route/interface watchdog and expected public-IP leak check.
- VPN self-heal command with cooldown.
- Bounded speed sampling isolated from the primary health loop.
- SQLite flight recorder with throttled snapshots and retention.
- FastAPI dashboard/API.
- Telegram notifications, authorized commands and `telegram-id` helper.
- Docker, macOS launchd, Linux systemd and Windows auto-start examples.
- Ruff + pytest tests and GitHub Actions workflow.
- Initial GitHub issues for v0.2/v0.3.
- Live macOS diagnostic validated: Internet UP, gateway and VPN route detected.
- Live FastAPI validation on temporary port: `/healthz`, `/api/status` and dashboard HTTP 200.
- Local checks: Ruff passed; 7 pytest tests passed.

## Known environment note
- GitHub Actions runner jobs currently do not start because the GitHub account is locked for a billing issue. The workflow itself is committed; local verification is green.

## Next
1. Publish/tag v0.1.0.
2. Connect a real Telegram bot token/chat ID when available.
3. Implement rolling packet loss, jitter and incident duration (Issue #1).
4. Design Cloud Watcher heartbeat/offline alerts (Issue #2).
5. Add provider-aware VPN adapters (Issue #3).
