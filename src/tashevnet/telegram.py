from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .config import TelegramConfig
from .models import Snapshot

StatusProvider = Callable[[], dict[str, Any]]
EventsProvider = Callable[[int], Awaitable[list[dict[str, Any]]]]


def format_snapshot(snapshot: Snapshot) -> str:
    icon = {"UP": "🟢", "DEGRADED": "🟡", "DOWN": "🔴", "UNKNOWN": "⚪"}.get(
        snapshot.health.value, "⚪"
    )
    lines = [
        f"{icon} TashevNet · {snapshot.health.value}",
        snapshot.reason,
        f"Public IP: {snapshot.public_ip or 'unknown'}",
        f"VPN: {'ON' if snapshot.vpn_connected else 'OFF'}"
        + (f" · {snapshot.vpn_interface}" if snapshot.vpn_interface else ""),
    ]
    if snapshot.gateway:
        lines.append(f"Gateway: {snapshot.gateway}")
    if snapshot.speed and snapshot.speed.download_mbps is not None:
        lines.append(
            f"Speed: ↓ {snapshot.speed.download_mbps:.1f} Mbps · "
            f"↑ {snapshot.speed.upload_mbps or 0:.1f} Mbps"
        )
    lines.append(snapshot.timestamp)
    return "\n".join(lines)


class TelegramBot:
    def __init__(
        self,
        config: TelegramConfig,
        status_provider: StatusProvider,
        events_provider: EventsProvider,
    ) -> None:
        self.config = config
        self.status_provider = status_provider
        self.events_provider = events_provider
        self.offset = 0
        self._client = httpx.AsyncClient(timeout=15.0)

    @property
    def ready(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token and self.config.chat_id)

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.config.bot_token}/{method}"

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, text: str) -> bool:
        if not self.ready:
            return False
        response = await self._client.post(
            self._url("sendMessage"),
            json={"chat_id": self.config.chat_id, "text": text, "disable_web_page_preview": True},
        )
        return response.is_success

    async def notify_snapshot(self, snapshot: Snapshot) -> bool:
        return await self.send(format_snapshot(snapshot))

    async def _command_text(self, command: str) -> str:
        status = self.status_provider()
        snapshot = status.get("snapshot")
        if command in {"/start", "/help"}:
            return (
                "TashevNet bot\n"
                "/status — current connection\n"
                "/vpn — VPN state\n"
                "/events — last incidents\n"
                "/ping — bot/agent heartbeat"
            )
        if command == "/ping":
            return "🏓 TashevNet agent is alive"
        if command == "/status":
            if not snapshot:
                return "⚪ No monitoring snapshot yet"
            return format_snapshot(snapshot)
        if command == "/vpn":
            if not snapshot:
                return "VPN: unknown"
            return (
                f"VPN: {'🟢 ON' if snapshot.vpn_connected else '🔴 OFF'}\n"
                f"Interface: {snapshot.vpn_interface or 'not detected'}\n"
                f"Public IP: {snapshot.public_ip or 'unknown'}"
            )
        if command == "/events":
            events = await self.events_provider(8)
            if not events:
                return "No incidents recorded yet."
            return "\n".join(
                f"{item['timestamp'][11:19]} · {item['health']} · {item['reason']}"
                for item in events
            )
        return "Unknown command. Use /help"

    async def poll_once(self) -> None:
        if not self.ready or not self.config.polling:
            return
        response = await self._client.get(
            self._url("getUpdates"),
            params={"timeout": 25, "offset": self.offset, "allowed_updates": '["message"]'},
            timeout=35.0,
        )
        response.raise_for_status()
        data = response.json()
        for update in data.get("result", []):
            self.offset = max(self.offset, int(update["update_id"]) + 1)
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if chat_id != str(self.config.chat_id):
                continue
            text = str(message.get("text", "")).strip().split(maxsplit=1)[0]
            if not text.startswith("/"):
                continue
            reply = await self._command_text(text.split("@", 1)[0].lower())
            await self.send(reply)

    async def polling_loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)
