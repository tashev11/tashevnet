# Contributing

Thanks for helping improve TashevNet.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest
```

## Pull requests

Keep changes focused, add tests for behavior changes, do not commit secrets, and update documentation when configuration or user-facing behavior changes.

Useful contribution areas include platform-specific network discovery, VPN adapters, packet-loss/jitter calculations, dashboard UX and notification integrations.
