"""Запуск Telegram-бота в фоновом режиме.

Бот работает через polling и не блокирует FastAPI lifespan.
Вызов start_bot/stop_bot происходит из lifespan app/main.py.

Также можно запустить как самостоятельный процесс:
    python -m bot.main
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from telegram.ext import Application
from app.database import settings

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Настроить базовое логирование для бота, если ещё не настроено."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")


_bot_app: Application | None = None


def get_bot_app() -> Application | None:
    """Вернуть глобальный экземпляр бота (для прямого доступа)."""
    global _bot_app
    return _bot_app


async def run_bot_standalone() -> None:
    """Запустить бота как самостоятельный процесс (не в составе FastAPI)."""
    _setup_logging()

    token = settings.telegram_bot_token
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан. Укажите токен в .env файле.")
        return

    from bot.handlers import build_application

    app = build_application(token)
    logger.info("Запуск Telegram-бота...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("Telegram-бот запущен. Нажмите Ctrl+C для остановки.")

    try:
        # Держим процесс живым
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Останавливаем Telegram-бота...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Telegram-бот остановлен.")


def main() -> None:
    """Entrypoint для запуска бота отдельно."""
    asyncio.run(run_bot_standalone())


if __name__ == "__main__":
    main()


@asynccontextmanager
async def bot_lifespan():
    """Context manager для запуска/остановки бота вместе с FastAPI.

    Если токен не указан или бот не смог подключиться — продолжаем без него.
    """
    global _bot_app
    token = settings.telegram_bot_token

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
        yield
        return

    _setup_logging()

    # Импортируем здесь чтобы избежать циклического импорта
    from bot.handlers import build_application

    _bot_app = build_application(token)
    try:
        logger.info("Подключаем бота к Telegram API...")
        await _bot_app.initialize()
        await _bot_app.start()
        await _bot_app.updater.start_polling()
        logger.info("Telegram-бот запущен и слушает обновления")
    except Exception as e:
        logger.error("Не удалось запустить Telegram-бота: %s", e)
        import traceback
        logger.error("Трейс:\n%s", traceback.format_exc())
        try:
            await _bot_app.shutdown()
        except Exception:
            pass
        _bot_app = None
        yield
        return

    try:
        yield
    finally:
        logger.info("Останавливаем Telegram-бота...")
        try:
            await _bot_app.updater.stop()
            await _bot_app.stop()
            await _bot_app.shutdown()
        except Exception as e:
            logger.error("Ошибка при остановке бота: %s", e)
        _bot_app = None
