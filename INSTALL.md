# Installation

## macOS / Linux

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

The dashboard binds to `127.0.0.1:8765` by default. Change the port in `config.yaml` if that port is already occupied.

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

## Docker

Docker is convenient for server/WAN monitoring, but native installation is recommended when TashevNet must inspect the host VPN interface on macOS or Windows.

```bash
cp config.example.yaml config.yaml
docker compose up -d --build
```

## Telegram

See [docs/TELEGRAM.md](docs/TELEGRAM.md).

## Auto-start

Examples are available in:
- `packaging/macos/`
- `packaging/systemd/`
- `packaging/windows/`

Review paths and environment variables before enabling any unattended service.
