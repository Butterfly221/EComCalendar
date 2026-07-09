"""Юнит-тесты для Telegram-бота.

Тестируем логику формирования сообщений и парсинга аргументов,
без реального подключения к Telegram API.
"""

from datetime import datetime

import pytest

from bot.handlers import _render_meeting
from app.models import Employee, Meeting


@pytest.mark.asyncio
async def test_render_meeting():
    """Проверяем форматирование встречи в HTML."""
    alice = Employee(id=1, name="Alice", email="alice@example.com")
    bob = Employee(id=2, name="Bob", email="bob@example.com")
    meeting = Meeting(
        id=42,
        title="Standup",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 10, 30, 0),
        created_by=1,
        participants=[alice, bob],
    )

    result = await _render_meeting(meeting)

    assert "Standup" in result
    assert "15.01.2026 10:00" in result
    assert "15.01.2026 10:30" in result
    assert "Alice" in result
    assert "Bob" in result
    assert "42" in result
    assert result.startswith("📅")


@pytest.mark.asyncio
async def test_render_meeting_no_participants():
    """Встреча без участников (крайний случай)."""
    meeting = Meeting(
        id=1,
        title="Solo",
        start_time=datetime(2026, 1, 15, 10, 0, 0),
        end_time=datetime(2026, 1, 15, 11, 0, 0),
        created_by=1,
        participants=[],
    )

    result = await _render_meeting(meeting)

    assert "Solo" in result
    assert "—" in result  # заглушка для пустых участников

