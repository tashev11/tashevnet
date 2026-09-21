from __future__ import annotations

import httpx
import pytest

from tashevnet import cli
from tashevnet.config import AppConfig, TelegramConfig

TOKEN = "123456:SECRET-TOKEN-VALUE"


def run(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    captured = capsys.readouterr()
    return exit_info.value.code, captured.out, captured.err


def test_typo_in_config_path_is_an_error(tmp_path, capsys):
    code, _, err = run(["--config", str(tmp_path / "confg.yaml"), "doctor"], capsys)
    assert code == 2 and "Config file not found" in err


def test_config_option_works_after_the_command(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text(f"app:\n  db_path: {tmp_path / 'db' / 'x.db'}\n", encoding="utf-8")
    code, out, _ = run(["doctor", "--config", str(path)], capsys)
    assert code == 0 and str(path) in out


def test_doctor_reports_missing_telegram_settings(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text(
        f"app:\n  db_path: {tmp_path / 'x.db'}\ntelegram:\n  enabled: true\n", encoding="utf-8"
    )
    code, out, _ = run(["--config", str(path), "doctor"], capsys)
    assert code == 1 and "bot token and chat id is missing" in out


async def test_telegram_id_does_not_print_the_token(monkeypatch, capsys):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"ok": False}))
    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw)
    )
    config = AppConfig(telegram=TelegramConfig(bot_token=TOKEN))
    assert await cli._telegram_id(config) == 2
    captured = capsys.readouterr()
    assert "HTTP 401" in captured.err and TOKEN not in captured.err + captured.out


async def test_once_writes_no_history(tmp_path, net, capsys):
    config = AppConfig(db_path=str(tmp_path / "never.db"))
    assert await cli._once(config) == 0
    assert '"health": "UP"' in capsys.readouterr().out
    assert not (tmp_path / "never.db").exists()
