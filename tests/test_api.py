"""Интеграционные тесты REST API через httpx + ASGITransport."""


import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Base


TEST_DATABASE_URL = "sqlite+aiosqlite://"

# Создаём engine один раз и переопределяем get_db для тестов
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db() -> AsyncSession:  # type: ignore[misc]
    async with test_session_factory() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncSession:  # type: ignore[misc]
    """Создать таблицы перед каждым тестом и очистить после."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncClient:  # type: ignore[misc]
    """HTTP-клиент, подключённый к FastAPI приложению."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Хелперы ─────────────────────────────────────────────────


async def _create_employee(client: AsyncClient, name: str, email: str) -> dict:
    r = await client.post("/employees", json={"name": name, "email": email})
    assert r.status_code == 201, r.text
    return r.json()


async def _create_meeting(
    client: AsyncClient,
    title: str,
    start: str,
    end: str,
    created_by: int,
    participant_ids: list[int],
    expected_status: int = 201,
) -> dict:
    r = await client.post(
        "/meetings",
        json={
            "title": title,
            "start_time": start,
            "end_time": end,
            "created_by": created_by,
            "participant_ids": participant_ids,
        },
    )
    assert r.status_code == expected_status, r.text
    return r.json()


# ── Тесты создания сотрудника ───────────────────────────────


@pytest.mark.asyncio
async def test_create_employee(client: AsyncClient):
    emp = await _create_employee(client, "Alice", "alice@example.com")
    assert emp["id"] == 1
    assert emp["name"] == "Alice"
    assert emp["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_list_employees(client: AsyncClient):
    """GET /employees возвращает всех сотрудников."""
    await _create_employee(client, "Alice", "alice@example.com")
    await _create_employee(client, "Bob", "bob@example.com")

    r = await client.get("/employees")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    names = {e["name"] for e in data}
    assert names == {"Alice", "Bob"}


@pytest.mark.asyncio
async def test_create_employee_duplicate_email(client: AsyncClient):
    """Создание сотрудника с уже существующим email — 409."""
    await _create_employee(client, "Alice", "alice@example.com")

    r = await client.post("/employees", json={"name": "Alice Again", "email": "alice@example.com"})
    assert r.status_code == 409
    assert "alice@example.com" in r.json()["detail"]


# ── Тесты создания встречи ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_meeting_success(client: AsyncClient):
    alice = await _create_employee(client, "Alice", "alice@example.com")
    bob = await _create_employee(client, "Bob", "bob@example.com")

    meeting = await _create_meeting(
        client,
        "Standup",
        "2026-01-15T10:00:00",
        "2026-01-15T10:30:00",
        alice["id"],
        [alice["id"], bob["id"]],
    )

    assert meeting["title"] == "Standup"
    assert len(meeting["participants"]) == 2
    participant_names = {p["name"] for p in meeting["participants"]}
    assert participant_names == {"Alice", "Bob"}


@pytest.mark.asyncio
async def test_create_meeting_conflict_409(client: AsyncClient):
    alice = await _create_employee(client, "Alice", "alice@example.com")

    # Первая встреча
    await _create_meeting(
        client, "First", "2026-01-15T10:00:00", "2026-01-15T11:00:00", alice["id"], [alice["id"]]
    )

    # Вторая встреча с пересечением — ждём 409
    r = await client.post(
        "/meetings",
        json={
            "title": "Second",
            "start_time": "2026-01-15T10:30:00",
            "end_time": "2026-01-15T11:30:00",
            "created_by": alice["id"],
            "participant_ids": [alice["id"]],
        },
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Alice" in detail
    assert "First" in detail


@pytest.mark.asyncio
async def test_create_meeting_adjacent_ok(client: AsyncClient):
    """Встреча впритык — 201, не 409."""
    alice = await _create_employee(client, "Alice", "alice@example.com")

    await _create_meeting(
        client, "First", "2026-01-15T10:00:00", "2026-01-15T10:30:00", alice["id"], [alice["id"]]
    )

    # Следующая начинается ровно когда первая заканчивается
    meeting = await _create_meeting(
        client, "Second", "2026-01-15T10:30:00", "2026-01-15T11:00:00", alice["id"], [alice["id"]]
    )
    assert meeting["title"] == "Second"


# ── Тесты получения встреч ──────────────────────────────────


@pytest.mark.asyncio
async def test_get_meetings_by_day(client: AsyncClient):
    alice = await _create_employee(client, "Alice", "alice@example.com")

    await _create_meeting(
        client, "Morning", "2026-01-15T09:00:00", "2026-01-15T10:00:00", alice["id"], [alice["id"]]
    )
    await _create_meeting(
        client, "Afternoon", "2026-01-15T14:00:00", "2026-01-15T15:00:00", alice["id"], [alice["id"]]
    )

    r = await client.get("/meetings?date=2026-01-15")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    titles = {m["title"] for m in data}
    assert titles == {"Morning", "Afternoon"}


@pytest.mark.asyncio
async def test_get_meetings_by_day_empty(client: AsyncClient):
    r = await client.get("/meetings?date=2026-01-15")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_meetings_by_week(client: AsyncClient):
    alice = await _create_employee(client, "Alice", "alice@example.com")

    # Понедельник
    await _create_meeting(
        client, "Mon", "2026-01-12T10:00:00", "2026-01-12T11:00:00", alice["id"], [alice["id"]]
    )
    # Четверг
    await _create_meeting(
        client, "Thu", "2026-01-15T14:00:00", "2026-01-15T15:00:00", alice["id"], [alice["id"]]
    )

    r = await client.get("/meetings?week_start=2026-01-12")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    titles = {m["title"] for m in data}
    assert titles == {"Mon", "Thu"}


@pytest.mark.asyncio
async def test_get_meetings_no_params_400(client: AsyncClient):
    r = await client.get("/meetings")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_meetings_both_params_400(client: AsyncClient):
    r = await client.get("/meetings?date=2026-01-15&week_start=2026-01-12")
    assert r.status_code == 400


# ── Тесты расписания сотрудника ─────────────────────────────


@pytest.mark.asyncio
async def test_get_employee_meetings(client: AsyncClient):
    alice = await _create_employee(client, "Alice", "alice@example.com")
    bob = await _create_employee(client, "Bob", "bob@example.com")

    # Встреча 1 — только Alice
    await _create_meeting(
        client, "Alice solo", "2026-01-15T10:00:00", "2026-01-15T11:00:00", alice["id"], [alice["id"]]
    )
    # Встреча 2 — оба
    await _create_meeting(
        client, "Both", "2026-01-15T14:00:00", "2026-01-15T15:00:00", alice["id"], [alice["id"], bob["id"]]
    )

    r = await client.get(f"/employees/{alice['id']}/meetings")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    titles = {m["title"] for m in data}
    assert titles == {"Alice solo", "Both"}