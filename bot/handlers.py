"""Обработчики команд Telegram-бота.

Бот использует то же FastAPI приложение напрямую (через Depends/get_db),
чтобы не плодить HTTP-клиенты и не терять транзакционность.
"""

import logging
from datetime import date, datetime, timedelta

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from app.crud import (
    create_employee,
    create_meeting,
    get_all_employees,
    get_employee_meetings,
    get_meetings_for_day,
    get_meetings_for_week,
)
from app.database import async_session_factory
from app.schemas import EmployeeCreate, MeetingCreate

logger = logging.getLogger(__name__)

DATETIME_FMT = "%Y-%m-%d %H:%M"


# ── Вспомогательные функции ─────────────────────────────────


async def _render_meeting(m: dict | object) -> str:
    """Форматирует встречу в читаемую строку."""
    if hasattr(m, "id"):
        # Это ORM-объект, достаём атрибуты
        title = m.title
        start = m.start_time.strftime(DATETIME_FMT)
        end = m.end_time.strftime(DATETIME_FMT)
        participants = ", ".join(p.name for p in m.participants) if m.participants else "—"
        return (
            f"📅 <b>{title}</b>\n"
            f"   {start} — {end}\n"
            f"   Участники: {participants}\n"
            f"   ID встречи: {m.id}"
        )
    return str(m)


# ── Команды ─────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветствие и список команд."""
    text = (
        "👋 <b>Meeting Scheduler Bot</b>\n\n"
        "Доступные команды:\n"
        "/employees — список сотрудников\n"
        "/create_employee <имя> <email> — создать сотрудника\n"
        "/create_meeting <название> <YYYY-MM-DD HH:MM> <длительность_мин> <id1,id2,...> — создать встречу\n"
        "/meetings <YYYY-MM-DD> — встречи на день\n"
        "/week <YYYY-MM-DD> — встречи на неделю (понедельник)\n"
        "/my_meetings <employee_id> — встречи сотрудника\n"
        "/help — эта справка"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_employees(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Список всех сотрудников."""
    async with async_session_factory() as db:
        employees = await get_all_employees(db)

    if not employees:
        await update.message.reply_text("😕 Сотрудников пока нет.")
        return

    lines = [f"• <b>{e.name}</b> — {e.email} (id={e.id})" for e in employees]
    await update.message.reply_text(
        "👥 <b>Сотрудники:</b>\n" + "\n".join(lines),
        parse_mode="HTML",
    )


async def cmd_create_employee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создать сотрудника: /create_employee Имя email@example.com"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: /create_employee <имя> <email>\n"
            "Пример: /create_employee Alice alice@example.com"
        )
        return

    name = context.args[0]
    email = context.args[1]

    async with async_session_factory() as db:
        try:
            emp = await create_employee(db, EmployeeCreate(name=name, email=email))
            await update.message.reply_text(
                f"✅ Сотрудник создан:\n"
                f"   <b>{emp.name}</b> — {emp.email} (id={emp.id})",
                parse_mode="HTML",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")


async def cmd_create_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создать встречу: /create_meeting Название 2026-01-15 10:00 30 1,2"""
    if len(context.args) < 4:
        await update.message.reply_text(
            "❌ Использование: /create_meeting <название> <YYYY-MM-DD HH:MM> <длительность_мин> <id1,id2,...>\n"
            "Пример: /create_meeting Standup 2026-01-15 10:00 30 1,2"
        )
        return

    title = context.args[0]
    date_str = context.args[1]
    time_str = context.args[2]
    duration_str = context.args[3]
    participant_str = context.args[4] if len(context.args) > 4 else ""

    try:
        start_dt = datetime.strptime(f"{date_str} {time_str}", DATETIME_FMT)
        duration = int(duration_str)
        end_dt = start_dt + timedelta(minutes=duration)
        participant_ids = [int(pid.strip()) for pid in participant_str.split(",") if pid.strip()]
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Неверный формат. Пример:\n"
            "/create_meeting Standup 2026-01-15 10:00 30 1,2"
        )
        return

    if len(participant_ids) < 1:
        await update.message.reply_text("❌ Укажите хотя бы одного участника (через запятую).")
        return

    # Создатель — первый участник
    created_by = participant_ids[0]

    async with async_session_factory() as db:
        try:
            meeting = await create_meeting(
                db,
                MeetingCreate(
                    title=title,
                    start_time=start_dt,
                    end_time=end_dt,
                    created_by=created_by,
                    participant_ids=participant_ids,
                ),
            )
            await update.message.reply_text(
                f"✅ Встреча создана:\n{await _render_meeting(meeting)}",
                parse_mode="HTML",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")


async def cmd_meetings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Встречи на день: /meetings 2026-01-15"""
    if not context.args:
        day = date.today()
    else:
        try:
            day = datetime.strptime(context.args[0], "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте YYYY-MM-DD")
            return

    async with async_session_factory() as db:
        meetings = await get_meetings_for_day(db, day)

    if not meetings:
        await update.message.reply_text(f"📭 На {day} встреч нет.")
        return

    lines = [await _render_meeting(m) for m in meetings]
    await update.message.reply_text(
        f"📋 <b>Встречи на {day}:</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML",
    )


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Встречи на неделю: /week 2026-01-12 (понедельник)"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите дату понедельника: /week 2026-01-12"
        )
        return

    try:
        week_start = datetime.strptime(context.args[0], "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Используйте YYYY-MM-DD")
        return

    week_end = week_start + timedelta(days=6)

    async with async_session_factory() as db:
        meetings = await get_meetings_for_week(db, week_start)

    if not meetings:
        await update.message.reply_text(f"📭 На неделю {week_start} — {week_end} встреч нет.")
        return

    # Группируем по дням
    by_day: dict[date, list[object]] = {}
    for m in meetings:
        d = m.start_time.date()
        by_day.setdefault(d, []).append(m)

    parts = [f"📋 <b>Неделя {week_start} — {week_end}</b>"]
    for d in sorted(by_day.keys()):
        day_meetings = by_day[d]
        day_lines = [await _render_meeting(m) for m in day_meetings]
        parts.append(f"\n<b>{d}:</b>")
        parts.extend(day_lines)

    await update.message.reply_text("\n\n".join(parts), parse_mode="HTML")


async def cmd_my_meetings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Встречи сотрудника: /my_meetings 1"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /my_meetings <employee_id>")
        return

    try:
        emp_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ employee_id должен быть числом.")
        return

    async with async_session_factory() as db:
        meetings = await get_employee_meetings(db, emp_id)

    if not meetings:
        await update.message.reply_text(f"📭 У сотрудника id={emp_id} встреч нет.")
        return

    lines = [await _render_meeting(m) for m in meetings]
    await update.message.reply_text(
        f"📋 <b>Встречи сотрудника id={emp_id}:</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML",
    )


# ── Сборка приложения ──────────────────────────────────────


def build_application(token: str) -> Application:
    """Собрать Application с обработчиками команд."""
    app = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .build()
    )

    handlers = [
        CommandHandler("start", cmd_start),
        CommandHandler("help", cmd_help),
        CommandHandler("employees", cmd_employees),
        CommandHandler("create_employee", cmd_create_employee),
        CommandHandler("create_meeting", cmd_create_meeting),
        CommandHandler("meetings", cmd_meetings),
        CommandHandler("week", cmd_week),
        CommandHandler("my_meetings", cmd_my_meetings),
    ]

    for handler in handlers:
        app.add_handler(handler)

    return app

