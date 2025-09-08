import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Класс для хранения всех настроек приложения"""
    
    # Telegram настройки
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_GROUP_CHAT_ID = os.getenv('TELEGRAM_GROUP_CHAT_ID')
    
    # OpenAI настройки
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = "gpt-4o"
    
    # Google Sheets настройки
    GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID')
    GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    SHEET_NAME = 'incidents'
    
    # Redis настройки
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
    
    # Настройки памяти
    MEMORY_TTL_DAYS = 30
    MAX_MESSAGES_PER_USER = 50
    CONTEXT_MESSAGES = 10
    
    # Бизнес-логика
    BRANCHES = ['Sergeli', 'Novza', 'Buyul Ipak Yoli', 'Chilonzor', 'Bodomzor']
    DEPARTMENTS = [
        'HR', 'Marketing', 'Бухгалтерия', 'IT', 
        'Закуп и снабжение', 'Контроль качества', 'Стандартизация и сервис', 'Главный офис'
    ]
    
    PRIORITY_LEVELS = {
        'Критический': ['пожар', 'отравление', 'авария', 'воровство', 'драка'],
        'Высокий': ['поломка оборудования', 'нехватка продуктов', 'проблемы с персоналом', 'касса', 'кондиционер'],
        'Средний': ['жалобы клиентов', 'мелкие поломки', 'задержки поставок'],
        'Низкий': ['предложения', 'улучшение', 'мелкие неполадки']
    }
    
    # Дедлайны по приоритетам (в часах)
    DEADLINES = {
        'Критический': 1,    # 1 час
        'Высокий': 3,        # 3 часа но щас 
        'Средний': 9,       # 24 часа (1 день)
        'Низкий': 12,        # 72 часа (3 дня)
    }
    
    # Интервалы напоминаний (в минутах до дедлайна)
    REMINDER_INTERVALS = [60, 30, 10]  # За час, полчаса и 10 минут
    
    # Ответственные по отделам
    DEPARTMENT_HEADS = {
        'HR': os.getenv('DEPT_HR_ID', '765305446'), #amir 
        'IT': os.getenv('DEPT_IT_ID', '2040216796'), #komron
        'Marketing': os.getenv('DEPT_MARKETING_ID', '765305446'), #amir
        'Бухгалтерия': os.getenv('DEPT_ACCOUNTING_ID', '6321655859'), #umid
        'Закуп и снабжение': os.getenv('DEPT_SUPPLY_ID', '6321655859'), #umid
        'Контроль качества': os.getenv('DEPT_QUALITY_ID', '7232563857'), 
        'Стандартизация и сервис': os.getenv('DEPT_SERVICE_ID', '962959948'), # said
        'Доставка и Колл-центр': os.getenv('DEPT_DELIVERY_ID', '6800942148'), # 
        'Главный офис': os.getenv('DEPT_HEAD_ID', '6321655859'), #Timur aka
    }
    
    # Статусы инцидентов
    INCIDENT_STATUSES = {
    'OPEN': 'Не решено',
    'RESOLVED': 'Решено',
    'OVERDUE': 'Просрочено'
}

settings = Settings()