# TashevNet — кратко на русском

TashevNet — локальный сетевой агент, который постоянно проверяет цепочку:

**компьютер → роутер → провайдер → DNS → интернет → VPN → нужные сервисы**.

Он не ограничивается сообщением «интернета нет», а пытается определить слой проблемы, записывает историю и может выполнить заранее настроенную команду восстановления VPN.

## Что уже есть в v0.1

- проверка физического шлюза;
- несколько независимых Internet probes;
- DNS и HTTP диагностика;
- контроль VPN-интерфейса;
- проверка ожидаемого внешнего IP для поиска VPN leak;
- ограниченный по трафику замер скорости;
- SQLite «чёрный ящик»;
- локальная веб-панель;
- Telegram-уведомления;
- команды Telegram `/status`, `/vpn`, `/events`, `/ping`;
- VPN self-heal с cooldown;
- macOS / Windows / Linux;
- Docker для серверного сценария.

## Быстрый запуск

```bash
git clone https://github.com/tashev11/tashevnet.git
cd tashevnet
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml
tashevnet doctor
tashevnet run
```

Панель: `http://127.0.0.1:8765`.

## Подключение Telegram

Создайте бота через **@BotFather**, задайте токен переменной окружения, напишите боту любое сообщение и выполните:

```bash
export TASHEVNET_TELEGRAM_BOT_TOKEN="..."
tashevnet telegram-id
export TASHEVNET_TELEGRAM_CHAT_ID="..."
```

Затем включите `telegram.enabled: true` в `config.yaml`.

Подробно: [TELEGRAM.md](TELEGRAM.md).
