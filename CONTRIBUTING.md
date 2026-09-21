# Contributing

Thanks for helping improve TashevNet.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make check        # ruff + pytest + compileall
```

The tests never touch the real network. `tests/conftest.py` provides a scriptable
`FakeNetwork` (flip `internet`, `icmp`, `icmp_spoofed`, `gateway_ping`… between checks to
stage an incident) and a fake Telegram API that can go offline. New behavior needs a test
in the same style: describe the situation, run a few checks, assert what the user would
see.

## Pull requests

- Keep changes focused and update the docs when settings or user-visible behavior change.
- Reasons produced by the classifier must stay free of numbers; the state tracker relies
  on identical reasons for a steady problem.
- Nothing may block the check loop: network calls to third parties go through a queue or a
  background task with a timeout.
- Never commit tokens, VPN credentials or private network inventories.

Useful areas: platform network discovery (especially Windows), VPN adapters,
packet-loss and jitter measurements, dashboard UX and new alert channels.
