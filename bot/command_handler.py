"""
Command handler
Handles all bot commands following DRY principles
"""
from typing import Dict, Optional, Any
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from bot.base_handler import BaseMessageHandler
from services.google_sheets import GoogleSheetsService
from services.redis_memory import RedisMemory
from services.incident_manager import IncidentManager
from config.settings import settings
from bot.constants import Messages, Errors, Commands


class CommandHandler(BaseMessageHandler):
    """Handles all bot commands"""
    
    def __init__(self):
        super().__init__()
        self.sheets_service = GoogleSheetsService()
        self.memory_service = RedisMemory()
        self.incident_manager = IncidentManager()
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /start command"""
        await self.show_typing(context, update.effective_chat.id)
        user_id = update.effective_user.id
        username = update.effective_user.username or "Пользователь"
        
        # Save user info
        self.memory_service.update_user_info(user_id, {
            "username": username,
            "first_name": update.effective_user.first_name,
            "chat_id": update.effective_chat.id
        })
        
        # Get user summary
        user_summary = self.memory_service.get_user_summary(user_id)
        
        if user_summary['incidents_count'] > 0:
            welcome = Messages.WELCOME_RETURNING_USER.format(
                name=update.effective_user.first_name,
                count=user_summary['incidents_count']
            )
            
            if user_summary['frequent_branches']:
                branches = ", ".join([b[0] for b in user_summary['frequent_branches'][:2]])
                welcome += f"• Частые филиалы: {branches}\n"
        else:
            welcome = Messages.WELCOME_NEW_USER.format(name=update.effective_user.first_name)
        
        welcome += Messages.WELCOME_COMMANDS
        
        await update.message.reply_text(welcome)
        
        # Save to memory
        self.memory_service.add_message(user_id, "user", "/start")
        self.memory_service.add_message(user_id, "assistant", welcome)
    
    async def handle_rep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /rep command with global statistics"""
        if not self.is_private_chat(update):
            return
        
        await self.show_typing(context, update.effective_chat.id)
        text = update.message.text
        query = text[4:].strip() if len(text) > 4 else ""
        
        if not query:
            await update.message.reply_text(Commands.REP_USAGE)
            return
        
        msg = await update.message.reply_text("🔍 Анализирую данные...")
        
        try:
            # Get data
            incidents = self.sheets_service.get_all_incidents()
            
            if not incidents:
                await msg.edit_text("📊 Нет данных для анализа.")
                return
            
            # Get global statistics
            global_stats = self.memory_service.get_global_stats()
            
            # Analyze through AI
            analysis = self.ai_agent.analyze_incidents_data(incidents, query, global_stats)
            
            # Send result
            if len(analysis) > 4000:
                await msg.edit_text(analysis[:4000])
                for i in range(4000, len(analysis), 4000):
                    await update.message.reply_text(analysis[i:i+4000])
            else:
                await msg.edit_text(analysis)
            
            # Save to memory
            self.memory_service.add_message(update.effective_user.id, "user", f"/rep {query}")
            self.memory_service.add_message(update.effective_user.id, "assistant", analysis[:500] + "...")
                
        except Exception as e:
            print(f"Analysis error: {e}")
            await msg.edit_text("❌ Ошибка при анализе. Попробуйте позже.")
    
    async def handle_mystats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /mystats command - personal statistics"""
        if not self.is_private_chat(update):
            return
        
        await self.show_typing(context, update.effective_chat.id)
        user_id = update.effective_user.id
        user_summary = self.memory_service.get_user_summary(user_id)
        
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
        
        # Get recent incidents from history
        history = self.memory_service.get_context(user_id, 20)
        recent_incidents = []
        
        for msg in history:
            if msg.get('metadata', {}).get('type') == 'incident':
                recent_incidents.append(msg['metadata'])
        
        if recent_incidents:
            stats_message += f"\n**Последние инциденты:**\n"
            for inc in recent_incidents[-3:]:
                stats_message += f"• {inc.get('incident_id', 'N/A')} - {inc.get('branch', 'N/A')}\n"
        
        await update.message.reply_text(stats_message, parse_mode='Markdown')
    
    async def handle_globalstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /globalstats command - global system statistics"""
        if not self.is_private_chat(update):
            return
        
        await self.show_typing(context, update.effective_chat.id)
        global_stats = self.memory_service.get_global_stats()
        
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
    
    async def handle_resolve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /resolve command for incident resolution"""
        await self.show_typing(context, update.effective_chat.id)
        
        if len(context.args) < 2:
            await update.message.reply_text(Commands.RESOLVE_USAGE)
            return
        
        incident_id = context.args[0]
        resolution = ' '.join(context.args[1:])
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or "Unknown"
        
        # Get incident
        incident = self.incident_manager.get_incident(incident_id)
        
        if not incident:
            await update.message.reply_text(Errors.INCIDENT_NOT_FOUND.format(incident_id=incident_id))
            return
        
        # Check status
        current_status = incident.get('status', 'OPEN')
        if current_status == 'RESOLVED':
            await update.message.reply_text(Errors.INCIDENT_ALREADY_RESOLVED.format(incident_id=incident_id))
            return
        
        # Check if user is responsible
        responsible_id = str(incident.get('responsible_id', ''))
        
        if user_id != responsible_id:
            await update.message.reply_text(Errors.NOT_RESPONSIBLE.format(
                responsible_id=responsible_id,
                user_id=user_id
            ))
            return
        
        # Save resolution and request photo
        incident['resolution'] = resolution
        incident['resolved_by'] = username
        incident['status'] = 'PENDING_PHOTO'
        self.incident_manager.save_incident(incident)
        
        # Set context for solution photo waiting
        if not hasattr(self, 'user_contexts'):
            self.user_contexts = {}
        self.user_contexts[str(user_id)] = {
            'waiting_for_solution_photo': True,
            'incident_id': incident_id,
            'resolution': resolution,
            'resolved_by': username
        }
        
        await update.message.reply_text(Messages.SOLUTION_ACCEPTED.format(
            incident_id=incident_id,
            resolution=resolution
        ))
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /status command for incident status check"""
        await self.show_typing(context, update.effective_chat.id)
        
        if not context.args:
            await update.message.reply_text(Commands.STATUS_USAGE)
            return
        
        incident_id = context.args[0]
        
        # Get incident
        incident = self.incident_manager.get_incident(incident_id)
        
        if not incident:
            await update.message.reply_text(Errors.INCIDENT_NOT_FOUND.format(incident_id=incident_id))
            return
        
        # Format status
        status = settings.INCIDENT_STATUSES.get(incident.get('status', 'OPEN'))
        deadline = datetime.fromisoformat(incident['deadline'])
        deadline_str = deadline.strftime('%d.%m.%Y %H:%M')
        
        # Calculate remaining time
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
    
    async def handle_myincidents(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /myincidents command - shows incidents for responsible person"""
        await self.show_typing(context, update.effective_chat.id)
        user_id = str(update.effective_user.id)
        
        # Determine user department
        user_department = None
        for dept, dept_id in settings.DEPARTMENT_HEADS.items():
            if dept_id == user_id:
                user_department = dept
                break
        
        if not user_department:
            await update.message.reply_text(Errors.NOT_DEPARTMENT_HEAD)
            return
        
        # Get all active incidents
        active_incidents_ids = self.incident_manager.redis.redis_client.smembers('roma_bot:active_incidents')
        
        # Filter only user's incidents
        user_incidents = []
        for incident_id in active_incidents_ids:
            incident = self.incident_manager.get_incident(incident_id)
            if incident and str(incident.get('responsible_id')) == user_id:
                user_incidents.append(incident)
        
        if not user_incidents:
            await update.message.reply_text(
                f"📊 У вас нет активных инцидентов\n"
                f"Отдел: {user_department}"
            )
            return
        
        # Sort by priority and deadline
        priority_order = {'Критический': 0, 'Высокий': 1, 'Средний': 2, 'Низкий': 3}
        user_incidents.sort(key=lambda x: (priority_order.get(x.get('priority', 'Низкий'), 4), x.get('deadline', '')))
        
        message = f"📋 Ваши активные инциденты (Отдел: {user_department}):\n\n"
        
        for inc in user_incidents:
            # Safe deadline handling
            try:
                deadline = datetime.fromisoformat(inc['deadline'])
                deadline_str = deadline.strftime('%d.%m %H:%M')
                
                # Calculate remaining time
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
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Main command handler - delegates to specific command handlers"""
        command = update.message.text.split()[0] if update.message.text else ""
        
        if command == "/start":
            await self.handle_start(update, context)
        elif command == "/rep":
            await self.handle_rep(update, context)
        elif command == "/mystats":
            await self.handle_mystats(update, context)
        elif command == "/globalstats":
            await self.handle_globalstats(update, context)
        elif command == "/resolve":
            await self.handle_resolve(update, context)
        elif command == "/status":
            await self.handle_status(update, context)
        elif command == "/myincidents":
            await self.handle_myincidents(update, context)
