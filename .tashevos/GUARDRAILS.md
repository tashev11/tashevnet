# Guardrails

- Local-first: cloud services must remain optional.
- Monitoring must stay lightweight; never run large speed tests every probe cycle.
- Do not hide network failures by treating a single successful probe as proof that everything works.
- Telegram must authorize commands by configured chat ID.
- Self-heal commands must be explicitly configured by the operator.
- Never log or commit secrets.
- Changes must keep tests and Ruff green before release.
