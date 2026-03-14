# ROADMAP.md

## 1. Общая стратегия развития

Roadmap MushAI строится по принципу **foundation first**:

1. Сначала собирается надёжное runtime-ядро.
2. Затем добавляется управляемая специализация execution.
3. Затем система получает контролируемое расширение capabilities.
4. После этого ветвление и workflow становятся зрелыми объектами.
5. В финале система становится зрелым автономным multi-channel runtime.

Иными словами, проект движется по траектории:

**Core Runtime -> Structured Execution -> Capability Expansion -> Branching & Workflow Maturity -> Mature Autonomous Runtime**

---

## 2. Версия v1 — Core Runtime

### Главная цель

Создать надёжное, расширяемое агентное ядро, где основным execution engine является **Magentic-One team**, и которое уже может использоваться как настоящий personal assistant runtime.

### Что должно появиться

#### Ядро
- FastAPI-first архитектура
- CLI и HTTP как первые адаптеры
- единый runtime для всех каналов
- нормализованные `InboundMessage / OutboundEvent`

#### Execution engine
- `MagenticOneGroupChat` как базовая команда
- `MagenticTeamFactory`
- базовый состав команды: `WebSurfer`, `FileSurfer`, `Coder`, `Terminal / CodeExecutor`

#### Состояние
- `Sessions`
- `Runs`
- `Messages`
- `Checkpoints`
- сохранение и восстановление состояния

#### Инструменты и execution
- workspace на уровне session/run
- Docker sandbox
- `stdout/stderr/exit code`
- artifacts

#### Память
- краткосрочная память
- summaries
- context compaction

#### Организация задач
- `Task model`
- `Artifact model`
- scheduler
- timed runs

#### Ветвление
- prototype `BranchManager`
- checkpoint fork
- branch summary back to main

#### Наблюдаемость
- structured logs
- trace ids
- execution/tool events

### Этапы разработки v1

#### V1-1. Зафиксировать архитектуру
Сделать документы:
- `PROJECT_SCOPE.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `ROADMAP.md`

Зафиксировать:
- Magentic-One team как базовый engine
- FastAPI-first
- channel adapters отдельно от ядра
- state/checkpoint model обязательно с v1
- capability registry как основа для будущего self-extension

#### V1-2. Разобрать текущий прототип
Разделить текущий `magnetic.py` на модули:
- settings/config
- prompt rules loader
- code executor factory
- team factory
- team runtime
- channels

Цель: убрать монолитный entry script.

#### V1-3. Собрать чистое ядро репозитория
Создать структуру:
- `api/`
- `channels/`
- `agents/`
- `execution/`
- `capabilities/`
- `sessions/`
- `branches/`
- `memory/`
- `artifacts/`
- `storage/`
- `policies/`
- `scheduling/`
- `schemas/`

#### V1-4. Реализовать TeamFactory
Сделать явную сборку базовой команды и вынести её в `MagenticTeamFactory`.

#### V1-5. Реализовать TeamRuntime
Слой должен:
- принимать нормализованный input
- находить session
- поднимать checkpoint
- строить или восстанавливать команду
- запускать team run
- собирать output events
- сохранять state и результаты

#### V1-6. Реализовать persistence
Добавить БД и модели:
- sessions
- runs
- messages
- checkpoints
- artifacts

Реализовать load/save lifecycle.

#### V1-7. Реализовать sandbox execution
Собрать `DockerExecutionService`:
- отдельный workspace
- sandbox limits
- `stdout/stderr/exit code`
- artifact export

#### V1-8. Реализовать capability registry v1
Добавить реестр для базовых capabilities:
- files
- code execution
- workspace ops
- later web/tool hooks

Пока без self-install, но уже через registry.

#### V1-9. Реализовать FastAPI и CLI adapters
Сделать:
- `POST /messages`
- `GET /sessions/{id}`
- `GET /runs/{id}`
- `GET /health`
- CLI adapter

Все каналы используют единый runtime.

#### V1-10. Реализовать summaries и compaction
Добавить:
- краткосрочную память
- summary blocks
- context compaction
- branch summaries

#### V1-11. Реализовать task/artifact layer
Добавить:
- `Task model`
- artifact storage
- artifact metadata
- привязку результатов к runs/sessions

#### V1-12. Реализовать scheduler
Добавить:
- once tasks
- interval tasks
- cron tasks
- synthetic system events
- уведомления / автозапуски

#### V1-13. Реализовать branch prototype
Сделать:
- checkpoint fork
- isolated branch run
- summarize branch
- merge summary to main

Пока без сложного merge state.

#### V1-14. Добавить observability
Сделать:
- structured logs
- trace ids
- tool execution logs
- team event logs
- branch event logs

#### V1-15. Hardening v1
Добавить:
- retries
- timeouts
- idempotency
- recovery after restart
- cleanup policies
- integration tests
- end-to-end tests

### Definition of Done для v1

v1 завершена, если:
- базовый engine = `Magentic-One team`
- CLI и HTTP работают через единый runtime
- state сохраняется и восстанавливается
- код выполняется в Docker
- есть workspace и artifacts
- есть summaries
- есть scheduler
- есть prototype branch flow
- есть логи и тесты

---

## 3. Версия v1.5 — Structured Execution

### Главная цель

Добавить управляемую специализацию execution modes без ломки v1.

### Что входит
- `ExecutionMode abstraction`
- `TeamRuntime` как расширяемый execution layer
- `AgentTool / TeamTool abstraction`
- router по типу задачи
- первые специализированные режимы:
  - direct chat mode
  - coding mode
  - research mode
  - branch mode
- первые deterministic workflows
- первый workflow runner

### Что это даёт

На этом этапе MushAI умеет не только запускать базовую команду, но и выбирать более подходящий execution mode под тип задачи.

### Что ещё не входит
- полноценный self-extension
- полноценная graph-centric execution architecture
- зрелая long-term memory

### Definition of Done для v1.5

MushAI умеет выбирать execution mode и использовать команду, подагента или специализированный workflow без изменения ядра.

---

## 4. Версия v2 — Capability Expansion

### Главная цель

Сделать MushAI системой, которая умеет контролируемо расширять собственные возможности.

### Базовый принцип

Никакого хаотичного hot reload. Саморасширение строится только как gated capability pipeline.

### Что входит

#### Capability Registry 2.0
- единый реестр capabilities
- типы capabilities:
  - function tools
  - file tools
  - sandbox tools
  - MCP capabilities
  - agent tools
  - team tools
  - workflow capabilities

#### Capability supply chain
- detect capability gap
- generate spec
- generate implementation
- sandbox test
- static checks
- policy checks
- candidate registration
- approval
- activation
- rollback

#### Skill / Tool packaging
- manifest
- versioning
- tests
- permissions
- dependencies
- install history

#### Subagent system
- `SubagentSpec`
- `SubagentRegistry`
- `TeamFactory` extensions
- подключаемые специализированные агенты

### Definition of Done для v2

MushAI умеет создавать, тестировать, регистрировать, одобрять, активировать и откатывать новые capabilities, включая tools, subagents и workflow components.

---

## 5. Версия v2.5 — Branching & Workflow Maturity

### Главная цель

Сделать ветвление и workflow полноценной частью системы.

### Что входит
- named branches
- branch inspection
- branch summaries
- selective merge
- workflow registry
- workflow runner
- GraphFlow / graph-based deterministic flows там, где это действительно полезно

### Важный принцип

Graph/workflow layer используется как execution mechanism для отдельных режимов, а не как основа всей пользовательской сессии.

### Definition of Done для v2.5

MushAI умеет управлять ветками и workflow как полноценными объектами системы.

---

## 6. Версия v3 — Mature Autonomous Runtime

### Главная цель

Сделать MushAI зрелой автономной системой, готовой к многоканальной работе и долгому циклу развития.

### Что входит
- Telegram adapter
- Web UI adapter
- дополнительные transport adapters
- long-term curated memory
- advanced policies
- improved observability
- capability governance
- устойчивый self-extension loop

### Definition of Done для v3

MushAI становится зрелым автономным personal runtime с несколькими каналами, управляемым расширением и стабильной архитектурой.

---

## 7. Рекомендуемый порядок работ на ближайшем старте

### Этап 1. Архитектурная фиксация
Сделать и принять базовые документы.

### Этап 2. Разделение текущего прототипа
Убрать `magnetic.py` как монолит.

### Этап 3. Вертикальный срез v1
Собрать минимальный путь:
`InboundMessage -> TeamRuntime -> TeamFactory -> Team Run -> State Save -> OutboundEvent`

### Этап 4. Persistence и sandbox
После первого вертикального среза стабилизировать storage и Docker execution.

### Этап 5. Adapters и branch/scheduler layer
Подключить реальные точки входа и первые side-quest / timed execution механики.

### Этап 6. Hardening
Добавить retries, cleanup, integration tests и observability до перехода к v1.5.

---

## 8. Критические риски roadmap

### Риск 1. Слишком ранний уход в UI и transport
Если начать с Telegram или Web UI, ядро может остаться сырым.

### Риск 2. Слишком ранняя graph-архитектура
Если сделать workflows основой всего проекта слишком рано, усложнение съест скорость разработки.

### Риск 3. Слишком раннее саморасширение
Если перенести capability pipeline в v1, устойчивость ядра пострадает.

### Риск 4. Отсутствие observability
Без логов, trace ids и run timeline будет трудно стабилизировать систему даже на v1.

---

## 9. Финальная формула развития проекта

**MushAI — это персональный автономный agent runtime, построенный вокруг Magentic-One team, который сначала становится надёжной системой выполнения задач, затем системой branching/workflow orchestration, а потом — контролируемо саморасширяемой платформой capabilities.**
