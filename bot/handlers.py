from telegram import Update
from telegram.ext import ContextTypes
from ai.agent import IncidentAIAgent
from services.google_sheets import GoogleSheetsService
from services.telegram import TelegramService
from services.redis_memory import RedisMemory
from services.incident_manager import IncidentManager
from config.settings import settings
from datetime import datetime
from telegram.constants import ChatAction
import asyncio
import re
from services.voice_handler import VoiceHandler
from telegram import Voice

async def show_typing(context, chat_id):
    """Показывает индикатор набора"""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except:
        pass

# Инициализируем сервисы
ai_agent = IncidentAIAgent()
sheets_service = GoogleSheetsService()
telegram_service = TelegramService()
memory_service = RedisMemory()
incident_manager = IncidentManager()
voice_handler = VoiceHandler()

# Локальный контекст для текущих инцидентов
user_contexts = {}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await show_typing(context, update.effective_chat.id)
    user_id = update.effective_user.id
    username = update.effective_user.username or "Пользователь"
    
    # Сохраняем информацию о пользователе
    memory_service.update_user_info(user_id, {
        "username": username,
        "first_name": update.effective_user.first_name,
        "chat_id": update.effective_chat.id
    })
    
    # Получаем сводку о пользователе
    user_summary = memory_service.get_user_summary(user_id)
    
    if user_summary['incidents_count'] > 0:
        welcome = (
            f"👋 С возвращением, {update.effective_user.first_name}!\n\n"
            f"📊 Ваша статистика:\n"
            f"• Зарегистрировано инцидентов: {user_summary['incidents_count']}\n"
        )
        
        if user_summary['frequent_branches']:
            branches = ", ".join([b[0] for b in user_summary['frequent_branches'][:2]])
            welcome += f"• Частые филиалы: {branches}\n"
    else:
        welcome = f"👋 Привет, {update.effective_user.first_name}! Я бот для регистрации инцидентов Roma Pizza.\n\n"
    
    welcome += (
        "\n📝 Отправьте отчет о проблеме:\n"
        "• 'Сломалась касса в Новза'\n"
        "• 'Не работает кондиционер в Chilonzor'\n\n"
        "📊 Для аналитики: /rep [запрос]\n"
        "📈 Моя статистика: /mystats"
    )
    
    await update.message.reply_text(welcome)
    
    # Сохраняем в память
    memory_service.add_message(user_id, "user", "/start")
    memory_service.add_message(user_id, "assistant", welcome)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех сообщений с памятью"""
    
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    chat_id = update.effective_chat.id
    await show_typing(context, chat_id)
    
    # ВАЖНО: Игнорируем сообщения из группы менеджеров
    if str(chat_id) == settings.TELEGRAM_GROUP_CHAT_ID:
        return
    
    # Проверяем, что это личный чат
    if update.effective_chat.type != 'private':
        return
    
    # Получаем информацию об авторе
    author_username = update.effective_user.username or "Неизвестный"
    author_name = update.effective_user.first_name or "Пользователь"
    author_info = f"@{author_username} ({author_name})"
    
    # Сохраняем сообщение пользователя
    memory_service.add_message(user_id, "user", message_text)
    
    # Получаем контекст и историю
    user_context = user_contexts.get(user_id)
    conversation_history = memory_service.get_context(user_id)
    user_summary = memory_service.get_user_summary(user_id)
    
    # Обрабатываем через AI с полным контекстом
    ai_response = ai_agent.process_message(
        message_text, 
        user_context, 
        conversation_history,
        user_summary
    )
    
    response_text = ai_response['response']
    
    if ai_response['type'] == 'incident':
        incident_data = ai_response.get('incident_data', {})
        
        if not all([incident_data.get('branch'), incident_data.get('department')]):
            await update.message.reply_text(response_text)
            memory_service.add_message(user_id, "assistant", response_text)
            return
        
        # Создаем инцидент с информацией об авторе
        if user_context:
            full_message = f"{user_context['original_message']}. {message_text}"
        else:
            full_message = message_text
        
        # Добавляем автора
        full_message_with_author = f"{full_message}\n\nАвтор: {author_info}"
        
        incident = ai_agent.create_incident_from_data(
            incident_data, 
            full_message_with_author
        )
        
        if incident:
            # Добавляем дедлайн и ответственного
            incident.deadline = incident.calculate_deadline()
            incident.responsible_id = incident.get_responsible_id()
            
            # Сохраняем в Sheets
            sheets_ok = sheets_service.append_incident(incident)
            
            # Сохраняем в Redis для отслеживания
            incident_dict = incident.dict()
            incident_manager.save_incident(incident_dict)
            
            # Отправляем в группу
            telegram_ok = await telegram_service.send_to_group(incident.to_telegram_message())
            
            # Отправляем ответственному
            if incident.responsible_id:
                try:
                    responsible_message = (
                        f"🚨 Вам назначен новый инцидент!\n\n"
                        f"{incident.to_telegram_message(include_deadline=True)}\n\n"
                        f"Пожалуйста, решите проблему до дедлайна.\n"
                        f"После решения отправьте:\n"
                        f"/resolve {incident.id} [описание решения]"
                    )
                    await context.bot.send_message(
                        chat_id=incident.responsible_id,
                        text=responsible_message
                    )
                except Exception as e:
                    print(f"Не удалось отправить ответственному: {e}")
            
            # Формируем ответ автору
            deadline_dt = datetime.fromisoformat(incident.deadline)
            deadline_str = deadline_dt.strftime('%d.%m.%Y %H:%M')
            
            base_response = (
                f"✅ Инцидент зарегистрирован!\n\n"
                f"📋 ID: {incident.id}\n"
                f"📍 Филиал: {incident.branch}\n"
                f"🏢 Отдел: {incident.department}\n"
                f"⚠️ Приоритет: {incident.priority}\n"
                f"⏰ Дедлайн: {deadline_str}\n"
                f"👤 Ответственный уведомлен\n\n"
                f"Менеджеры займутся решением проблемы."
            )
            
            await update.message.reply_text(base_response)
            
            # Сохраняем в память
            memory_service.add_message(user_id, "assistant", base_response, {
                "type": "incident",
                "incident_id": incident.id,
                "branch": incident.branch,
                "department": incident.department,
                "priority": incident.priority,
                "author": author_info,
                "deadline": incident.deadline
            })
            
            # Очищаем контекст
            if user_id in user_contexts:
                del user_contexts[user_id]
        else:
            await update.message.reply_text(response_text)
            memory_service.add_message(user_id, "assistant", response_text)
            
    elif ai_response['type'] == 'clarification':
        # Обновляем контекст
        if not user_context:
            user_contexts[user_id] = {
                'original_message': message_text,
                'partial_analysis': ai_response.get('incident_data', {}),
                'author_info': author_info
            }
        else:
            user_contexts[user_id]['original_message'] += f". {message_text}"
            if ai_response.get('incident_data'):
                user_contexts[user_id]['partial_analysis'].update(ai_response['incident_data'])
        
        await update.message.reply_text(response_text)
        memory_service.add_message(user_id, "assistant", response_text, {"type": "clarification"})
        
    else:  # not_incident
        await update.message.reply_text(response_text)
        memory_service.add_message(user_id, "assistant", response_text)
        
        if user_id in user_contexts:
            del user_contexts[user_id]

async def rep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /rep с глобальной статистикой"""
    # Проверяем, что это личный чат
    if update.effective_chat.type != 'private':
        return
    
    await show_typing(context, update.effective_chat.id)
    text = update.message.text
    query = text[4:].strip() if len(text) > 4 else ""
    
    if not query:
        await update.message.reply_text(
            "📊 Добавьте запрос после /rep:\n"
            "• /rep все инциденты\n" 
            "• /rep статистика по отделам\n"
            "• /rep проблемы за сегодня\n"
            "• /rep глобальная статистика"
        )
        return
    
    msg = await update.message.reply_text("🔍 Анализирую данные...")
    
    try:
        # Получаем данные
        incidents = sheets_service.get_all_incidents()
        
        if not incidents:
            await msg.edit_text("📊 Нет данных для анализа.")
            return
        
        # Получаем глобальную статистику из Redis
        global_stats = memory_service.get_global_stats()
        
        # Анализируем через AI с глобальной статистикой
        analysis = ai_agent.analyze_incidents_data(incidents, query, global_stats)
        
        # Отправляем результат
        if len(analysis) > 4000:
            await msg.edit_text(analysis[:4000])
            for i in range(4000, len(analysis), 4000):
                await update.message.reply_text(analysis[i:i+4000])
        else:
            await msg.edit_text(analysis)
        
        # Сохраняем в память
        memory_service.add_message(update.effective_user.id, "user", f"/rep {query}")
        memory_service.add_message(update.effective_user.id, "assistant", analysis[:500] + "...")
            
    except Exception as e:
        print(f"Ошибка анализа: {e}")
        await msg.edit_text("❌ Ошибка при анализе. Попробуйте позже.")

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mystats - персональная статистика"""
    # Проверяем, что это личный чат
    if update.effective_chat.type != 'private':
        return
    
    await show_typing(context, update.effective_chat.id)
    user_id = update.effective_user.id
    user_summary = memory_service.get_user_summary(user_id)
    
    if user_summary['incidents_count'] == 0:
        await update.message.reply_text("📊 У вас пока нет зарегистрированных инцидентов.")
        return
    
    stats_message = f"📊 **Ваша статистика**\n\n"
    stats_message += f"📋 Всего инцидентов: {user_summary['incidents_count']}\n"
    
    if user_summary['last_activity']:
        last_activity = datetime.fromisoformat(user_summary['last_activity'])
        days_ago = (datetime.now() - last_activity).days
        if days_ago == 0:
            stats_message += f"⏰ Последняя активность: сегодня\n"
        elif days_ago == 1:
            stats_message += f"⏰ Последняя активность: вчера\n"
        else:
            stats_message += f"⏰ Последняя активность: {days_ago} дней назад\n"
    
    if user_summary['frequent_branches']:
        stats_message += f"\n**Частые филиалы:**\n"
        for branch, count in user_summary['frequent_branches']:
            stats_message += f"• {branch}: {count} инцидентов\n"
    
    if user_summary['frequent_departments']:
        stats_message += f"\n**Проблемные отделы:**\n"
        for dept, count in user_summary['frequent_departments']:
            stats_message += f"• {dept}: {count} инцидентов\n"
    
    # Получаем последние инциденты из истории
    history = memory_service.get_context(user_id, 20)
    recent_incidents = []
    
    for msg in history:
        if msg.get('metadata', {}).get('type') == 'incident':
            recent_incidents.append(msg['metadata'])
    
    if recent_incidents:
        stats_message += f"\n**Последние инциденты:**\n"
        for inc in recent_incidents[-3:]:
            stats_message += f"• {inc.get('incident_id', 'N/A')} - {inc.get('branch', 'N/A')}\n"
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def globalstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /globalstats - глобальная статистика системы"""
    # Проверяем, что это личный чат
    if update.effective_chat.type != 'private':
        return
    
    await show_typing(context, update.effective_chat.id)
    global_stats = memory_service.get_global_stats()
    
    stats_message = "🌍 **Глобальная статистика Roma Pizza Bot**\n\n"
    stats_message += f"📊 Всего инцидентов в системе: {global_stats['total_incidents']}\n"
    stats_message += f"👥 Активных пользователей (24ч): {global_stats['active_users_24h']}\n"
    
    if global_stats['branch_stats']:
        stats_message += f"\n**Топ филиалов по инцидентам:**\n"
        for branch, count in list(global_stats['branch_stats'].items())[:5]:
            percentage = (count / global_stats['total_incidents'] * 100) if global_stats['total_incidents'] > 0 else 0
            stats_message += f"• {branch}: {count} ({percentage:.1f}%)\n"
    
    if global_stats['department_stats']:
        stats_message += f"\n**Топ проблемных отделов:**\n"
        for dept, count in list(global_stats['department_stats'].items())[:5]:
            percentage = (count / global_stats['total_incidents'] * 100) if global_stats['total_incidents'] > 0 else 0
            stats_message += f"• {dept}: {count} ({percentage:.1f}%)\n"
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def resolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /resolve для завершения инцидента"""
    await show_typing(context, update.effective_chat.id)
    # Отладочный вывод
    print(f"Команда /resolve от пользователя {update.effective_user.id}")
    print(f"Аргументы: {context.args}")
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Используйте: /resolve [ID инцидента] [описание решения]\n"
            "Например: /resolve #20250827234045 Заменил предохранитель, свет работает"
        )
        return
    
    incident_id = context.args[0]
    resolution = ' '.join(context.args[1:])
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "Unknown"
    
    # Получаем инцидент
    incident = incident_manager.get_incident(incident_id)
    
    if not incident:
        await update.message.reply_text(f"❌ Инцидент {incident_id} не найден")
        return
    
    # Проверяем статус
    current_status = incident.get('status', 'OPEN')
    if current_status == 'RESOLVED':
        await update.message.reply_text(f"ℹ️ Инцидент {incident_id} уже решен")
        return
    
    # Проверяем, что это ответственный
    responsible_id = str(incident.get('responsible_id', ''))
    print(f"Ответственный: {responsible_id}, Пользователь: {user_id}")
    
    if user_id != responsible_id:
        await update.message.reply_text(
            f"❌ Вы не являетесь ответственным за этот инцидент\n"
            f"Ответственный: ID {responsible_id}\n"
            f"Ваш ID: {user_id}"
        )
        return
    
    # Обновляем статус (БЕЗ resolved_by)
    success = incident_manager.update_incident_status(
        incident_id, 
        'RESOLVED',
        resolution
    )
    
    if success:
        # Уведомляем в группу
        completion_message = (
            f"✅ Инцидент {incident_id} решен!\n\n"
            f"📍 Филиал: {incident.get('branch', 'Неизвестно')}\n"
            f"🏢 Отдел: {incident.get('department', 'Неизвестно')}\n"
            f"📝 Проблема: {incident.get('short_description', 'Не указано')}\n"
            f"✨ Решение: {resolution}\n"
            f"👤 Решил: @{username}"
        )
        
        try:
            await telegram_service.send_to_group(completion_message)
        except Exception as e:
            print(f"Ошибка отправки в группу: {e}")
        
        await update.message.reply_text(
            f"✅ Инцидент {incident_id} успешно закрыт!\n"
            f"Решение: {resolution}"
        )
    else:
        await update.message.reply_text("❌ Ошибка при обновлении статуса")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status для проверки статуса инцидента"""
    await show_typing(context, update.effective_chat.id)
    if not context.args:
        await update.message.reply_text(
            "Используйте: /status [ID инцидента]\n"
            "Например: /status #20250827234045"
        )
        return
    
    incident_id = context.args[0]
    
    # Получаем инцидент
    incident = incident_manager.get_incident(incident_id)
    
    if not incident:
        await update.message.reply_text(f"❌ Инцидент {incident_id} не найден")
        return
    
    # Форматируем статус
    status = settings.INCIDENT_STATUSES.get(incident.get('status', 'OPEN'))
    deadline = datetime.fromisoformat(incident['deadline'])
    deadline_str = deadline.strftime('%d.%m.%Y %H:%M')
    
    # Рассчитываем оставшееся время
    now = datetime.now()
    time_left = deadline - now
    
    if time_left.total_seconds() > 0:
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        time_left_str = f"{hours}ч {minutes}мин"
    else:
        time_left_str = "Просрочен"
    
    status_message = (
        f"📊 Статус инцидента {incident_id}\n\n"
        f"📍 Филиал: {incident['branch']}\n"
        f"🏢 Отдел: {incident['department']}\n"
        f"📝 Проблема: {incident['short_description']}\n"
        f"⚠️ Приоритет: {incident['priority']}\n"
        f"📈 Статус: {status}\n"
        f"⏰ Дедлайн: {deadline_str}\n"
        f"⏱ Осталось: {time_left_str}\n"
    )
    
    if incident.get('manager_report'):
        status_message += f"\n💬 Отчет: {incident['manager_report']}"
    
    await update.message.reply_text(status_message)

async def myincidents_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /myincidents - показывает ТОЛЬКО инциденты конкретного ответственного"""
    await show_typing(context, update.effective_chat.id)
    user_id = str(update.effective_user.id)
    
    # Определяем отдел пользователя
    user_department = None
    for dept, dept_id in settings.DEPARTMENT_HEADS.items():
        if dept_id == user_id:
            user_department = dept
            break
    
    if not user_department:
        await update.message.reply_text(
            "❌ Вы не являетесь ответственным ни за один отдел.\n"
            "Эта команда доступна только назначенным ответственным."
        )
        return
    
    # Получаем ВСЕ активные инциденты
    active_incidents_ids = incident_manager.redis.redis_client.smembers('roma_bot:active_incidents')
    
    # Фильтруем только те, за которые отвечает пользователь
    user_incidents = []
    for incident_id in active_incidents_ids:
        incident = incident_manager.get_incident(incident_id)
        if incident and str(incident.get('responsible_id')) == user_id:
            user_incidents.append(incident)
    
    if not user_incidents:
        await update.message.reply_text(
            f"📊 У вас нет активных инцидентов\n"
            f"Отдел: {user_department}"
        )
        return
    
    # Сортируем по приоритету и дедлайну
    priority_order = {'Критический': 0, 'Высокий': 1, 'Средний': 2, 'Низкий': 3}
    user_incidents.sort(key=lambda x: (priority_order.get(x.get('priority', 'Низкий'), 4), x.get('deadline', '')))
    
    message = f"📋 Ваши активные инциденты (Отдел: {user_department}):\n\n"
    
    for inc in user_incidents:
        # Безопасное получение дедлайна
        try:
            deadline = datetime.fromisoformat(inc['deadline'])
            deadline_str = deadline.strftime('%d.%m %H:%M')
            
            # Рассчитываем оставшееся время
            time_left = deadline - datetime.now()
            if time_left.total_seconds() > 0:
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                if hours > 4:
                    emoji = "🟢"
                elif hours > 1:
                    emoji = "🟡"
                else:
                    emoji = "🔴"
                time_str = f"{hours}ч {minutes}м"
            else:
                emoji = "⚫"
                time_str = "Просрочен!"
        except:
            emoji = "⚪"
            deadline_str = "Не указан"
            time_str = "—"
        
        message += (
            f"{emoji} {inc['id']}\n"
            f"   📍 {inc['branch']} | {inc['short_description'][:30]}...\n"
            f"   ⚠️ {inc['priority']} | ⏰ До: {deadline_str} ({time_str})\n\n"
        )
    
    message += (
        f"\n📊 Всего активных: {len(user_incidents)}\n"
        f"Для решения используйте:\n"
        f"/resolve [ID] [описание решения]"
    )
    
    await update.message.reply_text(message)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Игнорируем голосовые из группы
    if str(chat_id) == settings.TELEGRAM_GROUP_CHAT_ID:
        return
    
    if update.effective_chat.type != 'private':
        return
    
    # Показываем что обрабатываем
    await show_typing(context, chat_id)
    
    # Отправляем уведомление
    processing_msg = await update.message.reply_text(
        "🎤 Обрабатываю голосовое сообщение..."
    )
    
    try:
        # Получаем файл
        voice_file = await update.message.voice.get_file()
        
        # Загружаем в память
        voice_data = await voice_file.download_as_bytearray()
        file_name = f"voice_{user_id}_{update.message.message_id}.ogg"
        
        # Обрабатываем
        success, text = await voice_handler.process_voice_message(bytes(voice_data), file_name)
        
        if not success:
            await processing_msg.edit_text(text)
            return
            
        # Показываем распознанный текст
        await processing_msg.edit_text(
            f"📝 Распознанный текст:\n<i>{text}</i>",
            parse_mode='HTML'
        )
        
        # Теперь обрабатываем как текстовое сообщение
        await show_typing(context, chat_id)
        
        # Получаем информацию об авторе
        author_username = update.effective_user.username or "Неизвестный"
        author_name = update.effective_user.first_name or "Пользователь"
        author_info = f"@{author_username} ({author_name})"
        
        # Сохраняем в память
        memory_service.add_message(user_id, "user", f"[Голосовое]: {text}")
        
        # Получаем контексты
        user_context = user_contexts.get(user_id)
        conversation_history = memory_service.get_context(user_id)
        user_summary = memory_service.get_user_summary(user_id)
        
        # Обрабатываем через AI
        ai_response = ai_agent.process_message(
            text, 
            user_context, 
            conversation_history,
            user_summary
        )
        
        response_text = ai_response['response']
        
        if ai_response['type'] == 'incident':
            incident_data = ai_response.get('incident_data', {})
            
            if not all([incident_data.get('branch'), incident_data.get('department')]):
                await update.message.reply_text(response_text)
                memory_service.add_message(user_id, "assistant", response_text)
                return
            
            # Создаем инцидент
            if user_context:
                full_message = f"{user_context['original_message']}. {text}"
            else:
                full_message = text
            
            full_message_with_author = f"{full_message}\n\nАвтор: {author_info}"
            
            incident = ai_agent.create_incident_from_data(
                incident_data, 
                full_message_with_author
            )
            
            if incident:
                await show_typing(context, chat_id)
                
                incident.deadline = incident.calculate_deadline()
                incident.responsible_id = incident.get_responsible_id()
                
                # Сохраняем
                sheets_ok = sheets_service.append_incident(incident)
                incident_dict = incident.dict()
                incident_manager.save_incident(incident_dict)
                
                # Отправляем уведомления
                telegram_ok = await telegram_service.send_to_group(incident.to_telegram_message())
                
                if incident.responsible_id:
                    try:
                        responsible_message = (
                            f"🚨 Вам назначен новый инцидент!\n\n"
                            f"{incident.to_telegram_message(include_deadline=True)}\n\n"
                            f"Пожалуйста, решите проблему до дедлайна.\n"
                            f"После решения отправьте:\n"
                            f"/resolve {incident.id} [описание решения]"
                        )
                        await context.bot.send_message(
                            chat_id=incident.responsible_id,
                            text=responsible_message
                        )
                    except Exception as e:
                        print(f"Не удалось отправить ответственному: {e}")
                
                # Формируем ответ
                deadline_dt = datetime.fromisoformat(incident.deadline)
                deadline_str = deadline_dt.strftime('%d.%m.%Y %H:%M')
                
                base_response = (
                    f"✅ Инцидент зарегистрирован!\n\n"
                    f"📋 ID: {incident.id}\n"
                    f"📍 Филиал: {incident.branch}\n"
                    f"🏢 Отдел: {incident.department}\n"
                    f"⚠️ Приоритет: {incident.priority}\n"
                    f"⏰ Дедлайн: {deadline_str}\n"
                    f"👤 Ответственный уведомлен\n\n"
                    f"Менеджеры займутся решением проблемы."
                )
                
                await update.message.reply_text(base_response)
                
                memory_service.add_message(user_id, "assistant", base_response, {
                    "type": "incident",
                    "incident_id": incident.id,
                    "branch": incident.branch,
                    "department": incident.department,
                    "priority": incident.priority,
                    "author": author_info,
                    "deadline": incident.deadline
                })
                
                if user_id in user_contexts:
                    del user_contexts[user_id]
            else:
                await update.message.reply_text(response_text)
                memory_service.add_message(user_id, "assistant", response_text)
                
        elif ai_response['type'] == 'clarification':
            # Обновляем контекст
            if not user_context:
                user_contexts[user_id] = {
                    'original_message': text,
                    'partial_analysis': ai_response.get('incident_data', {}),
                    'author_info': author_info
                }
            else:
                user_contexts[user_id]['original_message'] += f". {text}"
                if ai_response.get('incident_data'):
                    user_contexts[user_id]['partial_analysis'].update(ai_response['incident_data'])
            
            await update.message.reply_text(response_text)
            memory_service.add_message(user_id, "assistant", response_text, {"type": "clarification"})
            
        else:  # not_incident
            await update.message.reply_text(response_text)
            memory_service.add_message(user_id, "assistant", response_text)
            
            if user_id in user_contexts:
                del user_contexts[user_id]
                
    except Exception as e:
        print(f"Ошибка обработки голоса: {e}")
        await processing_msg.edit_text(
            "❌ Не удалось обработать голосовое сообщение. Попробуйте написать текстом."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    print(f"Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            response = ai_agent.process_message("произошла ошибка", None)
            await update.effective_message.reply_text(
                response.get('response', 'Произошла ошибка. Попробуйте еще раз.')
            )
        except:
            await update.effective_message.reply_text(
                "Произошла ошибка. Попробуйте позже."
            )