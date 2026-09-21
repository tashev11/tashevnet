from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx
import uvicorn

from .app import create_app
from .config import load_config
from .monitor import MonitorEngine
from .storage import Store


async def _once(config_path: str | None) -> int:
    config = load_config(config_path)
    store = Store(config.db_path)
    await store.init()
    engine = MonitorEngine(config, store)
    try:
        snapshot = await engine.tick()
        print(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False))
        return 0 if snapshot.health.value != "DOWN" else 2
    finally:
        await engine.telegram.close()


async def _telegram_id(config_path: str | None) -> int:
    config = load_config(config_path)
    token = config.telegram.bot_token or os.getenv("TASHEVNET_TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("Set TASHEVNET_TELEGRAM_BOT_TOKEN first.", file=sys.stderr)
        return 2
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    rows: list[tuple[str, str]] = []
    for update in data.get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            continue
        label = chat.get("title") or chat.get("username") or chat.get("first_name") or "chat"
        item = (chat_id, str(label))
        if item not in rows:
            rows.append(item)
    if not rows:
        print("No chats found. Send a message to the bot, then run this command again.")
        return 1
    print("Available Telegram chats:")
    for chat_id, label in rows:
        print(f"  {chat_id}  {label}")
    return 0


def _doctor(config_path: str | None) -> int:
    config = load_config(config_path)
    problems: list[str] = []
    if config.telegram.enabled and not config.telegram.bot_token:
        problems.append("Telegram is enabled but BOT_TOKEN is missing.")
    if config.telegram.enabled and not config.telegram.chat_id:
        problems.append("Telegram is enabled but CHAT_ID is missing.")
    if config.monitor.vpn_required and not config.monitor.vpn_interface_patterns:
        problems.append("VPN is required but no interface patterns are configured.")
    print(f"Database: {config.db_path}")
    print(f"Monitor interval: {config.monitor.interval_seconds}s")
    print(f"Speed test: {'enabled' if config.speed.enabled else 'disabled'}")
    print(f"VPN required: {config.monitor.vpn_required}")
    print(f"Telegram: {'ready' if config.telegram.enabled and not problems else 'not ready'}")
    if problems:
        for problem in problems:
            print(f"WARNING: {problem}")
        return 1
    print("Configuration looks good.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="tashevnet", description="TashevNet network watchdog")
    parser.add_argument("--config", help="Path to config YAML", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run monitor and dashboard")
    sub.add_parser("once", help="Run one diagnostic cycle and print JSON")
    sub.add_parser("doctor", help="Validate local configuration")
    sub.add_parser("telegram-id", help="Discover Telegram chat IDs from recent bot updates")
    args = parser.parse_args()

    if args.command == "once":
        raise SystemExit(asyncio.run(_once(args.config)))
    if args.command == "doctor":
        raise SystemExit(_doctor(args.config))
    if args.command == "telegram-id":
        raise SystemExit(asyncio.run(_telegram_id(args.config)))

    config = load_config(args.config)
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
