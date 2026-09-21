# Security policy

## Supported versions

The latest release and current `main` receive security fixes during the MVP stage.

## Reporting

Please avoid publishing secrets, exploit details against real systems, or private network data in a public issue. Open a minimal issue asking for a private contact path if a report contains sensitive details.

## Operator safety

- Never commit Telegram tokens, VPN credentials or private keys.
- Keep the dashboard bound to `127.0.0.1` unless you intentionally put authentication and TLS in front of it.
- The configured VPN self-heal command executes with the privileges of the TashevNet process. Treat `config.yaml` as trusted code-level configuration.
- Prefer a dedicated low-privilege service account for unattended installations.
- Docker cannot always observe a host VPN interface on macOS/Windows; native installation is recommended for endpoint VPN monitoring.
