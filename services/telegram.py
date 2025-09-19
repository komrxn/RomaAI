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
    
    async def send_to_group_with_photo(self, incident_id: str, description: str, 
                                     branch: str, department: str, priority: str, 
                                     full_message: str, photo_url: str) -> bool:
        """
        Отправляет инцидент с фото в группу менеджеров
        
        Args:
            incident_id: ID инцидента
            description: Краткое описание
            branch: Филиал
            department: Отдел
            priority: Приоритет
            full_message: Полное сообщение
            photo_url: URL фото
            
        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            # Формируем сообщение
            caption = (
                f"🚨 Новый инцидент Roma Pizza\n"
                f"ID: {incident_id}\n"
                f"📍 Филиал: {branch}\n"
                f"🏢 Отдел: {department}\n"
                f"⚠️ Приоритет: {priority}\n"
                f"📝 Проблема: {description}\n"
                f"—\n{full_message}"
            )
            
            await self.bot.send_photo(
                chat_id=self.group_chat_id,
                photo=photo_url,
                caption=caption,
                parse_mode='HTML'
            )
            return True
            
        except TelegramError as e:
            print(f"Ошибка отправки фото в группу: {e}")
            return False
        except Exception as e:
            print(f"Неожиданная ошибка при отправке фото: {e}")
            return False