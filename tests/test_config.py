from tashevnet.config import load_config


def test_telegram_secrets_can_come_from_environment(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("telegram:\n  enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("TASHEVNET_TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TASHEVNET_TELEGRAM_CHAT_ID", "123")
    cfg = load_config(str(path))
    assert cfg.telegram.bot_token == "token"
    assert cfg.telegram.chat_id == "123"
