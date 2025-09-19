import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
# Импортируйте фильтр для голосовых
from telegram.ext import MessageHandler, filters
from config.settings import settings
from bot.handlers import (
    start_command,
    handle_message,
    rep_command,
    mystats_command,
    globalstats_command,
    resolve_command,
    status_command,
    myincidents_command,
    error_handler,
    handle_voice,
    handle_photo
)
from services.incident_manager import IncidentManager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application):
    """Запускает фоновые задачи после инициализации"""
    # Запускаем проверку дедлайнов
    incident_manager = IncidentManager()
    asyncio.create_task(incident_manager.check_deadlines())
    logger.info("Запущена проверка дедлайнов")

def main():
    """Запуск бота с системой управления инцидентами"""
    
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("Нет TELEGRAM_BOT_TOKEN!")
        return
    
    if not settings.OPENAI_API_KEY:
        logger.error("Нет OPENAI_API_KEY!")
        return
    
    # Создаем приложение
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем инициализацию после запуска
    app.post_init = post_init
    
    # Команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("rep", rep_command))
    app.add_handler(CommandHandler("mystats", mystats_command))
    app.add_handler(CommandHandler("globalstats", globalstats_command))
    app.add_handler(CommandHandler("resolve", resolve_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("myincidents", myincidents_command))
    
    # Все текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Обработчик голосовых сообщений
    app.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, handle_voice))

    # Обработчик фото сообщений
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))

    # Обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Запуск
    logger.info("Roma Pizza Incident Management Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()