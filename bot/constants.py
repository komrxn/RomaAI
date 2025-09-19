"""
Constants for Roma Pizza Bot
Centralized location for all magic strings, numbers, and configuration values
"""

# Message templates
class Messages:
    WELCOME_NEW_USER = "👋 Привет, {name}! Я бот для регистрации инцидентов Roma Pizza.\n\n"
    WELCOME_RETURNING_USER = "👋 С возвращением, {name}!\n\n📊 Ваша статистика:\n• Зарегистрировано инцидентов: {count}\n"
    WELCOME_COMMANDS = (
        "\n📝 Отправьте отчет о проблеме:\n"
        "• 'Сломалась касса в Новза'\n"
        "• 'Не работает кондиционер в Chilonzor'\n\n"
        "📊 Для аналитики: /rep [запрос]\n"
        "📈 Моя статистика: /mystats"
    )
    
    INCIDENT_ACCEPTED = (
        "🟠 Отчет принят!\n\n"
        "📸 Теперь отправьте фото подтверждение проблемы.\n"
        "Только после получения фото отчет будет отправлен менеджерам."
    )
    
    PHOTO_WITHOUT_CONTEXT = (
        "📸 Фото принято, но я не ожидал его. Отправьте текстовое сообщение о проблеме."
    )
    
    PENDING_INCIDENT_WARNING = (
        "📸 У вас есть незавершенный инцидент {incident_id}!\n\n"
        "Пожалуйста, сначала отправьте фото подтверждение для этого инцидента, "
        "а затем можете создать новый отчет."
    )
    
    VOICE_PROCESSING = "🎤 Обрабатываю голосовое сообщение..."
    VOICE_RECOGNIZED = "📝 Распознанный текст:\n<i>{text}</i>"
    VOICE_ERROR = "❌ Не удалось обработать голосовое сообщение. Попробуйте написать текстом."
    
    PHOTO_VALIDATION_ERROR = "❌ {error}"
    PHOTO_SAVED_SUCCESS = (
        "✅ Спасибо за фото подтверждение!\n\n"
        "📋 ID: {incident_id}\n"
        "📍 Филиал: {branch}\n"
        "🏢 Отдел: {department}\n"
        "⚠️ Приоритет: {priority}\n"
        "⏰ Дедлайн: {deadline}\n\n"
        "📸 Фото добавлено к инциденту в Google Sheets и отправлено менеджерам.\n"
        "Они займутся решением проблемы."
    )
    
    SOLUTION_ACCEPTED = (
        "🟠 Решение принято!\n\n"
        "📋 ID: {incident_id}\n"
        "✨ Решение: {resolution}\n\n"
        "📸 Теперь отправьте фото подтверждения того, что проблема решена.\n"
        "Только после получения фото инцидент будет закрыт."
    )
    
    SOLUTION_PHOTO_SAVED = (
        "✅ Спасибо за фото решения!\n\n"
        "📸 Фото решения добавлено к инциденту и отправлено в группу.\n"
        "Инцидент успешно закрыт!"
    )
    
    GENERAL_ERROR = "❌ Произошла ошибка. Попробуйте еще раз."

# Error messages
class Errors:
    INCIDENT_NOT_FOUND = "❌ Инцидент {incident_id} не найден"
    INCIDENT_ALREADY_RESOLVED = "ℹ️ Инцидент {incident_id} уже решен"
    NOT_RESPONSIBLE = (
        "❌ Вы не являетесь ответственным за этот инцидент\n"
        "Ответственный: ID {responsible_id}\n"
        "Ваш ID: {user_id}"
    )
    NOT_DEPARTMENT_HEAD = (
        "❌ Вы не являетесь ответственным ни за один отдел.\n"
        "Эта команда доступна только назначенным ответственным."
    )
    SHEETS_ERROR = "❌ Ошибка сохранения инцидента. Попробуйте еще раз."
    PHOTO_SAVE_ERROR = "❌ Ошибка сохранения фото: {error}"
    GENERAL_ERROR = "❌ Произошла ошибка. Попробуйте еще раз."

# Command templates
class Commands:
    RESOLVE_USAGE = (
        "Используйте: /resolve [ID инцидента] [описание решения]\n"
        "Например: /resolve #20250827234045 Заменил предохранитель, свет работает"
    )
    STATUS_USAGE = (
        "Используйте: /status [ID инцидента]\n"
        "Например: /status #20250827234045"
    )
    REP_USAGE = (
        "📊 Добавьте запрос после /rep:\n"
        "• /rep все инциденты\n" 
        "• /rep статистика по отделам\n"
        "• /rep проблемы за сегодня\n"
        "• /rep глобальная статистика"
    )

# File handling
class FileHandling:
    MAX_PHOTO_SIZE_MB = 10
    ALLOWED_PHOTO_FORMATS = ['jpg', 'jpeg', 'png', 'gif', 'webp']
    PHOTO_REQUEST_TIMEOUT = 300  # 5 minutes
    
    # Magic bytes for format detection
    MAGIC_BYTES = {
        b'\xff\xd8\xff': 'jpg',
        b'\x89PNG': 'png',
        b'GIF': 'gif',
        b'RIFF': 'webp'  # Check for WEBP in first 12 bytes
    }

# Redis keys
class RedisKeys:
    USER_KEY = "roma_bot:user:{user_id}"
    MESSAGES_KEY = "roma_bot:messages:{user_id}"
    STATS_KEY = "roma_bot:stats:{user_id}"
    INCIDENT_KEY = "roma_bot:incident:{incident_id}"
    ACTIVE_INCIDENTS = "roma_bot:active_incidents"
    INCIDENT_COUNTER = "roma_bot:incident_counter:{date}"

# Logging
class LogMessages:
    VOICE_PROCESSING = "🎤 Обрабатываю голосовое сообщение..."
    PHOTO_DOWNLOADING = "⬇️ Скачиваю фото из Telegram..."
    PHOTO_VALIDATING = "🔍 Валидирую фото..."
    PHOTO_SAVING = "💾 Сохраняю фото..."
    INCIDENT_SAVING = "💾 Инцидент {incident_id} сохранен в Redis (ожидает фото)"
    SHEETS_UPDATING = "📊 Обновляю инцидент в Google Sheets..."
    NOTIFICATION_SENDING = "📤 Отправляю уведомление в группу с фото..."
    CONTEXT_CLEANING = "🧹 Очищаю контекст пользователя"

# Debug messages
class DebugMessages:
    USER_ID_CHECK = "🔍 Отладка: user_id={user_id}, pending_incident={pending_incident}"
    INCIDENT_FOUND = "🔍 Найден незавершенный инцидент: {incident_id}, has_image={has_image}"
    USER_CONTEXT = "🔍 user_context: {user_context}"
    WAITING_FOR_PHOTO = "🔍 waiting_for_photo: {waiting_for_photo}"
    BLOCKING_CONDITION = "🔍 Условие блокировки: pending_incident={pending_incident}, waiting_for_photo={waiting_for_photo}"
    PHOTO_RECEIVED = "📸 Получено фото {type} для инцидента: {incident_id}"
    PHOTO_IGNORED = "⚠️ Получено фото без ожидания - игнорирую"
    CONTEXT_CLEANING = "🧹 Очищаю контекст пользователя"
