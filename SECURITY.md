# Security policy

## Supported versions

The latest release and `main` receive security fixes.

## Reporting a vulnerability

Please do not publish exploit details, tokens or private network data in a public issue.
Use GitHub's **Report a vulnerability** button on the Security tab if it is available;
otherwise open a short issue asking for a private contact and leave the details out.

## Running TashevNet safely

- **Dashboard.** It has no login and shows your public IP, router and VPN state. It listens
  on `127.0.0.1` by default; do not expose it to a network without authentication and
  TLS in front. The Docker setup publishes it on the host's loopback only.
- **Check now.** `POST /api/check` requires the `X-TashevNet: check` header, so other
  websites open in your browser cannot trigger checks or self-heal runs.
- **Self-heal command.** It runs with TashevNet's own permissions, is stopped after
  `self_heal_timeout_seconds`, and its output goes to your Telegram chat. Treat
  `config.yaml` as trusted, code-level configuration.
- **Secrets.** Keep the Telegram token in environment variables or a secret store. It is
  never written to logs: request URLs are not logged, and errors are scrubbed of the token.
- **Service account.** For unattended installs, run TashevNet as a dedicated unprivileged
  user, as the systemd unit in `packaging/` does.
- **Docker** cannot observe a host VPN on macOS or Windows; install natively there.
