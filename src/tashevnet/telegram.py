from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

import httpx

from .config import TelegramConfig
from .models import Snapshot
from .probes import short_error
from .state import Transition

log = logging.getLogger("tashevnet.telegram")

StatusProvider = Callable[[], dict[str, Any]]
EventsProvider = Callable[[int], Awaitable[list[dict[str, Any]]]]
Delivery = Literal["sent", "retry", "rejected"]

ICONS = {"UP": "🟢", "DEGRADED": "🟡", "DOWN": "🔴", "UNKNOWN": "⚪"}
# Commands older than this were sent while the agent was offline, or were already
# answered before a restart; replying to them now would only confuse.
STALE_COMMAND_SECONDS = 120
MAX_PENDING_ALERTS = 50
RETRY_SECONDS = 10

HELP = (
    "TashevNet bot\n"
    "/status — current connection\n"
    "/vpn — VPN state\n"
    "/events — recent incidents\n"
    "/ping — is the agent alive"
)


class TelegramError(RuntimeError):
    pass


def local_time(value: str | None, *, date: bool = True) -> str:
    """ISO timestamp (stored in UTC) shown in this machine's time zone."""
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(value).astimezone()
    except (TypeError, ValueError):
        return value
    return moment.strftime("%d.%m %H:%M:%S %Z" if date else "%H:%M:%S").strip()


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = round(seconds)
    if total < 60:
        return f"{total} s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} min {secs} s" if secs else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h" if hours else f"{days} d"


def _details(snapshot: Snapshot) -> list[str]:
    vpn = "ON" if snapshot.vpn_connected else "OFF"
    if snapshot.vpn_interface:
        vpn += f" · {snapshot.vpn_interface}"
    lines = [f"Public IP: {snapshot.public_ip or 'unknown'}", f"VPN: {vpn}"]
    if snapshot.gateway:
        lines.append(f"Gateway: {snapshot.gateway}")
    if snapshot.line_latency_ms is not None:
        lines.append(f"Line latency: {snapshot.line_latency_ms:.0f} ms")
    if snapshot.speed and snapshot.speed.download_mbps is not None:
        lines.append(
            f"Speed: ↓ {snapshot.speed.download_mbps:.1f} Mbps · "
            f"↑ {snapshot.speed.upload_mbps or 0:.1f} Mbps"
        )
    return lines


def format_snapshot(snapshot: Snapshot) -> str:
    icon = ICONS.get(snapshot.health.value, "⚪")
    lines = [f"{icon} TashevNet · {snapshot.health.value}", snapshot.reason]
    lines += _details(snapshot)
    lines.append(local_time(snapshot.timestamp))
    return "\n".join(lines)


def format_transition(transition: Transition, snapshot: Snapshot | None = None) -> str:
    current, previous = transition.current, transition.previous
    icon = ICONS.get(current.health.value, "⚪")
    if previous is not None and previous.level > 0 and current.level == 0:
        head = f"{icon} TashevNet · back to {current.health.value}"
        if transition.duration_seconds is not None:
            head += f" after {human_duration(transition.duration_seconds)}"
        lines = [head, f"Was {previous.health.value}: {previous.reason}"]
    else:
        lines = [f"{icon} TashevNet · {current.health.value}", current.reason]
        if previous is None:
            lines.append("Detected right after start-up.")
    if snapshot is not None:
        lines += _details(snapshot)
    lines.append(f"Since {local_time(current.timestamp)}")
    return "\n".join(lines)


def _description(response: httpx.Response) -> str:
    with contextlib.suppress(ValueError):
        return str(response.json().get("description", ""))[:200]
    return response.text[:200]


class TelegramBot:
    def __init__(
        self,
        config: TelegramConfig,
        status_provider: StatusProvider,
        events_provider: EventsProvider,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.status_provider = status_provider
        self.events_provider = events_provider
        self.offset: int | None = None
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._pending: deque[str] = deque(maxlen=MAX_PENDING_ALERTS)
        self._wake = asyncio.Event()

    @property
    def ready(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token and self.config.chat_id)

    @property
    def pending(self) -> int:
        return len(self._pending)

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.config.bot_token}/{method}"

    def redact(self, text: str) -> str:
        token = self.config.bot_token
        return text.replace(token, "<bot-token>") if token else text

    async def close(self) -> None:
        await self._client.aclose()

    def notify(self, text: str) -> None:
        """Queue an alert. It is delivered as soon as Telegram is reachable, so an
        outage alert arrives after the connection returns instead of being lost."""
        if not self.ready:
            return
        self._pending.append(text)
        self._wake.set()

    async def flush(self) -> int:
        """Deliver queued alerts in order; stop at the first one that must wait."""
        done = 0
        while self._pending:
            if await self._deliver(self._pending[0]) == "retry":
                break
            self._pending.popleft()
            done += 1
        return done

    async def delivery_loop(self) -> None:
        while True:
            self._wake.clear()
            await self.flush()
            if self._pending:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=RETRY_SECONDS)
            else:
                await self._wake.wait()

    async def send(self, text: str) -> bool:
        """Send right away (command replies). Never raises."""
        if not self.ready:
            return False
        return await self._deliver(text) == "sent"

    async def _deliver(self, text: str) -> Delivery:
        try:
            response = await self._client.post(
                self._url("sendMessage"),
                json={
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
        except httpx.HTTPError as exc:
            log.warning("Telegram is unreachable: %s", self.redact(short_error(exc)))
            return "retry"
        if response.is_success:
            return "sent"
        description = self.redact(_description(response))
        if response.status_code == 429 or response.status_code >= 500:
            log.warning("Telegram asked to retry (HTTP %s): %s", response.status_code, description)
            return "retry"
        log.error("Telegram rejected a message (HTTP %s): %s", response.status_code, description)
        return "rejected"

    async def _command_text(self, command: str) -> str:
        status = self.status_provider()
        snapshot: Snapshot | None = status.get("snapshot")
        state: dict[str, Any] | None = status.get("state")
        if command in {"/start", "/help"}:
            return HELP
        if command == "/ping":
            last = local_time(snapshot.timestamp) if snapshot else "none yet"
            return f"🏓 TashevNet {status.get('version', '')} is alive · last check {last}"
        if command == "/status":
            if not snapshot:
                return "⚪ No check has finished yet"
            text = format_snapshot(snapshot)
            if state and state.get("since"):
                text += f"\nState {state['health']} since {local_time(state['since'])}"
            return text
        if command == "/vpn":
            if not snapshot:
                return "VPN: unknown"
            return (
                f"VPN: {'🟢 ON' if snapshot.vpn_connected else '🔴 OFF'}\n"
                f"Interface: {snapshot.vpn_interface or 'not detected'}\n"
                f"Carries Internet traffic: {'yes' if snapshot.vpn_routed else 'no'}\n"
                f"Public IP: {snapshot.public_ip or 'unknown'}"
            )
        if command == "/events":
            events = await self.events_provider(8)
            if not events:
                return "No incidents recorded yet."
            lines = []
            for item in events:
                line = (
                    f"{local_time(item['timestamp'])} · "
                    f"{ICONS.get(item['health'], '')} {item['health']} · {item['reason']}"
                )
                if item.get("duration_seconds") is not None:
                    line += f" · after {human_duration(item['duration_seconds'])}"
                lines.append(line)
            return "\n".join(lines)
        return "Unknown command. Use /help"

    async def poll_once(self) -> None:
        if not self.ready or not self.config.polling:
            await asyncio.sleep(30)
            return
        params: dict[str, Any] = {"timeout": 25, "allowed_updates": '["message"]'}
        if self.offset is not None:
            params["offset"] = self.offset
        try:
            response = await self._client.get(self._url("getUpdates"), params=params, timeout=35.0)
        except httpx.HTTPError as exc:
            raise TelegramError(f"getUpdates failed: {short_error(exc)}") from None
        if response.status_code == 409:
            raise TelegramError(
                "getUpdates conflict (HTTP 409): another program polls this bot "
                "or a webhook is set"
            )
        if not response.is_success:
            raise TelegramError(
                f"getUpdates failed (HTTP {response.status_code}): {_description(response)}"
            )
        now = time.time()
        for update in response.json().get("result", []):
            self.offset = max(self.offset or 0, int(update["update_id"]) + 1)
            message = update.get("message") or {}
            if str((message.get("chat") or {}).get("id", "")) != str(self.config.chat_id):
                continue
            if now - float(message.get("date") or 0) > STALE_COMMAND_SECONDS:
                continue
            words = str(message.get("text") or "").split()
            if not words or not words[0].startswith("/"):
                continue
            await self.send(await self._command_text(words[0].split("@", 1)[0].lower()))

    async def polling_loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Telegram commands: %s", self.redact(short_error(exc)))
                await asyncio.sleep(5)
