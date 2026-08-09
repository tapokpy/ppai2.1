# Инструкция для автономного ИИ-агента (Claude Code)

**Версия:** 2.0 (исправленная и синхронизированная)  
**Дата:** 2026-08-09  
**Назначение:** Этот документ является единственным источником инструкций для Claude Code (или аналогичного автономного агента) при реализации проекта «ПридПром». Агент должен выполнять все шаги последовательно, без остановок на вопросы, самостоятельно исправляя ошибки и прогоняя тесты до 100% прохождения.

---

## 🔴 Краткая директива для агента

Прочитай этот документ полностью. Не задавай никаких уточняющих вопросов.  
Начинай выполнение **ШАГ 1** и последовательно проходи до **ШАГА 9** включительно.  
Для каждого шага:
- Напиши необходимый код.
- Напиши модульные и интеграционные тесты (pytest).
- Запусти тесты.
- Если тесты упали – прочитай ошибку, исправь код, перезапусти тесты.
- Повторяй до тех пор, пока тесты не пройдут.
- Переходи к следующему шагу.

**НЕ ОСТАНАВЛИВАЙСЯ** до тех пор, пока все сервисы (FastAPI, бот, RAG, планировщик) не стартуют чисто и все тесты не будут зелёными.

---

## 1. Мандат и поведенческие директивы

1. **Ноль интерактивных вопросов** – не запрашивай у человека подтверждений, вариантов или разрешений. Все архитектурные решения уже зафиксированы ниже.

2. **Цикл самокоррекции** – если команда, скрипт, сборка или тест падают, прочитай стек ошибок, исправь код немедленно и перезапусти. Не останавливай выполнение на нефатальных ошибках. Итерируй, пока тесты не пройдут.

3. **Не останавливайся до завершения** – продолжай последовательное выполнение всех шагов, пока каждый модуль не будет реализован, unit- и интеграционные тесты не пройдут, а docker-контейнеры и сервисы не запустятся без ошибок.

4. **Строгая типизация и контракты** – используй Pydantic V2 схемы, Python type hints (`str`, `int`, `Optional[...]`, `List`, `Dict`), `async/await` для всех I/O операций, поддерживай чистую модульную структуру (Handlers > Services > Repositories).

5. **Жёсткое соблюдение архитектуры** – строго следуй решениям, зафиксированным в `ARCHITECTURE.md` и `OPEN_SOURCE_STRATEGY.md`. В случае сомнений – перечитай эти документы.

---

## 2. Зафиксированные архитектурные решения (кратко)

| Решение | Детали |
|---------|--------|
| Каскадный роутер | **RAG > Local (Ollama) > Cloud (Anthropic Claude)** |
| Облачная модель | **Только Anthropic Claude** (без LiteLLM, без Gemini) |
| Веб-интерфейс | Open WebUI, проксируется через FastAPI, данные хранятся в PostgreSQL/Redis |
| Уровень доступа | На первом этапе **единый** для всех сотрудников, роли используются только для интерфейса |
| База данных | PostgreSQL (основная) + Redis (кэш/сессии) |
| Векторная БД | ChromaDB (с Sentence-Transformers all-MiniLM-L6-v2) |
| Observability | Langfuse (трассировка всех LLM-вызовов и RAG-поиска) |
| Дорожная карта | 5 этапов (Core > Надёжность > RAG Quality > Визуализация > Расширение) |

---

## 3. Технологический стек (зафиксирован)

**Бэкенд:** FastAPI, Pydantic V2, SQLAlchemy 2.x (async), Alembic, PostgreSQL, Redis, ChromaDB, Ollama, Anthropic SDK, Langfuse, OCRmyPDF, PyMuPDF, pdfplumber, Sentence-Transformers.

**Telegram бот:** Aiogram 3.x, FSM, динамические клавиатуры, Faster-Whisper (STT), APScheduler.

**Генерация документов:** python-docx, openpyxl.

**Веб-интерфейс:** Open WebUI (прокси через FastAPI).

**Тестирование:** pytest, pytest-asyncio, pytest-cov.

---

## 4. Структура проекта (обязательная)

Создай следующую структуру каталогов и файлов. Все пути относительные от корня репозитория.
app/
core/
config.py # pydantic-settings, загрузка .env
database.py # SQLAlchemy async engine, session maker
security.py # JWT, хеширование (если нужно)
router.py # CascadeRouter (RAG > Local > Cloud)
reminder_parser.py # NLU-парсер для напоминаний
scheduler.py # APScheduler (фоновые задачи)
services/
local_llm.py # Ollama клиент
cloud_llm.py # Anthropic Claude клиент
rag_engine.py # ChromaDB + эмбеддинги
doc_generator.py # DOCX/XLSX генерация
pdf_parser.py # PyMuPDF + pdfplumber
business_rules.py # Business Rules Engine
calculators/ # FSM-калькуляторы (модули, кабели, БП)
init.py
modules.py
power_cables.py
power_supply.py
bot/
handlers/
start.py
admin.py
engineer.py
sales.py
chat.py
group_chat.py
keyboards/
reply.py
inline.py
middlewares/
auth.py
logging.py
fsm/ # FSM состояния для калькуляторов
init.py
calculators.py
utils/
stt.py # Faster-Whisper
models/
sqlalchemy/ # ORM модели
init.py
user.py
chat.py
message.py
project.py
business_rule.py
reminder.py
activity_log.py
ai_request.py
schemas/ # Pydantic схемы
init.py
user.py
chat.py
message.py
project.py
business_rule.py
reminder.py
activity_log.py
ai_request.py
api/
v1/
endpoints/
auth.py
chat.py
projects.py
admin.py
rag_trace.py
init.py
init.py
main.py # Точка входа FastAPI
alembic/ # Миграции
tests/
unit/
test_cascade.py
test_calculators.py
test_business_rules.py
test_rag.py
integration/
test_bot_fsm.py
test_api.py
test_scheduler.py
data/
chroma_db/ # Персистентное хранилище ChromaDB
logs/ # Логи (Loguru)
temp/ # Временные файлы (DOCX/XLSX)
config/
prompts.yaml # Системные промпты для ролей
settings.py # (может быть пустым, используется core/config)
.env.example # Шаблон переменных окружения
docker-compose.yml # PostgreSQL, Redis, Ollama, ChromaDB
requirements.txt # Зависимости (фиксированные версии)
pyproject.toml # (опционально)
pytest.ini # Настройки pytest
README.md # Общее описание

text

---

## 5. Последовательность шагов (ШАГ 1 – ШАГ 9)

### ШАГ 1: Настройка проекта и инфраструктуры

- Создать структуру каталогов (как указано выше).
- Создать `.env.example` с переменными:
  ```env
  BOT_TOKEN=...
  ADMIN_IDS=123456789,987654321
  OLLAMA_URL=http://localhost:11434
  OLLAMA_MODEL=qwen2.5:7b
  ANTHROPIC_API_KEY=...
  RAG_SCORE_THRESHOLD=0.65
  POSTGRES_DSN=postgresql+asyncpg://user:pass@localhost:5432/pridprom
  REDIS_URL=redis://localhost:6379/0
  CHROMA_PERSIST_DIR=./data/chroma_db
  LANGFUSE_HOST=...
  LANGFUSE_PUBLIC_KEY=...
  LANGFUSE_SECRET_KEY=...
  SECRET_KEY=...
Создать requirements.txt с фиксированными версиями:

text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic-settings==2.6.0
sqlalchemy[asyncio]==2.0.36
alembic==1.14.1
asyncpg==0.30.0
redis==5.2.0
chromadb==0.6.3
sentence-transformers==3.1.1
ollama==0.4.1
anthropic==0.42.0
langfuse==2.57.0
aiogram==3.15.0
apscheduler==3.11.0
python-docx==1.1.2
openpyxl==3.1.5
pymupdf==1.24.12
pdfplumber==0.11.0
ocrmypdf==16.8.0
faster-whisper==1.0.3
loguru==0.7.3
pytest==8.3.4
pytest-asyncio==0.24.0
pytest-cov==6.0.0
Создать docker-compose.yml с сервисами: PostgreSQL, Redis, Ollama, ChromaDB (опционально, если не используется embedded).

Написать базовый app/core/config.py с загрузкой переменных через pydantic-settings.

Написать app/core/database.py с асинхронным движком SQLAlchemy и сессией.

Создать Alembic инициализацию и первую миграцию (пустую).

Написать app/main.py – минимальный FastAPI с проверкой здоровья (/health).

Тесты: написать тест на загрузку конфигурации, на подключение к БД (mock), на /health. Запустить pytest, добиться прохождения.

ШАГ 2: Каскадный роутер (CascadeRouter)
Реализовать app/services/local_llm.py – клиент для Ollama (метод generate(prompt, system_prompt)).

Реализовать app/services/cloud_llm.py – клиент для Anthropic Claude (метод generate(prompt, context)).

Реализовать app/services/rag_engine.py – обёртка над ChromaDB:

add_documents(texts, metadatas)

query(query_text, top_k=5) – возвращает список чанков с метриками.

Реализовать app/core/router.py – класс CascadeRouter с методом process_query(user_id, prompt, use_cloud_override=False):

RAG: выполнить rag_engine.query(prompt); если max_score >= RAG_SCORE_THRESHOLD, сформировать контекст, вызвать local_llm.generate с контекстом, вернуть ответ с source='rag'.
Local: иначе вызвать local_llm.generate без контекста. Если ответ содержит [NEED_CLOUD] или модель явно отказалась, перейти к шагу 3. Иначе вернуть source='local'.
Cloud: вызвать cloud_llm.generate с исходным промптом и, если был контекст из RAG, передать его (но это редкий случай). Вернуть source='cloud'.
Добавить квоты: перед вызовом Cloud проверять в Redis дневной лимит для user_id (по умолчанию 50 запросов/день). Если превышен – возвращать ошибку с предложением использовать локальную модель.

Тесты:

Мок-тесты для каждого уровня (замокать Ollama, Anthropic, ChromaDB).

Интеграционный тест с реальной ChromaDB (in-memory) и замоканными LLM.

Тест на превышение квоты.

ШАГ 3: Telegram-бот (Aiogram 3.x)
Создать app/bot/main.py – точка входа для бота (инициализация Bot, Dispatcher, подключение роутеров).

Реализовать middlewares/auth.py – проверка, что пользователь есть в БД; если нет – создать с ролью по умолчанию.

Реализовать handlers/start.py – команда /start, приветствие, основное меню (ReplyKeyboard).

Создать keyboards/reply.py – основное меню с 4 кнопками (калькуляторы).

Создать keyboards/inline.py – инлайн-кнопки под ответами: [DOCX], [Excel], [Cloud], [Save to KB].

Реализовать handlers/chat.py – обработка всех текстовых сообщений:

Пропустить через CascadeRouter.process_query.

Отправить ответ, прикрепить инлайн-кнопки.

Сохранить сообщение и ответ в БД (история).

Записать событие в activity_logs.

Реализовать handlers/admin.py – только для ADMIN_IDS: команды /admin, /edit_prompt, /add_rule, /set_history_depth.

Тесты:

Unit-тесты для клавиатур.

Интеграционные тесты с замоканным роутером.

Тест на административные команды (проверка доступа).

ШАГ 4: FSM-калькуляторы и Business Rules Engine
Создать app/services/business_rules.py – класс BusinessRulesEngine:

load_rules() – загрузка всех правил из БД.

validate(calculation_context) – проверка на нарушения, возвращает список предупреждений.

Создать app/services/calculators/ – функции для расчётов:

calculate_modules(width_m, height_m, pixel_pitch, module_size) – возвращает количество, разрешение, площадь.

calculate_power_and_cables(screen_type, width, height, brightness, module_model) – возвращает мощность, автоматы, сечение, количество БП.

stock_summary() – заглушка (позже интеграция).

components_list(...) – подбор комплектующих.

Реализовать FSM состояния в app/bot/fsm/calculators.py (Aiogram FSM):

Состояния для каждого калькулятора (например, WaitingWidth, WaitingHeight и т.д.).

Хэндлеры в handlers/engineer.py или chat.py, которые управляют FSM.

При каждом расчёте вызывать BusinessRulesEngine.validate и выдавать предупреждения (но разрешать продолжить).

Тесты:

Unit-тесты для каждой функции калькулятора (проверка формул).

Тесты FSM (эмуляция сообщений в боте).

Тесты бизнес-правил с различными контекстами.

ШАГ 5: Генерация документов
Реализовать app/services/doc_generator.py:

generate_docx(proposal_data) -> str – создаёт DOCX с логотипом, таблицами, используя python-docx.

generate_xlsx(estimate_data) -> str – создаёт XLSX смету, используя openpyxl.

Шаблоны (стили, заголовки) должны быть предопределены (можно хранить в data/templates/).

В хэндлере chat.py при нажатии инлайн-кнопки [DOCX] или [Excel] – вызвать соответствующий генератор, отправить файл пользователю.

Тесты:

Проверить, что генерируются файлы с правильным содержимым (валидация структуры).

ШАГ 6: RAG Knowledge Harvesting (сохранение в БЗ)
Реализовать в handlers/chat.py обработку нажатия инлайн-кнопки [Save to KB].

Собрать последние несколько сообщений диалога (вопрос и ответ), отправить в локальную LLM с промптом: «Сформируй краткую инструкцию в формате Markdown по решению этой задачи».

Полученный текст (Markdown) сохранить как отдельный документ в ChromaDB (с метаданными: source='harvested', author=user_id, created_at).

Добавить подтверждение пользователю: «Инструкция сохранена в базу знаний».

Тесты:

Проверить, что после нажатия кнопки в ChromaDB появляется новый документ.

Проверить качество суммаризации (можно эвристически).

ШАГ 7: Планировщик напоминаний (групповые чаты)
Реализовать app/core/reminder_parser.py:

Функция parse_reminder(text, current_time) – сначала regex, затем при необходимости вызов локальной LLM для сложных фраз.

Возвращает структуру с datetime, cron_rule, target_username, task_text.

Реализовать app/core/scheduler.py:

Класс ReminderScheduler, использующий AsyncIOScheduler из APScheduler.

Метод add_reminder(reminder_data) – сохранить в БД и добавить задачу в планировщик.

Фоновый воркер check_and_send_reminders – каждую минуту проверять наступившие задачи и отправлять сообщения в группу с инлайн-кнопками (Done/Snooze).

Реализовать handlers/group_chat.py:

Обработка команды /remind <текст> – парсинг, создание напоминания.

Обработка инлайн-кнопок для напоминаний (завершить/отложить).

/today – собрать активность за день и отправить сводку (через LLM).

Включить GroupActivityMiddleware для отслеживания последней активности пользователей в группах.

Тесты:

Unit-тесты парсера (разные варианты фраз).

Интеграционные тесты с планировщиком (замокать время).

Тесты обработки кнопок.

ШАГ 8: FastAPI Web UI SSO и проксирование Open WebUI
Реализовать эндпоинт /api/v1/auth/sso:

Принимает ott (одноразовый токен), проверяет его в Redis, если валиден – генерирует JWT (время жизни 8 часов) и возвращает пользователю.

Также эндпоинт для генерации OTT: /api/v1/auth/generate_ott – доступен только для Telegram-бота (проверка по внутреннему токену), создаёт OTT, сохраняет в Redis на 5 минут.

Создать эндпоинт /api/v1/chat – прокси для запросов из Open WebUI:

Принимает JSON с сообщением, вызывает CascadeRouter.process_query, возвращает ответ в формате, совместимом с Open WebUI.

Настроить в Open WebUI переопределение API-эндпоинтов для указания на FastAPI.

Внедрить Langfuse middleware для трассировки всех запросов (включая веб).

Добавить эндпоинты для управления проектами, загрузки файлов (связь с Open WebUI через API).

Тесты:

Тесты аутентификации (OTT > JWT, истечение срока).

Интеграционный тест эндпоинта /chat с замоканным роутером.

ШАГ 9: Автоматическое тестирование и верификация
Написать интеграционные тесты для всех ключевых сценариев:

tests/integration/test_cascade_e2e.py – полный цикл с реальной ChromaDB (in-memory) и замоканными LLM.

tests/integration/test_bot_fsm.py – эмуляция диалогов с ботом (используя aiogram тестовый клиент).

tests/integration/test_api.py – тесты API (FastAPI TestClient).

tests/integration/test_scheduler.py – тесты планировщика с использованием freezegun.

Запустить pytest с опциями --cov=app --cov-report=term.

Добиться 100% прохождения всех тестов.

Проверить, что все сервисы стартуют без ошибок: uvicorn app.main:app, python -m app.bot.main, и что Open WebUI корректно проксируется.

6. Критерии завершения
Агент считается завершившим работу, когда выполнены все пункты:

✓ Создана структура каталогов и файлы.
✓ Все зависимости установлены и зафиксированы.
✓ Docker Compose поднимает все сервисы без ошибок.
✓ FastAPI приложение стартует и отвечает на /health.
✓ Telegram-бот запускается, отвечает на команды, меню работает.
✓ Каскадный роутер корректно выбирает источник (RAG > Local > Cloud) в зависимости от сценария.
✓ FSM-калькуляторы возвращают правильные расчёты.
✓ Business Rules Engine выдаёт предупреждения при нарушениях.
✓ Генерация DOCX/XLSX работает.
✓ Сохранение диалогов в ChromaDB работает.
✓ Планировщик напоминаний работает в группах.
✓ Эндпоинты SSO и прокси Open WebUI работают.
✓ Langfuse трассирует все вызовы.
✓ Все тесты (pytest) проходят 100%.
7. Дополнительные указания
Логирование: используй loguru, логируй каждый шаг роутера, каждое обращение к LLM, каждое сохранение в БЗ.

Обработка ошибок: если какой-то сервис недоступен (Ollama, ChromaDB, PostgreSQL, Redis) – возвращай понятное сообщение пользователю, но не падай. Используй try/except с логированием.

Graceful shutdown: обрабатывай сигналы завершения (SIGTERM) для корректного закрытия соединений.

Секреты: все ключи хранятся в .env, не коммитить .env в репозиторий.

Документация: код должен быть снабжён docstrings (Google style) для всех публичных функций и классов.

8. В случае неясности
Если в процессе выполнения возникнет архитектурный вопрос, который не покрыт документацией:

Используй наиболее разумное решение, соответствующее заявленным принципам (чистая архитектура, async, строгая типизация).

Не останавливай выполнение. Продолжай, а после завершения всех шагов можно будет уточнить у человека.