import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import json
from config.settings import settings
from services.redis_memory import RedisMemory
from services.google_sheets import GoogleSheetsService
from services.telegram import TelegramService
from telegram import Bot

class IncidentManager:
    """Менеджер для управления инцидентами"""
    
    def __init__(self):
        self.redis = RedisMemory()
        self.sheets = GoogleSheetsService()
        self.telegram = TelegramService()
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        
    def _get_incident_key(self, incident_id: str) -> str:
        """Ключ для хранения инцидента в Redis"""
        return f"roma_bot:incident:{incident_id}"
    
    def _get_deadline_key(self, deadline: str) -> str:
        """Ключ для хранения дедлайнов"""
        return f"roma_bot:deadlines:{deadline}"
    
    def save_incident(self, incident: Dict) -> bool:
        """Сохраняет инцидент в Redis"""
        try:
            incident_key = self._get_incident_key(incident['id'])
            
            # Добавляем временные метки
            incident['created_at'] = datetime.now().isoformat()
            incident['deadline'] = self._calculate_deadline(incident['priority'])
            incident['responsible_id'] = settings.DEPARTMENT_HEADS.get(incident['department'])
            incident['status'] = 'OPEN'
            incident['reminders_sent'] = '[]'  # Сохраняем как JSON строку
            
            # Сохраняем в Redis
            self.redis.redis_client.hset(
                incident_key,
                mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                        for k, v in incident.items()}
            )
            
            # Устанавливаем TTL на 30 дней
            self.redis.redis_client.expire(incident_key, 30 * 24 * 60 * 60)
            
            # Добавляем в список активных инцидентов
            self.redis.redis_client.sadd('roma_bot:active_incidents', incident['id'])
            
            return True
            
        except Exception as e:
            print(f"Ошибка сохранения инцидента: {e}")
            return False
    
    def _calculate_deadline(self, priority: str) -> str:
        """Рассчитывает дедлайн"""
        from zoneinfo import ZoneInfo
        hours = settings.DEADLINES.get(priority, 24)
        tashkent_time = datetime.now(ZoneInfo('Asia/Tashkent'))
        deadline = tashkent_time + timedelta(hours=hours)
        return deadline.isoformat()
    
    def get_incident(self, incident_id: str) -> Optional[Dict]:
        """Получает инцидент из Redis"""
        try:
            incident_key = self._get_incident_key(incident_id)
            data = self.redis.redis_client.hgetall(incident_key)
            
            if not data:
                return None
            
            # Парсим JSON поля
            incident = {}
            for k, v in data.items():
                try:
                    incident[k] = json.loads(v)
                except:
                    incident[k] = v
                    
            return incident
            
        except Exception as e:
            print(f"Ошибка получения инцидента: {e}")
            return None
    
    def update_incident_status(self, incident_id: str, status: str, 
                            manager_report: Optional[str] = None) -> bool:
        """Обновляет статус инцидента"""
        try:
            incident_key = self._get_incident_key(incident_id)
            
            # Проверяем существование инцидента
            if not self.redis.redis_client.exists(incident_key):
                print(f"Инцидент {incident_id} не найден в Redis")
                return False
            
            # Обновляем статус
            self.redis.redis_client.hset(incident_key, 'status', status)
            
            if status == 'RESOLVED':
                self.redis.redis_client.hset(incident_key, 'resolved_at', 
                                        datetime.now().isoformat())
                # ВАЖНО: Удаляем из активных инцидентов
                self.redis.redis_client.srem('roma_bot:active_incidents', incident_id)
                print(f"Инцидент {incident_id} удален из активных")
                
            elif status == 'OVERDUE':
                # При просрочке оставляем в активных для возможности решения
                print(f"Инцидент {incident_id} помечен как просроченный")
                
            if manager_report:
                self.redis.redis_client.hset(incident_key, 'manager_report', manager_report)
            
            # Обновляем в Google Sheets
            self._update_sheet_status(incident_id, status, manager_report)
            
            return True
            
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
            return False
    
    def _update_sheet_status(self, incident_id: str, status: str, 
                           manager_report: Optional[str] = None):
        """Обновляет статус в Google Sheets"""
        try:
            # Получаем все инциденты
            incidents = self.sheets.get_all_incidents()
            
            # Находим нужный по ID
            for i, incident_row in enumerate(incidents):
                if incident_row[0] == incident_id:
                    row_number = i + 2  # +2 так как индексация с 1 и есть заголовок
                    
                    # Обновляем статус (колонка J)
                    range_status = f"{settings.SHEET_NAME}!J{row_number}"
                    self.sheets.service.spreadsheets().values().update(
                        spreadsheetId=self.sheets.spreadsheet_id,
                        range=range_status,
                        valueInputOption='USER_ENTERED',
                        body={'values': [[settings.INCIDENT_STATUSES[status]]]}
                    ).execute()
                    
                    # Обновляем отчет менеджера если есть (колонка I)
                    if manager_report:
                        range_report = f"{settings.SHEET_NAME}!I{row_number}"
                        self.sheets.service.spreadsheets().values().update(
                            spreadsheetId=self.sheets.spreadsheet_id,
                            range=range_report,
                            valueInputOption='USER_ENTERED',
                            body={'values': [[manager_report]]}
                        ).execute()
                    
                    break
                    
        except Exception as e:
            print(f"Ошибка обновления в Sheets: {e}")
    
    async def send_reminder(self, incident_id: str, minutes_before: int):
        """Отправляет напоминание ответственному"""
        try:
            incident = self.get_incident(incident_id)
            
            # Проверяем что инцидент не решен
            if not incident or incident.get('status') != 'OPEN':
                return
            
            responsible_id = incident.get('responsible_id')
            if not responsible_id:
                return
            
            deadline = datetime.fromisoformat(incident['deadline'])
            deadline_str = deadline.strftime('%d.%m.%Y %H:%M')
            
            message = (
                f"⏰ Напоминание об инциденте!\n\n"
                f"ID: {incident['id']}\n"
                f"📍 Филиал: {incident['branch']}\n"
                f"⚠️ Приоритет: {incident['priority']}\n"
                f"📝 Проблема: {incident['short_description']}\n"
                f"⏱ Осталось времени: {minutes_before} минут\n"
                f"🏁 Дедлайн: {deadline_str}\n\n"
                f"Пожалуйста, решите проблему и отправьте отчет командой:\n"
                f"/resolve {incident['id']} [описание решения]"
            )
            
            await self.bot.send_message(chat_id=responsible_id, text=message)
            
            # Отмечаем что напоминание отправлено
            # ИСПРАВЛЕНИЕ: правильно работаем с JSON
            reminders_str = incident.get('reminders_sent', '[]')
            if isinstance(reminders_str, str):
                reminders = json.loads(reminders_str)
            else:
                reminders = reminders_str if isinstance(reminders_str, list) else []
                
            reminders.append(minutes_before)
            
            self.redis.redis_client.hset(
                self._get_incident_key(incident_id),
                'reminders_sent',
                json.dumps(reminders)
            )
            
        except Exception as e:
            print(f"Ошибка отправки напоминания для {incident_id}: {e}")

    async def check_deadlines(self):
        """Проверяет дедлайны и отправляет напоминания"""
        while True:
            try:
                # Получаем все активные инциденты
                active_incidents = self.redis.redis_client.smembers('roma_bot:active_incidents')
                
                for incident_id in active_incidents:
                    incident = self.get_incident(incident_id)
                    if not incident:
                        continue
                    
                    # ВАЖНО: Пропускаем решенные инциденты
                    if incident.get('status') == 'RESOLVED':
                        # Удаляем из активных если еще там
                        self.redis.redis_client.srem('roma_bot:active_incidents', incident_id)
                        continue
                    
                    # Проверяем дедлайн только для открытых инцидентов
                    if incident.get('status') == 'OPEN':
                        try:
                            deadline = datetime.fromisoformat(incident['deadline'])
                            now = datetime.now()
                            time_left = deadline - now
                            
                            # Проверяем просрочку
                            if time_left.total_seconds() <= 0:
                                self.update_incident_status(incident_id, 'OVERDUE')
                                await self._send_overdue_notification(incident)
                                continue
                            
                            # Проверяем напоминания
                            minutes_left = time_left.total_seconds() / 60
                            reminders_sent = incident.get('reminders_sent', [])
                            
                            for reminder_time in settings.REMINDER_INTERVALS:
                                if (minutes_left <= reminder_time and 
                                    reminder_time not in reminders_sent):
                                    await self.send_reminder(incident_id, reminder_time)
                        except Exception as e:
                            print(f"Ошибка проверки дедлайна для {incident_id}: {e}")
                            continue
                
                # Ждем 1 минуту перед следующей проверкой
                await asyncio.sleep(60)
                
            except Exception as e:
                print(f"Ошибка в проверке дедлайнов: {e}")
                await asyncio.sleep(60)
                    
    async def _send_overdue_notification(self, incident: Dict):
        """Отправляет уведомление о просрочке"""
        responsible_id = incident.get('responsible_id')
        if not responsible_id:
            return
        
        message = (
            f"🚨 ИНЦИДЕНТ ПРОСРОЧЕН!\n\n"
            f"ID: {incident['id']}\n"
            f"📍 Филиал: {incident['branch']}\n"
            f"🏢 Отдел: {incident['department']}\n"
            f"⚠️ Приоритет: {incident['priority']}\n"
            f"📝 Проблема: {incident['short_description']}\n\n"
            f"Срочно решите проблему и отправьте отчет!"
        )
        
        await self.bot.send_message(chat_id=responsible_id, text=message)