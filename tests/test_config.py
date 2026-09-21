from __future__ import annotations

from pathlib import Path

import pytest

from tashevnet.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "TASHEVNET_CONFIG",
        "TASHEVNET_TELEGRAM_BOT_TOKEN",
        "TASHEVNET_TELEGRAM_CHAT_ID",
        "TASHEVNET_HOST",
        "TASHEVNET_PORT",
        "TASHEVNET_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def write(tmp_path, text: str) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_example_config_is_valid():
    config = load_config(str(ROOT / "config.example.yaml"))
    assert config.monitor.alert_after_checks == 2
    assert config.config_path is not None


def test_telegram_secrets_can_come_from_environment(monkeypatch, tmp_path):
    path = write(tmp_path, "telegram:\n  enabled: true\n")
    monkeypatch.setenv("TASHEVNET_TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TASHEVNET_TELEGRAM_CHAT_ID", "123")
    config = load_config(path)
    assert config.telegram.bot_token == "token"
    assert config.telegram.chat_id == "123"


def test_empty_environment_does_not_wipe_the_token_from_the_file(monkeypatch, tmp_path):
    # docker compose passes "" for unset variables
    path = write(tmp_path, "telegram:\n  bot_token: '1:abc'\n  chat_id: -1001\n")
    monkeypatch.setenv("TASHEVNET_TELEGRAM_BOT_TOKEN", "")
    config = load_config(path)
    assert config.telegram.bot_token == "1:abc"
    assert config.telegram.chat_id == "-1001"


def test_app_settings_can_come_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TASHEVNET_HOST", "0.0.0.0")
    monkeypatch.setenv("TASHEVNET_PORT", "9000")
    monkeypatch.setenv("TASHEVNET_DB_PATH", str(tmp_path / "x.db"))
    config = load_config(write(tmp_path, "{}"))
    assert (config.host, config.port, config.db_path) == ("0.0.0.0", 9000, str(tmp_path / "x.db"))


def test_explicit_path_must_exist(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(str(tmp_path / "confg.yaml"))


def test_config_path_from_environment_must_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("TASHEVNET_CONFIG", str(tmp_path / "missing.yaml"))
    with pytest.raises(ConfigError, match="not found"):
        load_config()


def test_no_config_file_means_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.config_path is None and config.port == 8765


def test_directory_instead_of_file_explains_the_docker_pitfall(tmp_path):
    (tmp_path / "config.yaml").mkdir()
    with pytest.raises(ConfigError, match="cp config.example.yaml"):
        load_config(str(tmp_path / "config.yaml"))


def test_unknown_setting_is_rejected_with_the_allowed_list(tmp_path):
    with pytest.raises(ConfigError, match="intervall_seconds"):
        load_config(write(tmp_path, "monitor:\n  intervall_seconds: 5\n"))


def test_wrong_type_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="interval_seconds must be a whole number"):
        load_config(write(tmp_path, "monitor:\n  interval_seconds: 5s\n"))


def test_out_of_range_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="at least 1"):
        load_config(write(tmp_path, "monitor:\n  interval_seconds: 0\n"))


def test_empty_sections_mean_defaults(tmp_path):
    config = load_config(write(tmp_path, "app:\nmonitor:\ntelegram:\nspeed:\n"))
    assert config.monitor.interval_seconds == 5 and config.telegram.enabled is False


def test_float_setting_accepts_whole_numbers(tmp_path):
    config = load_config(write(tmp_path, "monitor:\n  degraded_latency_ms: 300\n"))
    assert config.monitor.degraded_latency_ms == 300.0
