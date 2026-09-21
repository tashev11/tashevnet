from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

import httpx

from . import __version__
from .config import AppConfig, ConfigError, load_config
from .probes import short_error, system_name

CONFIG_HELP = "path to config.yaml (default: $TASHEVNET_CONFIG, then ./config.yaml)"
TOKEN_SHAPE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


def _setup_logging(level: int) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every request URL at INFO, and Telegram URLs contain the bot token.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def _once(config: AppConfig) -> int:
    from .monitor import MonitorEngine

    engine = MonitorEngine(config, store=None)
    try:
        snapshot = await engine.collect()
    finally:
        await engine.close()
    print(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False))
    return 2 if snapshot.health.value == "DOWN" else 0


async def _telegram_id(config: AppConfig) -> int:
    token = config.telegram.bot_token
    if not token:
        print("Set TASHEVNET_TELEGRAM_BOT_TOKEN (or telegram.bot_token) first.", file=sys.stderr)
        return 2
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getUpdates")
    except httpx.HTTPError as exc:
        print(f"Could not reach api.telegram.org: {short_error(exc)}", file=sys.stderr)
        return 2
    if response.status_code == 401:
        print("Telegram rejected the bot token (HTTP 401). Copy it again from @BotFather.",
              file=sys.stderr)
        return 2
    if response.status_code == 409:
        print("The bot has a webhook or another program is reading its updates "
              "(stop `tashevnet run` first).", file=sys.stderr)
        return 2
    if not response.is_success:
        print(f"Telegram answered HTTP {response.status_code}.", file=sys.stderr)
        return 2
    rows: list[tuple[str, str]] = []
    for update in response.json().get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            continue
        label = chat.get("title") or chat.get("username") or chat.get("first_name") or "chat"
        if (chat_id, str(label)) not in rows:
            rows.append((chat_id, str(label)))
    if not rows:
        print("No chats found. Send any message to the bot, then run this command again.")
        return 1
    print("Chats that recently wrote to the bot:")
    for chat_id, label in rows:
        print(f"  {chat_id}  {label}")
    return 0


def _writable_dir(path: Path) -> bool:
    for candidate in [path, *path.parents]:
        if candidate.exists():
            return os.access(candidate, os.W_OK)
    return False


def _doctor(config: AppConfig) -> int:
    monitor, telegram = config.monitor, config.telegram
    problems: list[str] = []
    notes: list[str] = []

    def row(label: str, value: str) -> None:
        print(f"  {label:<14}{value}")

    print(f"TashevNet {__version__} — configuration check\n")
    row("Config", config.config_path or "not found, using built-in defaults "
                                       "(cp config.example.yaml config.yaml)")
    db_dir = Path(config.db_path).parent
    row("Database", config.db_path)
    if not _writable_dir(db_dir):
        problems.append(f"Cannot write the database directory {db_dir}.")
    row("Dashboard", f"http://{config.host}:{config.port}")
    if config.host not in {"127.0.0.1", "localhost", "::1"}:
        notes.append(
            f"The dashboard listens on {config.host}: anyone on that network can open it "
            "(it has no login). Keep 127.0.0.1 unless it sits behind auth."
        )
    row("Checks", f"every {monitor.interval_seconds} s; incident after "
                  f"{monitor.alert_after_checks} bad of the last "
                  f"{max(monitor.alert_after_checks, monitor.recover_after_checks)} checks")
    row("Speed sample", f"every {config.speed.interval_minutes} min"
        if config.speed.enabled else "off")

    row("VPN required", "yes" if monitor.vpn_required else "no")
    if monitor.vpn_required and not monitor.vpn_interface_patterns:
        problems.append("VPN is required but monitor.vpn_interface_patterns is empty.")
    if monitor.vpn_expected_ip:
        try:
            ipaddress.ip_address(monitor.vpn_expected_ip)
        except ValueError:
            problems.append(f"monitor.vpn_expected_ip is not an IP address: "
                            f"{monitor.vpn_expected_ip!r}")
        if not monitor.vpn_required:
            notes.append("vpn_expected_ip is set but vpn_required is false: the leak "
                         "check only runs when vpn_required is true.")
    row("Self-heal", "configured" if monitor.self_heal_vpn_command else "off")
    if monitor.self_heal_vpn_command and not monitor.vpn_required:
        notes.append("self_heal_vpn_command never runs unless vpn_required is true.")

    if not telegram.enabled:
        row("Telegram", "off")
    else:
        missing = [name for name, value in (("bot token", telegram.bot_token),
                                            ("chat id", telegram.chat_id)) if not value]
        row("Telegram", "ready" if not missing else f"missing {' and '.join(missing)}")
        if missing:
            problems.append("Telegram is enabled but the " + " and ".join(missing)
                            + " is missing (see docs/TELEGRAM.md).")
        elif not TOKEN_SHAPE.match(telegram.bot_token):
            notes.append("The bot token does not look like 123456789:AA… — check for typos.")

    tools = ["ping"] + {"darwin": ["route", "netstat", "ifconfig"], "linux": ["ip"],
                        "windows": ["powershell"]}.get(system_name(), [])
    missing_tools = [tool for tool in tools if shutil.which(tool) is None]
    row("Local tools", "all found" if not missing_tools else f"missing {', '.join(missing_tools)}")
    if "ping" in missing_tools:
        notes.append("ping is missing: ICMP checks are off, HTTPS checks still work.")
    if [tool for tool in missing_tools if tool != "ping"]:
        notes.append("Gateway and VPN detection need the missing tools above.")

    for note in notes:
        print(f"\nNote: {note}")
    for problem in problems:
        print(f"\nProblem: {problem}")
    if problems:
        return 1
    print("\nConfiguration looks good. Run `tashevnet once` for a live check.")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tashevnet", description="TashevNet — network flight recorder and VPN watchdog"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help=CONFIG_HELP)
    # Accept --config after the command too: `tashevnet run --config x.yaml`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help=CONFIG_HELP, default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    sub.add_parser("run", parents=[common], help="run the monitor and the dashboard")
    sub.add_parser("once", parents=[common], help="run one check and print it as JSON")
    sub.add_parser("doctor", parents=[common], help="check the configuration and local tools")
    sub.add_parser("telegram-id", parents=[common],
                   help="list chats that recently wrote to your bot")
    args = parser.parse_args(argv)

    _setup_logging(logging.INFO if args.command == "run" else logging.WARNING)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    if args.command == "once":
        raise SystemExit(asyncio.run(_once(config)))
    if args.command == "doctor":
        raise SystemExit(_doctor(config))
    if args.command == "telegram-id":
        raise SystemExit(asyncio.run(_telegram_id(config)))

    import uvicorn

    from .app import create_app

    logging.getLogger("tashevnet").info(
        "TashevNet %s · dashboard http://%s:%s · config %s",
        __version__, config.host, config.port, config.config_path or "built-in defaults",
    )
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
