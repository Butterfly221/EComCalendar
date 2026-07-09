from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import create_employee, create_meeting, get_all_employees, get_employee_meetings, get_meetings_for_day, get_meetings_for_week
from app.database import engine, get_db
from app.models import Base
from app.schemas import EmployeeCreate, EmployeeRead, MeetingCreate, MeetingRead


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: D401 — conventional FastAPI name
    """Создать таблицы при старте приложения и запустить Telegram-бота."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Запускаем Telegram-бота (если настроен токен)
    from bot.main import bot_lifespan
    async with bot_lifespan():
        yield


app = FastAPI(title="Meeting Scheduler", version="0.1.0", lifespan=lifespan)


# ── Сотрудники ─────────────────────────────────────────────

@app.post("/employees", response_model=EmployeeRead, status_code=201)
async def api_create_employee(data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    """Создать сотрудника."""
    try:
        return await create_employee(db, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/employees", response_model=list[EmployeeRead])
async def api_list_employees(db: AsyncSession = Depends(get_db)):
    """Получить список всех сотрудников."""
    return await get_all_employees(db)


# ── Встречи ────────────────────────────────────────────────

@app.post("/meetings", response_model=MeetingRead, status_code=201)
async def api_create_meeting(data: MeetingCreate, db: AsyncSession = Depends(get_db)):
    """Создать встречу. Возвращает 409 при конфликте расписания."""
    try:
        return await create_meeting(db, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/meetings", response_model=list[MeetingRead])
async def api_get_meetings(
    date: date | None = Query(None, alias="date"),
    week_start: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Получить встречи на день (date) или неделю (week_start). Нельзя передать оба сразу."""
    if date is not None and week_start is not None:
        raise HTTPException(status_code=400, detail="Передайте только date ИЛИ week_start, не оба сразу")
    if date is None and week_start is None:
        raise HTTPException(status_code=400, detail="Передайте date ИЛИ week_start")

    if date is not None:
        return await get_meetings_for_day(db, date)
    else:
        return await get_meetings_for_week(db, week_start)  # type: ignore[arg-type]


# ── Расписание сотрудника ──────────────────────────────────

@app.get("/employees/{employee_id}/meetings", response_model=list[MeetingRead])
async def api_get_employee_meetings(employee_id: int, db: AsyncSession = Depends(get_db)):
    """Получить все встречи сотрудника."""
    return await get_employee_meetings(db, employee_id)