from __future__ import annotations

import os
from dataclasses import MISSING, Field, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_FILE = "config.yaml"


class ConfigError(ValueError):
    """config.yaml (or an environment override) cannot be used as written."""


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
    snapshot_interval_seconds: int = 60
    retention_days: int = 30
    degraded_latency_ms: float = 250.0
    alert_after_checks: int = 2
    recover_after_checks: int = 3
    internet_hosts: list[str] = field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])
    dns_names: list[str] = field(default_factory=lambda: ["cloudflare.com", "github.com"])
    http_urls: list[str] = field(
        default_factory=lambda: ["https://www.cloudflare.com/cdn-cgi/trace"]
    )
    public_ip_url: str = "https://api.ipify.org"
    public_ip_interval_seconds: int = 30
    gateway: str = ""
    vpn_required: bool = False
    vpn_expected_ip: str = ""
    vpn_interface_patterns: list[str] = field(
        default_factory=lambda: [
            "utun", "tun", "tap", "wg", "wireguard", "wintun", "openvpn", "tailscale", "ppp",
        ]
    )
    self_heal_vpn_command: str = ""
    self_heal_cooldown_seconds: int = 60
    self_heal_timeout_seconds: int = 60


@dataclass(slots=True)
class _AppSection:
    host: str = "127.0.0.1"
    port: int = 8765
    db_path: str = "~/.tashevnet/tashevnet.db"


@dataclass(slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    db_path: str = "~/.tashevnet/tashevnet.db"
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    speed: SpeedConfig = field(default_factory=SpeedConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    # Where the settings came from; None means built-in defaults.
    config_path: str | None = None


SECTIONS = ("app", "monitor", "speed", "telegram")


def load_config(path: str | None = None) -> AppConfig:
    """Read config.yaml and apply environment overrides.

    A path given explicitly (argument or TASHEVNET_CONFIG) must exist: a typo there
    must not silently turn off the VPN watchdog. Without an explicit path, a missing
    ./config.yaml means built-in defaults.
    """
    explicit = path or os.getenv("TASHEVNET_CONFIG") or None
    target = Path(explicit or DEFAULT_CONFIG_FILE).expanduser()
    raw: dict[str, Any] = {}
    source: str | None = None

    if target.is_dir():
        raise ConfigError(
            f"{target} is a directory, not a YAML file. Docker creates a directory when "
            "./config.yaml is missing: run `cp config.example.yaml config.yaml` first."
        )
    if target.exists():
        try:
            loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"{target}: invalid YAML: {exc}") from exc
        raw = _mapping(loaded, str(target))
        source = str(target.resolve())
    elif explicit:
        raise ConfigError(f"Config file not found: {target}")

    unknown = sorted(set(raw) - set(SECTIONS))
    if unknown:
        raise ConfigError(
            f"Unknown section(s) in {target}: {', '.join(unknown)}. "
            f"Allowed: {', '.join(SECTIONS)}."
        )

    app = _build(_AppSection, raw.get("app"), "app")
    monitor = _build(MonitorConfig, raw.get("monitor"), "monitor")
    speed = _build(SpeedConfig, raw.get("speed"), "speed")
    telegram = _build(TelegramConfig, raw.get("telegram"), "telegram")

    # Environment wins over the file, but only when it carries a value: docker compose
    # passes empty strings for unset variables and must not wipe a token from the file.
    telegram.bot_token = _env("TASHEVNET_TELEGRAM_BOT_TOKEN") or telegram.bot_token
    telegram.chat_id = _env("TASHEVNET_TELEGRAM_CHAT_ID") or telegram.chat_id
    app.host = _env("TASHEVNET_HOST") or app.host
    app.db_path = _env("TASHEVNET_DB_PATH") or app.db_path
    port = _env("TASHEVNET_PORT")
    if port:
        try:
            app.port = int(port)
        except ValueError as exc:
            raise ConfigError(f"TASHEVNET_PORT must be a number, got {port!r}") from exc

    config = AppConfig(
        host=app.host,
        port=app.port,
        db_path=os.path.expanduser(app.db_path),
        monitor=monitor,
        speed=speed,
        telegram=telegram,
        config_path=source,
    )
    _check_ranges(config)
    return config


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{where}' must be a mapping of settings, got {type(value).__name__}")
    return value


def _default_of(spec: Field) -> Any:
    if spec.default is not MISSING:
        return spec.default
    return spec.default_factory()  # type: ignore[misc]


def _build(cls: type, data: Any, section: str) -> Any:
    values = _mapping(data, section)
    specs = {spec.name: spec for spec in fields(cls)}
    unknown = sorted(set(values) - set(specs))
    if unknown:
        raise ConfigError(
            f"Unknown setting(s) in '{section}': {', '.join(unknown)}. "
            f"Allowed: {', '.join(specs)}."
        )
    kwargs = {
        name: _coerce(value, _default_of(specs[name]), f"{section}.{name}")
        for name, value in values.items()
    }
    return cls(**kwargs)


def _coerce(value: Any, default: Any, key: str) -> Any:
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        raise ConfigError(f"{key} must be true or false, got {value!r}")
    if isinstance(default, int):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise ConfigError(f"{key} must be a whole number, got {value!r}")
    if isinstance(default, float):
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        raise ConfigError(f"{key} must be a number, got {value!r}")
    if isinstance(default, str):
        if value is None:
            return ""
        if isinstance(value, str | int | float) and not isinstance(value, bool):
            return str(value)
        raise ConfigError(f"{key} must be text, got {value!r}")
    if isinstance(default, list):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ConfigError(f"{key} must be a list, got {value!r}")
        items = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, str | int | float):
                raise ConfigError(f"{key} must contain only text items, got {item!r}")
            items.append(str(item))
        return items
    return value


def _check_ranges(config: AppConfig) -> None:
    monitor, speed = config.monitor, config.speed
    rules = [
        (1 <= config.port <= 65535, "app.port must be between 1 and 65535"),
        (monitor.interval_seconds >= 1, "monitor.interval_seconds must be at least 1"),
        (monitor.snapshot_interval_seconds >= 1, "monitor.snapshot_interval_seconds must be >= 1"),
        (monitor.retention_days >= 0, "monitor.retention_days must be 0 (keep) or more"),
        (monitor.degraded_latency_ms > 0, "monitor.degraded_latency_ms must be positive"),
        (monitor.alert_after_checks >= 1, "monitor.alert_after_checks must be at least 1"),
        (monitor.recover_after_checks >= 1, "monitor.recover_after_checks must be at least 1"),
        (monitor.public_ip_interval_seconds >= 0, "monitor.public_ip_interval_seconds must be >= 0"),
        (monitor.self_heal_cooldown_seconds >= 0, "monitor.self_heal_cooldown_seconds must be >= 0"),
        (monitor.self_heal_timeout_seconds >= 1, "monitor.self_heal_timeout_seconds must be >= 1"),
        (speed.interval_minutes >= 1, "speed.interval_minutes must be at least 1"),
        (speed.download_bytes >= 1, "speed.download_bytes must be at least 1"),
        (speed.upload_bytes >= 1, "speed.upload_bytes must be at least 1"),
    ]
    for ok, message in rules:
        if not ok:
            raise ConfigError(message)
