from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.datefmt import DATETIME_FMT
from app.models import Employee, Meeting, meeting_participant


async def has_conflict(
    db: AsyncSession,
    participant_ids: list[int],
    start_time: datetime,
    end_time: datetime,
    exclude_meeting_id: int | None = None,
) -> tuple[bool, str | None]:
    """Проверяет, есть ли у кого-то из участников пересекающаяся встреча.

    Пересечение: существующая встреча и новый слот накладываются во времени.
    Встречи впритык (10:00–10:30 и 10:30–11:00) НЕ считаются конфликтом.

    Возвращает (есть_конфликт, описание_конфликта).
    """
    # Формула пересечения интервалов:
    # existing.start_time < new.end_time AND existing.end_time > new.start_time
    # Сначала находим Meeting.id и employee_id тех, у кого есть пересечение
    overlap_query = (
        select(Meeting.id, meeting_participant.c.employee_id)
        .join(meeting_participant)
        .where(
            meeting_participant.c.employee_id.in_(participant_ids),
            Meeting.start_time < end_time,
            Meeting.end_time > start_time,
        )
    )

    if exclude_meeting_id is not None:
        overlap_query = overlap_query.where(Meeting.id != exclude_meeting_id)

    result = await db.execute(overlap_query)
    rows = result.all()

    if not rows:
        return False, None

    # Собираем Meeting.id, у которых есть пересечение
    meeting_ids = {row.id for row in rows}
    # И ID сотрудников, которые пересекаются (уже отфильтровано по participant_ids)
    conflicted_employee_ids = {row.employee_id for row in rows}

    # Загружаем названия сотрудников и встречи для сообщения
    emp_result = await db.execute(
        select(Employee).where(Employee.id.in_(conflicted_employee_ids))
    )
    employees = {e.id: e.name for e in emp_result.scalars().all()}

    # Берём первую конфликтующую встречу для деталей
    meeting_result = await db.execute(
        select(Meeting)
        .where(Meeting.id.in_(list(meeting_ids)[:1]))
        .options(selectinload(Meeting.participants))
    )
    first_conflict = meeting_result.scalar_one_or_none()
    if first_conflict is None:
        return True, "Конфликт расписания"

    names = ", ".join(employees.get(pid, f"id={pid}") for pid in conflicted_employee_ids)
    return (
        True,
                f"У сотрудника(ов) {names} уже есть встреча "
        f"'{first_conflict.title}' "
        f"({first_conflict.start_time.strftime(DATETIME_FMT)} — "
        f"{first_conflict.end_time.strftime(DATETIME_FMT)})",
    )
