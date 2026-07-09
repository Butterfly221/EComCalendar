# Meeting Scheduler — тестовое задание AI Developer

Сервис бронирования встреч между сотрудниками с проверкой пересечений слотов.
Уровень A (MVP): REST API + SQLite + проверка конфликтов + тесты.

## Быстрый старт

```bash
# 1. Склонировать и перейти в папку
cd EComCalendar

# 2. Создать .env (опционально, для теста не требуется)
cp .env.example .env

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Запустить сервер
uvicorn app.main:app --reload

# 5. Swagger UI
# http://127.0.0.1:8000/docs
```

## Тесты

```bash
pytest tests/ -v        # 18 тестов
ruff check .            # линтер — без ошибок
```

## API

### POST /employees — создать сотрудника
```bash
curl -X POST http://127.0.0.1:8000/employees \
  -H 'Content-Type: application/json' \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

### POST /meetings — создать встречу
```bash
curl -X POST http://127.0.0.1:8000/meetings \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Standup",
    "start_time": "2026-01-15T10:00:00",
    "end_time": "2026-01-15T10:30:00",
    "created_by": 1,
    "participant_ids": [1, 2]
  }'
```
Ответ 409 при конфликте:
```json
{"detail": "У сотрудника(ов) Alice уже есть встреча 'First' (2026-01-15 10:00:00 — 2026-01-15 11:00:00)"}
```

### GET /employees — список сотрудников
```bash
curl http://127.0.0.1:8000/employees
```

### GET /meetings?date=YYYY-MM-DD — встречи на день
```bash
curl http://127.0.0.1:8000/meetings?date=2026-01-15
```

### GET /meetings?week_start=YYYY-MM-DD — встречи на неделю
```bash
curl http://127.0.0.1:8000/meetings?week_start=2026-01-12
```
Неделя — от понедельника `week_start` до `week_start + 7 дней`.

### GET /employees/{id}/meetings — расписание сотрудника
```bash
curl http://127.0.0.1:8000/employees/1/meetings
```

## Модель данных

| Таблица | Поля |
|---|---|
| Employee | id, name, email |
| Meeting | id, title, start_time (UTC), end_time (UTC), created_by (FK→Employee) |
| MeetingParticipant | meeting_id (FK), employee_id (FK) — связь many-to-many |

## Известные допущения

1. **Гонки при параллельных запросах** — известное ограничение MVP. При одновременном создании встреч с пересекающимися слотами возможна ситуация, когда оба запроса пройдут проверку конфликтов до коммита. В продакшене: пессимистическая блокировка (SELECT FOR UPDATE) или уникальный констрейнт на уровне БД.
2. **Аутентификация и регистрация** — не реализованы, это тестовое задание, не продукт. Сотрудники создаются через POST /employees без авторизации.
3. **Временная зона** — всё хранится в UTC. Конвертация в MSK на клиенте/границе API не делается, т.к. клиент сам передаёт время в UTC. При необходимости — добавить pydantic validator на выходе.
4. **Миграция на Postgres** — заменить `DATABASE_URL` в `.env` на `postgresql+asyncpg://...`, SQLAlchemy-код написан без SQLite-специфичных хаков.
5. **Понедельник — начало недели** — как указано в AGENTS.md. Функция `get_meetings_for_week` принимает дату понедельника и возвращает встречи за 7 дней.
6. **Empty participant list** — схема `MeetingCreate.participant_ids` требует `min_length=1`, пустой список отвергается на уровне Pydantic.
7. **Создатель встречи не обязан быть участником** — `created_by` не добавляется автоматически в `participant_ids`. Это позволяет создавать встречи для других людей (аналог роли админа в будущем).

## Стек

- Python 3.12, FastAPI 0.115, Pydantic v2
- SQLite + SQLAlchemy 2.0 (async)
- pytest + httpx (ASGITransport)
- ruff, black

## Структура проекта

```
app/
  main.py            # FastAPI приложение, роуты
  models.py          # SQLAlchemy модели
  schemas.py         # Pydantic схемы
  crud.py            # бизнес-логика работы с БД
  conflicts.py       # проверка пересечений слотов
  database.py        # engine, session, настройки
tests/
  test_conflicts.py  # юнит-тесты has_conflict (7)
  test_api.py        # интеграционные тесты API (10)
README.md
PLAN.md
AGENTS.md
GUARDRAILS.md
requirements.txt
.env.example
pytest.ini