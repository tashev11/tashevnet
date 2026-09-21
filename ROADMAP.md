# Roadmap

## v0.1 — local MVP (done)
- [x] Router, Internet, DNS and HTTP checks
- [x] VPN watchdog and expected-IP leak check
- [x] Bounded speed sampling
- [x] SQLite flight recorder
- [x] Dashboard and JSON API
- [x] Telegram alerts and commands
- [x] Configurable VPN self-heal

## v0.1.1 — reliability (done)
- [x] Monitoring survives network outages; alerts are queued until delivery
- [x] Checks that proxy-type VPN clients cannot fake
- [x] Confirmed incidents instead of per-check alerts; outage durations
- [x] Hourly retention, strict configuration, working Docker image
- [x] Redesigned dashboard

## v0.2 — stronger diagnostics
- [ ] Rolling packet-loss and jitter windows
- [ ] Traceroute snapshots around incidents
- [ ] Wi-Fi signal and SSID telemetry
- [ ] Per-target service monitors
- [ ] Bandwidth baseline and anomaly detection
- [ ] Notification quiet hours
- [ ] Webhook, Discord and Slack outputs
- [ ] Windows verified on real machines

## v0.3 — desktop product
- [ ] macOS menu-bar app
- [ ] Windows tray app
- [ ] One-click installers and auto-start
- [ ] Native VPN adapters for WireGuard, Tailscale and OpenVPN
- [ ] Safe self-heal recipes
- [ ] Signed releases

## v0.4 — Cloud Watcher
- [ ] Heartbeat API
- [ ] Offline-device alerts
- [ ] Multi-device dashboard
- [ ] Team workspaces and roles
- [ ] Retention policies and reports
- [ ] Optional hosted plan

## Later
- [ ] ISP evidence report (HTML/PDF)
- [ ] Route-change correlation
- [ ] Fleet / office view
- [ ] Mobile companion
