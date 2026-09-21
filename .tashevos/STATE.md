# Current state

Updated: 2026-09-21

## Completed
- v0.1.0 published: router, Internet, DNS and HTTP checks, VPN watchdog, SQLite history,
  dashboard, Telegram, self-heal, packaging examples.
- v0.1.1 reliability release:
  - check loop survives outages; Telegram alerts are queued and delivered after recovery;
  - canary 203.0.113.1 detects proxy-type VPN clients that answer TCP/ICMP locally;
    Internet checks count trusted ping or real HTTPS answers only;
  - state tracker: incident after 2 of 3 bad checks, recovery after 3 clean checks,
    outage durations in events and alerts;
  - hourly retention, strict config validation, heal timeout, `/healthz` 503 when stale;
  - Docker image fixed (loopback-only publish, ping/ip, non-root, health check);
  - redesigned dashboard, new logo, README in English and Russian.
- Verified on macOS (Python 3.12 and 3.14): ruff clean, 84 tests, live checks behind a
  proxy-type VPN.

## Not verified
- Docker image and systemd unit on a real Linux server.
- Windows code paths (PowerShell route/adapter lookup, localized ping output).

## Next
1. Run the Docker image and the systemd unit on a Linux host.
2. Test on Windows.
3. Rolling packet loss and jitter (Issue #1).
4. Cloud Watcher heartbeats for real offline alerts (Issue #2).
5. Provider-aware VPN adapters (Issue #3).
