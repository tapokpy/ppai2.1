# ppai — ИИ-ассистент для инженеров и продажников

Корпоративный ИИ-ассистент: каскадная маршрутизация запросов (RAG → локальная LLM → облачная LLM), Telegram-бот, веб-интерфейс, генерация коммерческих документов и работа с базой знаний.

## Статус

Проект в разработке, сессия 1 из 4 (см. план в issue/переписке):

- [x] Шаг 1 — каркас проекта: `app/core/config.py`, `app/core/database.py`, `app/main.py` (`/health`), Alembic, docker-compose (Postgres/Redis/Ollama)
- [x] Шаг 2 — Cascade Router: `app/services/local_llm.py`, `app/services/cloud_llm.py`, `app/services/rag_engine.py`, `app/core/router.py`
- [ ] Шаг 3 — Telegram-бот (Aiogram)
- [ ] Шаг 4 — FSM-калькуляторы + Business Rules Engine
- [ ] Шаг 5 — генерация DOCX/XLSX
- [ ] Шаг 6 — RAG Knowledge Auto-Harvesting
- [ ] Шаг 7 — напоминания (NLU + APScheduler)
- [ ] Шаг 8 — FastAPI SSO + Open WebUI
- [ ] Шаг 9 — интеграционные тесты, финальная проверка

## Архитектура каскадной маршрутизации

1. **RAG** — поиск в ChromaDB; если релевантность ≥ `RAG_SCORE_THRESHOLD` (по умолчанию 0.65), контекст передаётся локальной модели.
2. **Local** — Ollama (`qwen2.5:7b`); если модель не может ответить (маркер `[NEED_CLOUD]` или ошибка), запрос уходит дальше.
3. **Cloud** — Anthropic Claude, с суточным лимитом на пользователя (Redis), деградирует до отказа с понятным сообщением при превышении лимита.

## Быстрый старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить BOT_TOKEN, ANTHROPIC_API_KEY и т.д.

docker compose up -d postgres redis   # или локальные Postgres/Redis
alembic upgrade head

uvicorn app.main:app --reload
```

Проверка: `curl http://localhost:8000/health`

## Тесты

```bash
pytest --cov=app --cov-report=term
```

Интеграционные тесты, требующие реального Postgres/Redis, автоматически пропускаются (`skip`), если сервисы недоступны — см. `tests/integration/conftest.py`.

## Документация

| Файл | Описание |
|------|----------|
| `ARCHITECTURE.md` | Полная архитектура: backend, бот, Web UI, бизнес-модули |
| `OPEN_SOURCE_STRATEGY.md` | Выбор Open Source компонентов, стратегия RAG |
| `AUTONOMOUS_EXECUTION.md` | Пошаговый план разработки (9 шагов) |
| `DEVELOPMENT_TOOLS.md` | Code-review агент, `.claude/skills/` |
