from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.conflicts import has_conflict
from app.models import Employee, Meeting
from app.schemas import EmployeeCreate, MeetingCreate


async def create_employee(db: AsyncSession, data: EmployeeCreate) -> Employee:
    """Создать сотрудника.

    Raises ValueError, если email уже занят.
    """
    # Проверяем уникальность email заранее
    existing = await db.execute(
        select(Employee).where(Employee.email == data.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Сотрудник с email '{data.email}' уже существует")

    employee = Employee(name=data.name, email=data.email)
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


async def get_employee(db: AsyncSession, employee_id: int) -> Employee | None:
    """Получить сотрудника по id."""
    return await db.get(Employee, employee_id)


async def get_all_employees(db: AsyncSession) -> list[Employee]:
    """Получить список всех сотрудников."""
    result = await db.execute(select(Employee).order_by(Employee.id))
    return list(result.scalars().all())


async def create_meeting(db: AsyncSession, data: MeetingCreate) -> Meeting:
    """Создать встречу с проверкой конфликтов.

    Raises ValueError с описанием конфликта, если слот занят.
    """
    # Загружаем всех участников и создателя одним запросом
    all_ids = list(set(data.participant_ids + [data.created_by]))
    result = await db.execute(
        select(Employee).where(Employee.id.in_(all_ids))
    )
    employees = result.scalars().all()
    found_ids = {e.id for e in employees}

    # Проверяем создателя
    if data.created_by not in found_ids:
        raise ValueError(f"Сотрудник-создатель с id={data.created_by} не найден")

    # Проверяем участников
    missing = set(data.participant_ids) - found_ids
    if missing:
        raise ValueError(f"Сотрудник(и) с id={missing} не найдены")

    participants = [e for e in employees if e.id in data.participant_ids]

    # Проверяем конфликты у всех участников
    conflict, description = await has_conflict(db, data.participant_ids, data.start_time, data.end_time)
    if conflict:
        raise ValueError(description or "Конфликт расписания")

    meeting = Meeting(
        title=data.title,
        start_time=data.start_time,
        end_time=data.end_time,
        created_by=data.created_by,
        participants=participants,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)

    # Подгружаем связи для ответа
    return await get_meeting(db, meeting.id)  # type: ignore[return-value]


async def get_meeting(db: AsyncSession, meeting_id: int) -> Meeting | None:
    """Получить встречу со всеми связями."""
    result = await db.execute(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.participants))
    )
    return result.scalar_one_or_none()


async def get_meetings_for_day(db: AsyncSession, day: date) -> list[Meeting]:
    """Все встречи за указанный день (UTC)."""
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end = start + timedelta(days=1)
    result = await db.execute(
        select(Meeting)
        .where(Meeting.start_time >= start, Meeting.start_time < end)
        .options(selectinload(Meeting.participants))
        .order_by(Meeting.start_time)
    )
    return list(result.scalars().all())


async def get_meetings_for_week(db: AsyncSession, week_start: date) -> list[Meeting]:
    """Все встречи за неделю, начиная с week_start (понедельник)."""
    start = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
    end = start + timedelta(days=7)
    result = await db.execute(
        select(Meeting)
        .where(Meeting.start_time >= start, Meeting.start_time < end)
        .options(selectinload(Meeting.participants))
        .order_by(Meeting.start_time)
    )
    return list(result.scalars().all())


async def get_employee_meetings(db: AsyncSession, employee_id: int) -> list[Meeting]:
    """Все встречи конкретного сотрудника."""
    from app.models import meeting_participant

    result = await db.execute(
        select(Meeting)
        .join(meeting_participant)
        .where(meeting_participant.c.employee_id == employee_id)
        .options(selectinload(Meeting.participants))
        .order_by(Meeting.start_time)
    )
    return list(result.scalars().all())

