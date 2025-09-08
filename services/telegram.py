from telegram import Bot
from telegram.error import TelegramError
from config.settings import settings

class TelegramService:
    """Сервис для отправки сообщений в Telegram"""
    
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.group_chat_id = settings.TELEGRAM_GROUP_CHAT_ID
        
    async def send_to_group(self, message: str) -> bool:
        """
        Отправляет сообщение в группу менеджеров
        
        Args:
            message: Текст сообщения
            
        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            await self.bot.send_message(
                chat_id=self.group_chat_id,
                text=message,
                parse_mode='HTML'  # Поддержка форматирования
            )
            return True
            
        except TelegramError as e:
            print(f"Ошибка отправки в группу: {e}")
            return False
        except Exception as e:
            print(f"Неожиданная ошибка при отправке: {e}")
            return False