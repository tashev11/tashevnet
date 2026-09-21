from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(slots=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    polling: bool = True


@dataclass(slots=True)
class SpeedConfig:
    enabled: bool = True
    interval_minutes: int = 60
    download_bytes: int = 2_000_000
    upload_bytes: int = 500_000
    base_url: str = "https://speed.cloudflare.com"


@dataclass(slots=True)
class MonitorConfig:
    interval_seconds: int = 5
    degraded_latency_ms: float = 250
    internet_hosts: list[str] = field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])
    dns_names: list[str] = field(default_factory=lambda: ["cloudflare.com", "github.com"])
    http_urls: list[str] = field(
        default_factory=lambda: ["https://www.cloudflare.com/cdn-cgi/trace"]
    )
    public_ip_url: str = "https://api.ipify.org"
    gateway: str = ""
    vpn_required: bool = False
    vpn_expected_ip: str = ""
    vpn_interface_patterns: list[str] = field(
        default_factory=lambda: ["utun", "tun", "tap", "wg", "wireguard", "tailscale", "ppp"]
    )
    self_heal_vpn_command: str = ""
    self_heal_cooldown_seconds: int = 60


@dataclass(slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    db_path: str = "~/.tashevnet/tashevnet.db"
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    speed: SpeedConfig = field(default_factory=SpeedConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


def load_config(path: str | None = None) -> AppConfig:
    raw: dict = {}
    target = Path(path or os.getenv("TASHEVNET_CONFIG", "config.yaml"))
    if target.exists():
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

    monitor = MonitorConfig(**raw.get("monitor", {}))
    speed = SpeedConfig(**raw.get("speed", {}))
    tg_raw = raw.get("telegram", {})
    telegram = TelegramConfig(
        enabled=bool(tg_raw.get("enabled", False)),
        bot_token=os.getenv("TASHEVNET_TELEGRAM_BOT_TOKEN", tg_raw.get("bot_token", "")),
        chat_id=os.getenv("TASHEVNET_TELEGRAM_CHAT_ID", str(tg_raw.get("chat_id", ""))),
        polling=bool(tg_raw.get("polling", True)),
    )
    app = raw.get("app", {})
    return AppConfig(
        host=app.get("host", "127.0.0.1"),
        port=int(app.get("port", 8765)),
        db_path=os.path.expanduser(app.get("db_path", "~/.tashevnet/tashevnet.db")),
        monitor=monitor,
        speed=speed,
        telegram=telegram,
    )
