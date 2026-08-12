# Развёртывание в production (Docker + VPN split-tunnel)

Пошаговая инструкция по установке Docker и запуску стека `docker-compose.prod.yml`
на сервере. Рассчитано на чистый Ubuntu 22.04/24.04 (или любой другой Linux
с systemd — команды установки Docker будут немного отличаться).

Минимальные требования к серверу: 4 vCPU / 8 GB RAM / 30+ GB диска (Ollama и
sentence-transformers прожорливы по памяти; на 4 GB будет тесно).

---

## 0. Если у вас чистая Windows (а не Linux-сервер)

Docker на Windows работает через **WSL2** (Windows Subsystem for Linux) — по
факту внутри поднимается настоящее Linux-ядро, и весь дальнейший гайд (шаги
1–9 ниже) выполняется **внутри WSL2**, а не в PowerShell. Это важно: команды
вроде `openssl`, `curl | sh`, `nano` в чистой PowerShell не работают так же,
как в bash, а в WSL2 — работают один в один как на Linux-сервере.

### 0.1 Проверить требования

- Windows 10 версии 2004+ (сборка 19041+) или Windows 11, 64-бит.
- Виртуализация включена в BIOS/UEFI (Intel VT-x / AMD-V). Проверить: диспетчер
  задач → вкладка «Производительность» → ЦП → строка «Виртуализация» должна
  быть «Включено».
- Права администратора на машине.

### 0.2 Установить WSL2 + Ubuntu

Открыть **PowerShell от имени администратора** (правой кнопкой на Пуск →
«Терминал (администратор)») и выполнить:

```powershell
wsl --install
```

Это одной командой включит нужные компоненты Windows, установит WSL2 и
поставит Ubuntu по умолчанию. Дальше — перезагрузка компьютера, если попросит.

После перезагрузки Ubuntu должна сама запуститься и попросить придумать
логин/пароль для пользователя внутри Linux (это отдельный логин, не от
Windows — любые, главное запомнить). Если не запустилась сама — найти в Пуске
приложение «Ubuntu» и открыть его.

Проверить версию WSL:

```powershell
wsl --version
wsl -l -v
```

В выводе `wsl -l -v` у Ubuntu должно быть `VERSION 2`, а не `1` — если `1`,
перевести: `wsl --set-version Ubuntu 2`.

### 0.3 Установить Docker Desktop

1. Скачать с [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
2. Запустить установщик. На экране настроек должна быть отмечена галка
   **«Use WSL 2 instead of Hyper-V»** — оставить как есть, это значение по
   умолчанию в современных версиях.
3. После установки — перезагрузка, если попросит.
4. Запустить Docker Desktop, дождаться, пока иконка кита в трее перестанет
   анимироваться (движок запустился).
5. Зайти в Docker Desktop → **Settings → Resources → WSL Integration** —
   убедиться, что переключатель напротив `Ubuntu` включён. Применить (Apply
   & Restart), если что-то меняли.

### 0.4 Дальше работать внутри Ubuntu (WSL2), а не в PowerShell

Открыть приложение **Ubuntu** из Пуска — откроется bash-терминал. Проверить,
что Docker виден изнутри WSL2 (он общий с Docker Desktop, отдельно
устанавливать не нужно):

```bash
docker --version
docker compose version
docker run --rm hello-world
```

Если всё вывелось без ошибок — переходите к шагу **2** этого документа
(«Получение кода») и далее выполняйте **все команды из этого гайда именно в
этом Ubuntu-терминале**. Шаг 1 («Установка Docker») на Windows не нужен —
Docker Desktop уже сделал его роль.

Единственная разница с реальным Linux-сервером: сама машина должна быть
включена и не уходить в сон, пока бот должен отвечать (в настройках
электропитания Windows отключить сон для «питание от сети», если это
рабочий ПК, а не выделенный сервер). Для по-настоящему постоянной работы
24/7 лучше всё-таки вынести на VPS с Ubuntu — Windows-машина для этого
стека больше подходит как окружение для тестирования перед боевым
разворачиванием.

---

## 1. Установка Docker (нативный Linux-сервер)

Пропустите этот шаг, если вы на Windows и уже прошли раздел 0 — Docker Desktop
уже установлен.

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker   # применить группу без перелогина

docker --version
docker compose version
```

Проверка, что всё встало:

```bash
docker run --rm hello-world
```

---

## 2. Получение кода

```bash
git clone https://github.com/tapokpy/ppai.git
cd ppai
git checkout claude/review-files-plan-rn4l2a   # или main, если PR уже смёржен
```

---

## 3. Настройка `.env`

```bash
cp .env.example .env
nano .env   # или любой другой редактор
```

Обязательно заполнить:

| Переменная | Где взять |
|---|---|
| `BOT_TOKEN` | у [@BotFather](https://t.me/BotFather) в Telegram |
| `ADMIN_IDS` | ваш Telegram ID (узнать через [@userinfobot](https://t.me/userinfobot)), через запятую если админов несколько |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `POSTGRES_PASSWORD` | придумать надёжный пароль |
| `SECRET_KEY` | случайная строка, например `openssl rand -hex 32` |
| `INTERNAL_API_TOKEN` | случайная строка, `openssl rand -hex 32` |

VPN-переменные (`VPN_ENDPOINT_IP` и т.д.) заполнять не нужно — по умолчанию
VPN отключён, см. раздел 6.1.

Остальные переменные (`OLLAMA_MODEL`, `RAG_SCORE_THRESHOLD`, `CLOUD_DAILY_LIMIT_PER_USER`
и т.д.) можно оставить по умолчанию — их удобнее подстраивать после первого
запуска, когда видно реальное поведение бота.

**Важно:** `.env` содержит секреты — он уже в `.gitignore`, не коммитьте его.

---

## 4. Сборка и запуск стека

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Это поднимет: `postgres`, `redis`, `ollama`, `api` (FastAPI), `bot` (Telegram),
`open-webui`, `portainer`. VPN (`gluetun`) по умолчанию **не** поднимается —
`api`/`bot` обращаются к Anthropic напрямую, без прокси (см. раздел 6.1, если
понадобится включить VPN позже).

Первая сборка `api`/`bot` займёт несколько минут (сборка образов + установка
зависимостей, включая тяжёлые `chromadb`/`sentence-transformers`).

Проверить, что всё поднялось:

```bash
docker compose -f docker-compose.prod.yml ps
```

Все сервисы должны быть `Up` (для `postgres`/`redis` — `healthy`).

---

## 5. Первоначальная настройка после запуска

### 5.1 Скачать модель для Ollama

Образ Ollama сам по себе не содержит весов модели — их нужно скачать один раз:

```bash
docker compose -f docker-compose.prod.yml exec ollama ollama pull qwen2.5:7b
```

Это несколько GB, может занять время в зависимости от канала сервера.

### 5.2 Применить миграции БД

`api` сервис уже применяет `alembic upgrade head` при каждом старте
(см. `Dockerfile.api`), так что отдельно это делать не нужно — но проверить
можно так:

```bash
docker compose -f docker-compose.prod.yml exec api alembic current
```

### 5.3 Одобрить себя как пользователя бота

Бот теперь не пускает никого, кроме одобренных пользователей. Если ваш
`ADMIN_IDS` уже настроен — вы одобряетесь автоматически при первом сообщении
боту. Если нужно одобрить кого-то ещё, из своего аккаунта в Telegram:

```
/add_user <telegram_id_пользователя>
```

---

## 6. Проверка, логи, диагностика

```bash
# статус и health всех контейнеров
docker compose -f docker-compose.prod.yml ps

# логи конкретного сервиса (Ctrl+C для выхода)
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs -f api

# health FastAPI напрямую с сервера
curl http://localhost:8000/health
```

Проверка каскада без VPN: сообщение боту в Telegram должно приходить и
отвечать (RAG/Ollama), а вопрос, требующий эскалации в Cloud, должен либо
получить ответ от Claude (прямое соединение, реальный IP сервера), либо, если
`ANTHROPIC_API_KEY` не задан/невалиден, вернуть сообщение "расширенный
облачный ответ сейчас недоступен" вместо падения — это ожидаемое поведение
graceful fallback, не баг.

---

## 6.1 Включение VPN (опционально, сейчас отключено)

По умолчанию `gluetun` не запускается, и Claude-трафик идёт напрямую. Когда
будет готов VPN-эндпоинт с обычным протоколом WireGuard (не обфусцированный
AmneziaWG — Gluetun его не понимает):

1. Добавьте в `.env`:
   ```
   VPN_ENDPOINT_IP=<IP сервера>
   VPN_ENDPOINT_PORT=<порт, обычно 51820>
   VPN_SERVER_PUBLIC_KEY=<PublicKey из секции [Peer]>
   VPN_CLIENT_PRIVATE_KEY=<PrivateKey из секции [Interface]>
   VPN_CLIENT_ADDRESS=<Address из секции [Interface], напр. 10.8.1.2/32>
   ```
2. В `docker-compose.prod.yml` верните в сервисы `api` и `bot`:
   ```yaml
   environment:
     ANTHROPIC_PROXY_URL: http://gluetun:8888
   depends_on:
     gluetun:
       condition: service_healthy
   ```
   (сейчас закомментировано/убрано намеренно — см. коммит "Disable VPN in the
   default prod stack for now").
3. Запустите с профилем VPN:
   ```bash
   docker compose -f docker-compose.prod.yml --profile vpn up -d --build
   ```
4. Проверка: `docker compose -f docker-compose.prod.yml logs gluetun` должен
   показать успешное поднятие WireGuard-туннеля; вопрос боту, уходящий в
   Cloud, должен получать ответ через `gluetun`, а не напрямую.

---

## 7. Открытые интерфейсы

| Сервис | Порт | Назначение |
|---|---|---|
| `api` (FastAPI) | `8000` | health-check, `/api/v1/*`, точка входа для Open WebUI |
| `frontend` | `8080` | RAG-панель (визуализация retrieval/трейсов/документов) — вход через `/dashboard` в Telegram |
| `open-webui` | `3000` | веб-чат для сотрудников |
| `portainer` | `9443` | мониторинг контейнеров (см. раздел 6 tech-спеки) |

**RAG-панель:** админ пишет боту `/dashboard`, получает одноразовую
ссылку (`WEB_DASHBOARD_URL/login?ott=...`, действует `OTT_EXPIRES_SECONDS`
секунд). Если браузер админа не на той же машине, что Docker-хост —
поправьте `WEB_DASHBOARD_URL` в `.env` на реально доступный адрес
(по умолчанию `http://localhost:8080`, что верно только для локального
доступа с самого хоста).

`postgres`, `redis`, `ollama` (и `gluetun`, если включите VPN) наружу не
публикуются — доступны только внутри Docker-сети, как и требовала
спецификация (изоляция инфраструктуры от внешнего мира).

**Для реального продакшена перед публикацией портов 8000/3000/9443 наружу
поставьте перед ними реверс-прокси с TLS** (Caddy/Traefik/nginx или встроенный
прокси Coolify, если разворачиваете через него) — сейчас в стеке HTTPS не
настроен, это осознанно оставлено на усмотрение вашей инфраструктуры
(Coolify обычно берёт эту задачу на себя автоматически).

---

## 8. Обновление после нового PR/релиза

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Alembic-миграции применятся автоматически при старте `api`. Данные в
`postgres_data`, `redis_data`, `ollama_data`, `app_data` (включая
персистентную RAG-базу Chroma) сохраняются между перезапусками — это именованные
Docker-тома, `down` без `-v` их не удаляет.

---

## 9. Известные ограничения этого стека (см. также PR #1)

- **VPN отключён по умолчанию.** Самостоятельно поднятый сервер оказался на
  протоколе AmneziaWG (обфусцированный WireGuard), который `gluetun` не
  поддерживает. Пока используется прямое соединение с Anthropic API; см.
  раздел 6.1 про включение VPN, когда будет готов эндпоинт на обычном
  WireGuard.
- `api` и `bot` пишут в один и тот же embedded Chroma-каталог через общий том
  `app_data`. Конкурентная запись из двух процессов одновременно — риск
  (embedded Chroma не рассчитан на multi-writer). Пока оба сервиса не пишут
  в RAG одновременно интенсивно — не критично; при росте нагрузки следующий
  шаг — вынести Chroma в отдельный сервер (`HttpClient` вместо
  `PersistentClient`).
- HTTPS/реверс-прокси не входит в этот compose-файл (см. раздел 7).
- Self-hosted Langfuse не включён — используется облачный `LANGFUSE_HOST`,
  если задан; для полностью локальной обсервабилити потребуется отдельный
  compose-стек Langfuse (свои Postgres/ClickHouse/MinIO).
