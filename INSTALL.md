# Установка и настройка ppai — пошаговая инструкция

Эта инструкция рассчитана на то, что вы устанавливаете проект **с нуля на новом
компьютере**, без чьей-либо помощи. Написана по мотивам реальной установки —
включает все проблемы, которые встретились по пути, и как их решить.

Подходит для Windows 10/11. Если ставите на Linux-сервер — читайте
[DEPLOYMENT.md](DEPLOYMENT.md), там инструкция для «чистого» Ubuntu.

---

## Что это такое

`ppai` — ИИ-ассистент для расчётов и консультаций: Telegram-бот +
веб-интерфейс, с каскадом «своя база знаний (RAG) → локальная модель (Ollama)
→ облачная модель (Claude)». Весь стек разворачивается через Docker —
устанавливать Python, PyMuPDF, Tesseract и прочее вручную не нужно, всё это
уже упаковано в образы.

---

## Системные требования

- Windows 10 (сборка 19041+) или Windows 11, 64-бит — либо Linux с Docker.
- **Минимум 60 ГБ свободного места на диске.** Это не опечатка — образы
  проекта тянут за собой PyTorch, CUDA-библиотеки, ChromaDB и модели
  распознавания речи, только `api`+`bot` образы занимают ~15-20 ГБ, плюс
  модель Ollama (~4-5 ГБ), плюс сам Docker съедает место под свои служебные
  файлы. **Если на системном диске (обычно `C:`) свободно меньше 60 ГБ —
  сразу планируйте разместить Docker на другом диске (шаг 3.3 ниже),
  иначе упрётесь в «Device or resource busy» / «read-only file system»
  посреди установки, как это случилось у нас.**
- 8+ ГБ RAM (лучше 16, особенно если Ollama будет работать с моделью 7B).
- Включена виртуализация в BIOS/UEFI (Intel VT-x или AMD-V) — без неё Docker
  не запустится вообще. Проверяется и включается на шаге 1.
- Права администратора на компьютере.

---

## Шаг 1. Проверить и включить виртуализацию

Откройте PowerShell (не обязательно от администратора) и выполните:

```powershell
systeminfo | findstr /C:"Virtualization Enabled In Firmware"
```

Если видите `Virtualization Enabled In Firmware: No` — виртуализация выключена
в BIOS, без этого шага Docker Desktop откажется запускаться с ошибкой
**«Virtualization support not detected»**. Включается так:

1. Перезагрузите компьютер.
2. Сразу после включения, до логотипа Windows, начните повторно нажимать
   клавишу входа в BIOS. Клавиша зависит от производителя:

   | Производитель | Клавиша |
   |---|---|
   | Gigabyte, ASUS, MSI | `Del` |
   | Dell | `F2` (иногда `F12` для меню загрузки) |
   | HP | `F10` или `Esc` |
   | Lenovo | `F1` или `F2` |
   | Acer | `F2` или `Del` |
   | Не знаете/не подошло | Попробуйте `Del`, затем `F2`, затем `Esc` |

3. В BIOS найдите пункт (называется по-разному в зависимости от платы):
   - На платах с процессором **AMD**: `SVM Mode`
   - На платах с процессором **Intel**: `Intel Virtualization Technology` /
     `Intel VT-x`
   - Обычно лежит на вкладке **"BIOS Features"**, **"Advanced"** или
     **"CPU Configuration"**. Если в BIOS есть поиск (значок лупы) — наберите
     `virtualization` или `SVM`.
4. Выставьте значение **Enabled**.
5. Сохраните и выйдите: обычно клавиша **F10** → подтвердить **Yes**.

После перезагрузки повторите команду `systeminfo` выше — должно появиться
`A hypervisor has been detected` вместо `No`.

---

## Шаг 2. Установить WSL2

Откройте **PowerShell от имени администратора** (правый клик на Пуск →
«Терминал (администратор)»):

```powershell
wsl --install
```

Перезагрузите компьютер, если попросит. Проверка:

```powershell
wsl --version
```

Должна показать номер версии (не ошибку про «не установлено»). Отдельный
Linux-дистрибутив (Ubuntu и т.п.) ставить не обязательно — Docker Desktop
создаст свои служебные WSL-окружения сам.

---

## Шаг 3. Установить Docker Desktop

### 3.1 Установка

```powershell
winget install -e --id Docker.DockerDesktop
```

Если команда выполнилась, но `docker --version` потом не находится —
скорее всего, установка прошла без прав администратора и Docker встал не в
`C:\Program Files\Docker`, а в личную папку пользователя
(`%LOCALAPPDATA%\Programs\DockerDesktop`). Это не страшно, просто откройте
**новое** окно PowerShell (переменные PATH подхватятся) и проверьте снова:

```powershell
docker --version
docker compose version
```

Если winget не сработал вообще — скачайте установщик вручную:
[desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe](https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe)
и запустите как обычную программу (правой кнопкой → «Запуск от имени
администратора», если спросит).

### 3.2 Первый запуск

Запустите Docker Desktop из Пуска. Дождитесь, пока иконка кита в трее
перестанет анимироваться. Если сразу видите красный экран с ошибкой про
виртуализацию — вернитесь к шагу 1, вы что-то пропустили.

### 3.3 Важно: разместите диск Docker там, где есть место

**Сделайте это ДО того, как начнёте собирать образы проекта**, иначе
придётся переносить уже заполненный диск (это долго и рискованно, мы сами
через это прошли).

1. Docker Desktop → шестерёнка **⚙ Settings** (правый верхний угол).
2. **Resources → Advanced**.
3. Поле **"Disk image location"** → **Browse** → выберите папку на диске,
   где есть минимум 60 ГБ свободного места (например, `D:\DockerData`).
4. **Apply & Restart**.

Если у вас единственный диск и на нём объективно мало места — освободите
место (проверить, что занимает больше всего:
`Get-ChildItem "$env:LOCALAPPDATA" -Directory | ForEach-Object {[PSCustomObject]@{Folder=$_.Name; GB=[math]::Round((Get-ChildItem $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1GB,2)}} | Sort GB -Descending | Select -First 10`
в PowerShell), это первое, на что стоит смотреть, если Docker внезапно
перестал что-либо запускать с ошибками про диск.

---

## Шаг 4. Установить Git

```powershell
winget install -e --id Git.Git
```

При установке на экране про line endings выберите вариант по умолчанию
(**"Checkout Windows-style, commit Unix-style line endings"**).

Проверка:

```powershell
git --version
```

---

## Шаг 5. Получить код проекта

```powershell
mkdir C:\ppai
cd C:\ppai
git clone https://github.com/tapokpy/ppai.git .
git checkout claude/review-files-plan-rn4l2a
```

(Замените адрес репозитория, если вы клонируете из другого места, например
`https://github.com/tapokpy/ppai2.1.git` — там уже основная ветка `main`, чекаут
не нужен.)

---

## Шаг 6. Настроить `.env`

```powershell
copy .env.example .env
```

Откройте `.env` любым текстовым редактором и заполните:

| Переменная | Обязательна? | Где взять |
|---|---|---|
| `BOT_TOKEN` | Да | Telegram → [@BotFather](https://t.me/BotFather) → `/newbot` |
| `ADMIN_IDS` | Да | Ваш числовой Telegram ID — узнать у [@userinfobot](https://t.me/userinfobot) (`/start`). Можно несколько через запятую |
| `SECRET_KEY` | Да | Случайная строка. В PowerShell: `[guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()` |
| `INTERNAL_API_TOKEN` | Да | Аналогично, другая случайная строка |
| `ANTHROPIC_API_KEY` | Нет | [console.anthropic.com](https://console.anthropic.com/settings/keys). **Можно оставить пустым** — бот будет работать через базу знаний и локальную модель (Ollama), а на вопросы, требующие облака, вежливо ответит, что расширенный ответ временно недоступен, вместо ошибки |
| `POSTGRES_PASSWORD` | Да (для Docker-стека) | Придумайте сами, надёжный пароль. В `.env.example` этой строки нет — допишите вручную: `POSTGRES_PASSWORD=...` |

VPN-переменные (`VPN_ENDPOINT_IP` и т.д.) трогать не нужно — VPN в проекте
сейчас выключен по умолчанию (см. раздел про VPN в
[DEPLOYMENT.md](DEPLOYMENT.md), если понадобится включить позже).

Остальные переменные (`OLLAMA_MODEL`, `RAG_SCORE_THRESHOLD` и т.д.) можно
оставить как есть.

**`.env` содержит секреты — он уже в `.gitignore`, никогда его не коммитьте.**

---

## Шаг 7. Собрать и запустить

```powershell
cd C:\ppai
docker compose -f docker-compose.prod.yml up -d --build
```

Первая сборка займёт долго (10-25 минут в зависимости от скорости интернета
и мощности машины) — качаются и собираются тяжёлые зависимости. Это
нормально, дайте команде отработать до конца.

Проверить, что всё поднялось:

```powershell
docker compose -f docker-compose.prod.yml ps
```

`postgres` и `redis` должны быть в статусе `healthy`, остальные — `Up`.

### 7.1 Скачать модель для Ollama

Сам Docker-образ Ollama пустой, модель нужно скачать один раз внутрь него:

```powershell
docker compose -f docker-compose.prod.yml exec ollama ollama pull qwen2.5:7b
```

Это ~4-5 ГБ, тоже может занять время.

### 7.2 Проверить, что API отвечает

```powershell
curl http://localhost:8000/health
```

Ожидается: `{"status":"ok","database":true}`.

### 7.3 Одобрить себя как администратора бота

Если ваш Telegram ID уже стоит в `ADMIN_IDS` — вы одобряетесь автоматически
при первом сообщении боту. Проверить: напишите боту `/start` в Telegram, он
должен ответить (а не написать про «доступ ограничен»).

Чтобы одобрить кого-то ещё, напишите боту от своего (админского) аккаунта:

```
/add_user <telegram_id_пользователя>
```

---

## Проверка, что всё работает

- `http://localhost:3000` — веб-интерфейс (Open WebUI).
- `http://localhost:9443` — Portainer (мониторинг контейнеров).
- Напишите боту в Telegram что-нибудь простое — должен ответить.
- Попробуйте калькулятор (кнопка в меню бота) — должен посчитать и предложить
  выгрузить DOCX/Excel.

---

## Частые проблемы

| Симптом | Причина и решение |
|---|---|
| Docker Desktop: «Virtualization support not detected» | Виртуализация выключена в BIOS — см. шаг 1. |
| `docker` не находится в PowerShell после установки | Установка прошла в папку пользователя, а не Program Files — откройте **новое** окно PowerShell, PATH обновится. |
| При сборке/запуске ошибка `read-only file system` или `Device or resource busy` внутри Docker | Кончилось место на диске, где лежит файл Docker (`docker_data.vhdx`). Проверьте `Get-PSDrive C` в PowerShell — если `Free` близко к нулю, перенесите диск Docker на другой раздел (шаг 3.3) или освободите место. |
| `docker compose up` падает с `required variable ... is missing a value` про `VPN_*` | Не должно происходить в текущей версии стека (VPN-переменные без `:?required`), но если видите — значит используется старая версия `docker-compose.prod.yml`, обновите репозиторий (`git pull`). |
| Бот не отвечает вообще, пишет «доступ ограничен» | Это новая система контроля доступа — нужно одобрить пользователя через `/add_user`, см. шаг 7.3. |
| Вопрос, требующий Cloud, отвечает «расширенный облачный ответ сейчас недоступен» | `ANTHROPIC_API_KEY` не задан или неверный — это ожидаемое поведение (graceful fallback), а не баг. Впишите рабочий ключ в `.env` и перезапустите `api`/`bot`: `docker compose -f docker-compose.prod.yml restart api bot`. |

---

## Полезные команды на каждый день

```powershell
# статус контейнеров
docker compose -f docker-compose.prod.yml ps

# логи (Ctrl+C для выхода)
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs -f api

# перезапуск после правки .env
docker compose -f docker-compose.prod.yml restart api bot

# обновление до последней версии кода
git pull
docker compose -f docker-compose.prod.yml up -d --build

# полная остановка
docker compose -f docker-compose.prod.yml down

# остановка с удалением данных (БД, RAG-база, модель Ollama) — осторожно!
docker compose -f docker-compose.prod.yml down -v
```

---

## Дальнейшее чтение

- [DEPLOYMENT.md](DEPLOYMENT.md) — тот же процесс для Linux-сервера, плюс
  включение VPN (split-tunnel только для запросов к Claude).
- [ARCHITECTURE.md](ARCHITECTURE.md) — как всё устроено внутри.
