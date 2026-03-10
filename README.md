# MushAI

Черновой pet-проект с агентами на базе AutoGen:
- `chief.py` — агент с веб-поиском и отправкой сообщений в Telegram.
- `magnetic.py` — Magentic-One команда (FileSurfer, WebSurfer, Coder, Terminal).

## Что нужно

- Python 3.11+
- Ключ OpenAI (`OPENAI_API_KEY`)
- Для `chief.py`: ключ Serper (`SERPER_API_KEY`) и Telegram bot credentials

## Установка

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

## Конфиг окружения

Создай `config/.env`:

```env
OPENAI_API_KEY=your_openai_key
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-5

SERPER_API_KEY=your_serper_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# optional
PROMPTS_FILE=config/prompts/chief_agents.yml
```

## Запуск

`chief.py`:

```powershell
.\venv\Scripts\python.exe chief.py
```

`magnetic.py`:

```powershell
.\venv\Scripts\python.exe magnetic.py
```

При запуске `magnetic.py` нужно ввести задачу в консоль.

## Структура

```text
MushAI/
  chief.py
  magnetic.py
  creator.py
  modules/
    telegram_bot.py
  config/
    prompts/
      chief_agents.yml
```

## Статус проекта

Проект в ранней стадии разработки. Интерфейс и структура могут часто меняться.
