# MushAI

MushAI - это персональный agent runtime на Python, который строится вокруг `Magentic-One team`. Проект всё ещё движется к `v1`, но на текущем этапе уже есть рабочий базовый чат в CLI и выделенное runtime-ядро, через которое проходит выполнение задачи.

Сейчас это не "готовый продукт", а собираемая основа для будущего `v1`: с нормальной архитектурой, отдельным runtime, конфигурацией, sandbox execution и дальнейшим переходом к полноценным сессиям и сохранению контекста.

## Текущий этап

На данном этапе в проекте уже есть:

- базовый CLI-чат;
- `TeamRuntime`, который запускает команду агентов и стримит события наружу;
- `MagneticTeamFactory`, который собирает `Magentic-One` команду;
- конфигурация через `.env` и YAML-файл с prompt rules;
- локальный и Docker-режимы для code execution.

Ключевые файлы текущей версии:

- [`src/mushai/main.py`](src/mushai/main.py) - точка входа;
- [`src/mushai/channels/cli.py`](src/mushai/channels/cli.py) - текущий CLI-чат;
- [`src/mushai/execution/team_runtime.py`](src/mushai/execution/team_runtime.py) - runtime-цикл исполнения;
- [`src/mushai/execution/team_factory.py`](src/mushai/execution/team_factory.py) - сборка команды, model client и executor;
- [`src/mushai/settings/config.py`](src/mushai/settings/config.py) - загрузка настроек;
- [`config/prompts/system/magnetic_one.yml`](config/prompts/system/magnetic_one.yml) - правила поведения команды;
- [`Dockerfile`](Dockerfile) - базовый образ для sandbox execution.

## Что уже работает

Сценарий, который уже можно считать рабочим:

1. Пользователь пишет задачу в CLI.
2. `TeamRuntime` создаёт `run`, собирает команду и запускает её.
3. CLI показывает поток событий: выбор агента, размышления, tool calls, code execution и финальный ответ.
4. В рамках активной сессии runtime пытается использовать сохранённый `team_state` для следующего сообщения.

То есть базовый chat loop уже есть, и это важный шаг к `v1`.

## Текущее ограничение

Главная проблема на этом этапе: сохранение состояния само по себе пока не даёт нормального сохранения контекста.

Сейчас runtime уже умеет вызывать `save_state()` и `load_state()`, но этого недостаточно, чтобы диалог стабильно продолжал мысль между сообщениями так, как нужно для полноценной session-based работы. Проще говоря: состояние формально сохраняется, но полезный разговорный контекст удерживается не так надёжно, как требуется для `v1`.

Именно поэтому следующая основная задача проекта - не просто "добавить persistence", а сделать так, чтобы сохранение состояния реально помогало сохранять контекст между ходами и стало основой для будущих `sessions`, `runs`, `messages` и `checkpoints`.

## Ближайший фокус

Следующий этап разработки:

- разобраться, почему текущий `team_state` не удерживает нужный контекст;
- доработать модель сессии и восстановления состояния;
- связать сохранение состояния с реальным conversational context;
- после этого продолжить движение к полноценному `v1` runtime.

Иными словами, текущая цель проекта - превратить "рабочий CLI-чат" в устойчивый runtime, который не теряет нить задачи между сообщениями.

## Запуск текущей версии

На текущем этапе основной способ работы с проектом - запуск CLI-чата.

### 1. Подготовить окружение

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настроить `.env`

Проект автоматически читает переменные окружения из одного из двух файлов:

1. `config/.env`
2. `.env`

Если оба файла существуют, значения подхватываются без перезаписи уже существующих переменных окружения. Логика загрузки описана в [`src/mushai/settings/config.py`](src/mushai/settings/config.py).

Минимально для старта нужно задать модель и ключ доступа. Пример:

```env
PROJECT_NAME=MushAI

OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-5
MODEL_BASE_URL=https://api.openai.com/v1

MAGNETIC_PROMPTS_FILE=config/prompts/system/magnetic_one.yml

CODE_EXECUTOR_MODE=local
WORKSPACE_DIR=.magnetic_workspace
CODE_EXECUTION_TIMEOUT_SECONDS=90

TEAM_MAX_TURNS=12
TEAM_MAX_STALLS=2

HIL_MODE=false
HIL_TIMEOUT_SECONDS=300
```

### 3. Выбрать режим выполнения кода

Для быстрых локальных проверок:

```env
CODE_EXECUTOR_MODE=local
```

Для sandbox-режима через Docker:

```env
CODE_EXECUTOR_MODE=docker
CODE_EXECUTOR_IMAGE=python:3.12-slim
```

Если используется Docker-режим, Docker Engine должен быть установлен и доступен на машине.

### 4. Запустить CLI

```bash
PYTHONPATH=src python -m mushai.main
```

После запуска откроется простой цикл чата в терминале. Выход: `exit`, `quit`, `q`, `выход`.

## Переменные окружения текущего этапа

Ниже перечислены переменные окружения, которые уже реально используются кодом на текущем этапе.

| Переменная | Обязательна | По умолчанию | Что делает |
|---|---|---|---|
| `PROJECT_NAME` | нет | `MushAI` | Имя проекта в runtime-настройках. |
| `OPENAI_API_KEY` | обычно да | `None` | API-ключ для model client. Если провайдер требует ключ, без него модель не запустится. |
| `MODEL_NAME` | нет | `gpt-5` | Имя модели, с которой создаётся `OpenAIChatCompletionClient`. |
| `MODEL_BASE_URL` | нет | `https://api.openai.com/v1` | Базовый URL OpenAI-совместимого API. |
| `MAGNETIC_PROMPTS_FILE` | нет | `config/prompts/system/magnetic_one.yml` или fallback path | Путь до YAML-файла с prompt rules для команды. |
| `CODE_EXECUTOR_MODE` | нет | `docker` | Режим выполнения кода: `docker` или `local`. |
| `CODE_EXECUTOR_IMAGE` | нет | `autogen-custom-python` | Docker image для code execution, используется только в режиме `docker`. |
| `WORKSPACE_DIR` | нет | `.magnetic_workspace` | Рабочая директория для артефактов и исполнения кода. |
| `TEAM_MAX_TURNS` | нет | `12` | Максимальное число ходов команды в одном run. |
| `TEAM_MAX_STALLS` | нет | `2` | Порог остановки при зависании или отсутствии прогресса. |
| `CODE_EXECUTION_TIMEOUT_SECONDS` | нет | `90` | Таймаут выполнения кода. |
| `HIL_MODE` | нет | `false` | Включает human-in-the-loop для запросов на подтверждение и ввод пользователя. |
| `HIL_TIMEOUT_SECONDS` | нет | `300` | Зарезервированный таймаут для human-in-the-loop режима. |


## Документы проекта

Архитектурный контекст и план развития лежат здесь:

- [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) - границы и цель проекта;
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - целевая архитектура;
- [`DECISIONS.md`](DECISIONS.md) - ключевые архитектурные решения;
- [`ROADMAP.md`](ROADMAP.md) - движение к `v1`, `v1.5` и дальше.

## Статус

MushAI всё ещё находится на пути к `v1`. Уже есть рабочая точка входа через CLI и базовый runtime-цикл, но следующая критическая задача - добиться настоящего сохранения контекста между сообщениями, а не только формального сохранения состояния команды.

Именно это сейчас и является главным направлением разработки.
