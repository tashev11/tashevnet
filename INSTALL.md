# Installation

TashevNet needs Python 3.11 or newer and the system `ping` (plus `ip` on Linux). It does
not need administrator rights.

## macOS and Linux

```bash
git clone https://github.com/tashev11/tashevnet.git
cd tashevnet
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
tashevnet doctor
tashevnet run
```

Open http://127.0.0.1:8765. If the port is taken, change `app.port` in `config.yaml`.

## Windows

```powershell
git clone https://github.com/tashev11/tashevnet.git
cd tashevnet
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item config.example.yaml config.yaml
tashevnet doctor
tashevnet run
```

Windows support is new in 0.1.1 and not yet tested on a real machine.

## Start at login

- **macOS:** [packaging/macos/com.tashevnet.agent.plist.example](packaging/macos/com.tashevnet.agent.plist.example) has the steps in its header.
- **Linux:** [packaging/systemd/tashevnet.service](packaging/systemd/tashevnet.service) runs it as a dedicated user with history in `/var/lib/tashevnet`.
- **Windows:** [packaging/windows/README.md](packaging/windows/README.md) registers a Task Scheduler task.

`tashevnet run` stays alive through network outages and restarts its own background loops if one of them fails, and `/healthz` answers `503` if checks stop. Service managers can rely on both.

## Docker (Linux servers)

Docker is meant for watching a Linux server's own connection. On macOS and Windows,
Docker runs inside a virtual machine and cannot see your router or VPN: install
natively there.

```bash
cp config.example.yaml config.yaml     # must exist before the first start
docker compose up -d --build
```

The dashboard is published on the host's `127.0.0.1:8765` only. For Telegram, set
`telegram.enabled: true` in `config.yaml` and put the token and chat ID into a `.env`
file next to `docker-compose.yml` (see `.env.example`).

To watch the host's real interfaces and VPN on Linux, use host networking and keep the
dashboard on loopback:

```yaml
services:
  tashevnet:
    network_mode: host
    environment:
      TASHEVNET_HOST: 127.0.0.1
```

(With `network_mode: host`, remove the `ports:` section.)

## Updating

```bash
cd tashevnet
git pull
pip install -e .
```

History and settings are kept: the database lives in `~/.tashevnet/` (or wherever
`app.db_path` points) and `config.yaml` is not tracked by git.
