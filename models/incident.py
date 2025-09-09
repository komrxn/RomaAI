from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from config.settings import settings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

class Incident(BaseModel):
    """Модель инцидента с расширенными полями"""
    
    id: str = Field(description="ID в формате #YYYY-MMDDhhmmss")
    date: str = Field(description="Дата в формате YYYY-MM-DD")
    time: str = Field(description="Время в формате HH:mm")
    branch: str = Field(description="Филиал")
    department: str = Field(description="Отдел")
    short_description: str = Field(description="Краткое описание проблемы")
    priority: str = Field(description="Приоритет: Критический/Высокий/Средний/Низкий")
    full_message: str = Field(description="Полное сообщение пользователя с автором")
    manager_report: Optional[str] = Field(default="", description="Отчет менеджера")
    status: str = Field(default="OPEN", description="Статус инцидента")
    deadline: Optional[str] = Field(default=None, description="Дедлайн решения")
    responsible_id: Optional[str] = Field(default=None, description="Telegram ID ответственного")
    completed_at: Optional[str] = Field(default=None, description="Время завершения")
    
    @classmethod
    def create_id(cls) -> str:
        """Генерация более удобного ID"""
        # Используем счетчик в Redis для последовательных номеров
        from services.redis_memory import RedisMemory
        redis = RedisMemory()
        
        # Получаем текущий день
        today = datetime.now().strftime('%Y%m%d')
        
        # Ключ счетчика на день
        counter_key = f"roma_bot:incident_counter:{today}"
        
        # Инкрементируем счетчик
        count = redis.redis_client.incr(counter_key)
        
        # Устанавливаем TTL на 2 дня
        redis.redis_client.expire(counter_key, 2 * 24 * 60 * 60)
        
        # Формат: #YYYYMMDD-NNN (например: #20250829-001)
        return f"#{today}-{count:03d}"

    @classmethod
    def get_current_date(cls) -> str:
        """Получение текущей даты по Ташкенту"""
        tashkent_time = datetime.now(ZoneInfo('Asia/Tashkent'))
        return tashkent_time.strftime('%Y-%m-%d')

    @classmethod
    def get_current_time(cls) -> str:
        """Получение текущего времени по Ташкенту"""
        tashkent_time = datetime.now(ZoneInfo('Asia/Tashkent'))
        return tashkent_time.strftime('%H:%M')

    def calculate_deadline(self) -> str:
        """Рассчитывает дедлайн с учетом часового пояса Ташкента"""
        hours = settings.DEADLINES.get(self.priority, 24)
        tashkent_time = datetime.now(ZoneInfo('Asia/Tashkent'))
        deadline_time = tashkent_time + timedelta(hours=hours)
        return deadline_time.isoformat()
        
    def get_responsible_id(self) -> Optional[str]:
        """Получает ID ответственного по отделу"""
        return settings.DEPARTMENT_HEADS.get(self.department)
    
    def to_sheet_row(self) -> list:
        """Преобразование в строку для Google Sheets"""
        # Добавим новую колонку для статуса (J)
        return [
            self.id,                           # A
            self.date,                         # B
            self.time,                         # C
            self.branch,                       # D
            self.department,                   # E
            self.short_description,            # F
            self.priority,                     # G
            self.full_message,                 # H
            self.manager_report,               # I
            settings.INCIDENT_STATUSES[self.status]  # J - Статус
        ]
    
    def to_telegram_message(self, include_deadline: bool = False) -> str:
        """Форматирование для отправки в Telegram"""
        # Извлекаем основное сообщение без автора
        main_message = self.full_message.split('\n\nАвтор:')[0] if '\n\nАвтор:' in self.full_message else self.full_message
        
        message = (
            f"🚨 Новый инцидент Roma Pizza\n"
            f"ID: {self.id}\n"
            f"📅 {self.date} {self.time}\n"
            f"📍 Филиал: {self.branch}\n"
            f"🏢 Отдел: {self.department}\n"
            f"⚠️ Приоритет: {self.priority}\n"
            f"📝 Проблема: {self.short_description}\n"
        )
        
        if include_deadline and self.deadline:
            deadline_dt = datetime.fromisoformat(self.deadline)
            deadline_str = deadline_dt.strftime('%d.%m.%Y %H:%M')
            message += f"⏰ Дедлайн: {deadline_str}\n"
        
        message += f"—\n{main_message}"
        
        # Добавляем автора если есть
        if '\n\nАвтор:' in self.full_message:
            author = self.full_message.split('\n\nАвтор:')[1].strip()
            message += f"\n\n— {author}"
        
        return message