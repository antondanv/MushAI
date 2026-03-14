# ARCHITECTURE.md

## 1. Архитектурная идея

MushAI строится как **transport-agnostic, state-first, capability-driven agent runtime**, где центральным execution engine является **Magentic-One team runtime**, а все внешние каналы и будущие специализированные режимы подключаются поверх него.

Ключевой принцип: в центре системы находится не чат и не конкретный бот, а **единый runtime исполнения задач**, умеющий принимать нормализованный input, восстанавливать состояние, запускать команду агентов, сохранять результаты и возвращать наружу нормализованные output events.

## 2. Архитектурные слои

### 2.1. Transport / Channel Adapters
Ответственность слоя:
- принимать внешние события;
- преобразовывать их в `InboundMessage`;
- передавать их в runtime;
- преобразовывать `OutboundEvent` в формат канала.

Примеры адаптеров:
- CLI adapter
- HTTP / FastAPI adapter
- позже Telegram adapter
- позже Web UI adapter

Этот слой не должен содержать бизнес-логику исполнения задач.

### 2.2. API / Ingress Layer
Основной входной слой v1 — FastAPI.

Минимальные endpoint'ы:
- `POST /messages`
- `GET /sessions/{id}`
- `GET /runs/{id}`
- `GET /health`

FastAPI является основным ingress layer, но сам не исполняет задачу напрямую. Он делегирует выполнение в `TeamRuntime`.

### 2.3. Runtime Layer
Это сердце всей системы.

Основные обязанности:
- принять нормализованный input;
- определить `session` и создать `run`;
- загрузить checkpoint и memory context;
- создать или восстановить команду агентов;
- запустить execution;
- собрать `OutboundEvent`;
- сохранить state, logs и artifacts.

Главные сущности слоя:
- `TeamRuntime`
- `ExecutionContext`
- `RunCoordinator`
- `BranchManager`
- `SchedulerDispatcher`

### 2.4. Team Construction Layer
Этот слой отвечает за сборку execution engine.

Ключевой компонент:
- `MagenticTeamFactory`

Задачи:
- создать базовый состав команды;
- подключить model clients и инструменты;
- включить/выключить режимы исполнения;
- уметь собрать команду как для main run, так и для branch run.

Базовая команда v1:
- `WebSurfer`
- `FileSurfer`
- `Coder`
- `Terminal / CodeExecutor`

### 2.5. Capability Layer
Возможности системы оформляются как capabilities, а не как произвольные вызовы кода.

Начальный состав v1:
- files
- code execution
- workspace ops
- later web/tool hooks

Ключевые компоненты:
- `CapabilityRegistry`
- `CapabilityDescriptor`
- `CapabilityPolicy`

В v1 registry служит архитектурной основой. Полноценный pipeline расширения появляется позже, в v2.

### 2.6. State & Persistence Layer
Этот слой отвечает за сохранение жизненного цикла выполнения.

Основные сущности:
- `Session`
- `Run`
- `Message`
- `Checkpoint`
- `Artifact`
- `Task`
- `Branch`
- `SummaryBlock`

Требования к слою:
- хранить полный trace;
- хранить condensed context отдельно;
- сохранять checkpoints после run и branch run;
- уметь восстанавливаться после рестарта процесса.

### 2.7. Execution Sandbox Layer
Любое исполнение кода и терминальных команд должно проходить через контролируемый слой.

Ключевой компонент:
- `DockerExecutionService`

Функции:
- создать изолированный workspace;
- выполнить код / команды;
- вернуть `stdout`, `stderr`, `exit code`;
- сохранить файлы как artifacts;
- ограничить execution по времени и ресурсам.

### 2.8. Memory Layer
Memory в v1 — это не long-term semantic memory, а управляемая рабочая память runtime.

Компоненты:
- `MessageStore`
- `SummaryService`
- `ContextCompactor`
- `BranchSummaryWriter`

Подход:
- полный trace хранится отдельно;
- в модель подаётся condensed context;
- старые блоки диалога сворачиваются в summaries;
- branch traces не загрязняют main line, в неё попадает summary.

### 2.9. Scheduling Layer
Scheduler нужен для проактивных задач и future automation.

Компоненты:
- `TaskScheduler`
- `ScheduledTask`
- `SyntheticEventProducer`

Типы задач v1:
- once
- interval
- cron

Scheduler не исполняет задачу сам — он генерирует события, которые передаются в тот же runtime.

### 2.10. Observability Layer
Нужен для дебага, анализа и восстановления причинно-следственной цепочки.

Компоненты:
- structured logs
- trace ids
- tool logs
- execution logs
- branch logs
- run status timeline

## 3. Логическая схема системы

```text
[CLI / HTTP / Future Telegram / Future Web UI]
                |
                v
         [Channel Adapter]
                |
                v
          [FastAPI / API]
                |
                v
           [TeamRuntime]
      /         |         \
     v          v          v
[State]   [TeamFactory]  [Scheduler Events]
  |            |                |
  v            v                v
[Storage]   [Magentic Team]  [Synthetic Input]
                |
                v
        [Capability Registry]
                |
                v
      [DockerExecutionService]
                |
                v
           [Artifacts / Logs]
```

## 4. Предлагаемая структура репозитория

```text
mushai/
  api/
  channels/
  agents/
  execution/
  capabilities/
  sessions/
  branches/
  memory/
  artifacts/
  storage/
  policies/
  scheduling/
  schemas/
  settings/
  tests/
```

### Назначение каталогов

- `api/` — FastAPI app, endpoints, request/response schemas.
- `channels/` — CLI и будущие transport adapters.
- `agents/` — профили агентов, system prompts, team member configuration.
- `execution/` — `TeamRuntime`, `TeamFactory`, execution orchestration.
- `capabilities/` — registry, descriptors, bindings, future proposal pipeline hooks.
- `sessions/` — session lifecycle, repositories, session services.
- `branches/` — branch manager, branch summaries, fork mechanics.
- `memory/` — summaries, compaction, context materialization.
- `artifacts/` — artifact metadata, storage bindings, export logic.
- `storage/` — ORM/models, repositories, checkpoint persistence.
- `policies/` — execution and capability policies.
- `scheduling/` — scheduled tasks, synthetic events, dispatch.
- `schemas/` — normalized contracts and shared models.
- `settings/` — config and environment handling.
- `tests/` — integration and end-to-end tests.

## 5. Базовые контракты данных

### 5.1. InboundMessage
Минимальный нормализованный вход:
- `message_id`
- `channel`
- `user_id`
- `session_id`
- `content`
- `metadata`
- `timestamp`

### 5.2. OutboundEvent
Нормализованный выход:
- `event_id`
- `run_id`
- `session_id`
- `event_type`
- `payload`
- `artifacts`
- `timestamp`

### 5.3. Session
Хранит долгоживущее состояние пользовательской линии взаимодействия.

### 5.4. Run
Хранит отдельное исполнение внутри session.

### 5.5. Checkpoint
Снимок состояния команды и связанного рабочего контекста.

### 5.6. Artifact
Файл, лог, результат выполнения кода, summary или иной полезный выход run.

### 5.7. Branch
Производная линия выполнения, созданная fork'ом от checkpoint.

## 6. Основные execution-потоки

### 6.1. Основной пользовательский run

```text
InboundMessage
  -> Channel Adapter
  -> FastAPI / API
  -> TeamRuntime
  -> Load Session / Checkpoint
  -> Build or Restore Team
  -> Execute Team Run
  -> Save Messages / Checkpoint / Artifacts
  -> Produce OutboundEvent
```

### 6.2. Branch run

```text
Main Session Checkpoint
  -> BranchManager.fork()
  -> Isolated Branch Run
  -> Branch Trace / Branch Artifacts
  -> Branch Summary
  -> Attach Summary to Main Session
```

### 6.3. Scheduled run

```text
Scheduler Trigger
  -> SyntheticEventProducer
  -> TeamRuntime
  -> Normal Run Lifecycle
  -> Notification / Artifact / Status Update
```

## 7. Почему ядро строится вокруг TeamRuntime

`TeamRuntime` — это точка, в которой сходятся:
- все transport adapters;
- state lifecycle;
- team construction;
- capability access;
- sandbox execution;
- logging and observability.

Если не сделать этот слой отдельным, проект быстро скатится обратно в монолитный `magnetic.py`, где transport, prompts, execution и storage будут смешаны в один entry script.

## 8. Почему FastAPI-first

FastAPI в v1 нужен не как "веб-фреймворк ради моды", а как универсальный ingress layer, который:
- даёт стабильную точку входа;
- упрощает интеграцию CLI и будущих transport adapters;
- позволяет позже добавить Web UI, webhooks и streaming;
- отделяет transport concerns от runtime concerns.

## 9. Почему state-first

Если состояние не является базовой сущностью с самого начала, то позже будет очень трудно корректно добавить:
- restart recovery;
- summaries;
- scheduler;
- branching;
- workflow modes;
- capability lifecycle.

Поэтому `sessions`, `runs`, `messages`, `checkpoints` и `artifacts` — не вторичная инфраструктура, а основа архитектуры.

## 10. Почему branching делается как summary-first

В v1 ветвление нужно не для полного merge состояний, а для безопасного побочного исследования.

Правильная модель v1:
- создать fork от checkpoint;
- выполнить side-quest в изоляции;
- вернуть в main line summary и, при необходимости, selected artifacts.

Это даёт большую часть пользы ветвления без преждевременной сложности полноценного state merge.

## 11. Архитектурные риски

### Риск 1. Возврат к монолиту
Если `TeamRuntime` и `TeamFactory` не будут выделены явно, система снова превратится в хрупкий entrypoint.

### Риск 2. Раннее усложнение v1
Если попытаться добавить long-term memory, graph engine и self-extension в v1, базовый runtime станет нестабильным.

### Риск 3. Смешение transport и execution
Если каналы начнут выполнять свою собственную бизнес-логику, transport-agnostic модель будет разрушена.

### Риск 4. Отсутствие изоляции исполнения
Если код начнёт выполняться без строгой песочницы, это нарушит один из ключевых принципов безопасности проекта.

## 12. Архитектурный ориентир на будущее

v1 должна быть достаточно простой, чтобы её можно было реально собрать, но при этом достаточно правильной, чтобы на неё естественно наслаивались:
- `ExecutionMode abstraction` в v1.5;
- `Capability pipeline` в v2;
- зрелый `BranchManager` и `WorkflowRegistry` в v2.5;
- multi-channel mature runtime в v3.
