"""Юнит-тесты на функцию has_conflict (проверка пересечений слотов)."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.conflicts import has_conflict
from app.models import Base, Employee, Meeting

# Используем SQLite в памяти для изоляции тестов
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture
async def db_session() -> AsyncSession:  # type: ignore[misc]
    """Сессия с in-memory SQLite и созданными таблицами."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_employee(db: AsyncSession, name: str, email: str) -> Employee:
    e = Employee(name=name, email=email)
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


# ── Тесты ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_conflict_when_no_meetings(db_session: AsyncSession):
    """Пустая БД — конфликта нет."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")
    has, desc = await has_conflict(
        db_session,
        [alice.id],
        datetime(2026, 1, 15, 10, 0, 0),
        datetime(2026, 1, 15, 11, 0, 0),
    )
    assert not has
    assert desc is None


@pytest.mark.asyncio
async def test_full_overlap_conflict(db_session: AsyncSession):
    """Полное вложение новой встречи в существующую — конфликт."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")

    # Существующая встреча Alice 10:00–12:00
    existing = Meeting(
        title="Existing",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 12, 0, 0),
        created_by=alice.id,
        participants=[alice],
    )
    db_session.add(existing)
    await db_session.commit()

    # Новая встреча 10:30–11:30 — полностью внутри существующей
    has, desc = await has_conflict(
        db_session,
        [alice.id],
        datetime(2026, 1, 15, 10, 30, 0),
        datetime(2026, 1, 15, 11, 30, 0),
    )
    assert has
    assert desc is not None
    assert "Alice" in desc


@pytest.mark.asyncio
async def test_partial_overlap_conflict(db_session: AsyncSession):
    """Частичное пересечение — новая начинается во время старой — конфликт."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")

    existing = Meeting(
        title="Existing",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 11, 0, 0),
        created_by=alice.id,
        participants=[alice],
    )
    db_session.add(existing)
    await db_session.commit()

    # Новая встреча 10:30–11:30 — частичное пересечение
    has, desc = await has_conflict(
        db_session,
        [alice.id],
        datetime(2026, 1, 15, 10, 30, 0),
        datetime(2026, 1, 15, 11, 30, 0),
    )
    assert has
    assert "Alice" in (desc or "")


@pytest.mark.asyncio
async def test_adjacent_meetings_not_conflict(db_session: AsyncSession):
    """Встречи впритык (10:00–10:30 и 10:30–11:00) — НЕ конфликт."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")

    existing = Meeting(
        title="First",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 10, 30, 0),
        created_by=alice.id,
        participants=[alice],
    )
    db_session.add(existing)
    await db_session.commit()

    # Новая начинается ровно когда старая заканчивается
    has, desc = await has_conflict(
        db_session,
        [alice.id],
        datetime(2026, 1, 15, 10, 30, 0),
        datetime(2026, 1, 15, 11, 0, 0),
    )
    assert not has
    assert desc is None


@pytest.mark.asyncio
async def test_different_participants_not_conflict(db_session: AsyncSession):
    """Разные участники в то же время — НЕ конфликт."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")
    bob = await _create_employee(db_session, "Bob", "bob@example.com")

    # Встреча Alice
    existing = Meeting(
        title="Alice meeting",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 11, 0, 0),
        created_by=alice.id,
        participants=[alice],
    )
    db_session.add(existing)
    await db_session.commit()

    # Встреча Bob в то же время
    has, desc = await has_conflict(
        db_session,
        [bob.id],
        datetime(2026, 1, 15, 10, 0, 0),
        datetime(2026, 1, 15, 11, 0, 0),
    )
    assert not has
    assert desc is None


@pytest.mark.asyncio
async def test_same_employee_two_meetings_no_conflict(db_session: AsyncSession):
    """Один сотрудник в двух непересекающихся встречах — НЕ конфликт."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")

    existing = Meeting(
        title="Morning",
        start_time=datetime(2026, 1, 15, 9, 0, 0),
        end_time=datetime(2026, 1, 15, 10, 0, 0),
        created_by=alice.id,
        participants=[alice],
    )
    db_session.add(existing)
    await db_session.commit()

    # Послеобеденная встреча, не пересекается
    has, desc = await has_conflict(
        db_session,
        [alice.id],
        datetime(2026, 1, 15, 14, 0, 0),
        datetime(2026, 1, 15, 15, 0, 0),
    )
    assert not has
    assert desc is None


@pytest.mark.asyncio
async def test_exclude_meeting_id(db_session: AsyncSession):
    """При обновлении своей же встречи exclude_meeting_id исключает её из проверки."""
    alice = await _create_employee(db_session, "Alice", "alice@example.com")

    existing = Meeting(
        title="Update me",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 11, 0, 0),
        created_by=alice.id,
        participants=[alice],
    )
    db_session.add(existing)
    await db_session.commit()

    # Тот же слот, но с exclude_meeting_id — конфликта нет
    has, desc = await has_conflict(
        db_session,
        [alice.id],
        datetime(2026, 1, 15, 10, 0, 0),
        datetime(2026, 1, 15, 11, 0, 0),
        exclude_meeting_id=existing.id,
    )
    assert not has
    assert desc is None