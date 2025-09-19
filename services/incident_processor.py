"""
Incident processing service
Handles all incident-related business logic following DRY principles
"""
from typing import Dict, Optional, Tuple, Any, List
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from ai.agent import IncidentAIAgent
from services.google_sheets import GoogleSheetsService
from services.telegram import TelegramService
from services.redis_memory import RedisMemory
from services.incident_manager import IncidentManager
from config.settings import settings
from bot.constants import Messages, Errors, LogMessages, DebugMessages


class IncidentProcessor:
    """Centralized incident processing service"""
    
    def __init__(self):
        self.ai_agent = IncidentAIAgent()
        self.sheets_service = GoogleSheetsService()
        self.telegram_service = TelegramService()
        self.memory_service = RedisMemory()
        self.incident_manager = IncidentManager()
    
    async def process_text_message(
        self, 
        message_text: str, 
        user_id: int, 
        author_info: str,
        user_context: Optional[Dict] = None,
        conversation_history: Optional[list] = None,
        user_summary: Optional[Dict] = None
    ) -> Tuple[str, Optional[Dict], str]:
        """
        Processes text message for incident creation
        Returns: (response_text, incident_data, response_type)
        """
        # Save user message
        self.memory_service.add_message(user_id, "user", message_text)
        
        # Get context and history
        if conversation_history is None:
            conversation_history = self.memory_service.get_context(user_id)
        if user_summary is None:
            user_summary = self.memory_service.get_user_summary(user_id)
        
        # Process through AI
        ai_response = self.ai_agent.process_message(
            message_text, 
            user_context, 
            conversation_history,
            user_summary
        )
        
        response_text = ai_response['response']
        response_type = ai_response['type']
        
        if response_type == 'incident':
            incident_data = ai_response.get('incident_data', {})
            
            if not all([incident_data.get('branch'), incident_data.get('department')]):
                return response_text, None, 'incomplete'
            
            # Create incident with author info
            if user_context:
                full_message = f"{user_context['original_message']}. {message_text}"
            else:
                full_message = message_text
            
            full_message_with_author = f"{full_message}\n\nАвтор: {author_info}"
            
            incident = self.ai_agent.create_incident_from_data(
                incident_data, 
                full_message_with_author
            )
            
            if incident:
                # Add deadline and responsible
                deadline_info = self.ai_agent.calculate_smart_deadline(
                    incident_data, 
                    full_message
                )
                incident.deadline = deadline_info['deadline']
                responsible_id = incident.get_responsible_id()
                incident.responsible_id = str(responsible_id) if responsible_id else None
                
                # Save incident data
                incident_dict = incident.dict()
                incident_dict['user_id'] = str(user_id)
                self.incident_manager.save_incident(incident_dict)
                print(LogMessages.INCIDENT_SAVING.format(incident_id=incident.id))
                
                return Messages.INCIDENT_ACCEPTED, {
                    'incident': incident,
                    'deadline_reasoning': deadline_info['reasoning'],
                    'full_message_with_author': full_message_with_author
                }, 'incident'
        
        return response_text, None, response_type
    
    async def handle_incident_creation(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        incident_data: Dict,
        user_id: int,
        author_info: str
    ) -> None:
        """Handles response after incident creation"""
        incident = incident_data['incident']
        
        await update.message.reply_text(Messages.INCIDENT_ACCEPTED)
        
        # Save to memory
        self.memory_service.add_message(user_id, "assistant", Messages.INCIDENT_ACCEPTED, {
            "type": "incident_created",
            "incident_id": incident.id,
            "status": "waiting_for_photo"
        })
    
    async def handle_photo_processing(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        user_context: Dict,
        user_id: int
    ) -> None:
        """Handles photo processing for incidents"""
        try:
            # Get photo
            photo = update.message.photo[-1]  # Get largest photo
            file_id = photo.file_id
            
            # Download file
            print(LogMessages.PHOTO_DOWNLOADING)
            file = await context.bot.get_file(file_id)
            file_data = await file.download_as_bytearray()
            file_size = len(file_data)
            
            # Determine file extension
            file_extension = self._detect_file_format(file_data)
            
            # Validate photo
            print(LogMessages.PHOTO_VALIDATING)
            is_valid, error_msg = self._validate_photo(file_extension, file_size)
            
            if not is_valid:
                await update.message.reply_text(Errors.PHOTO_VALIDATION_ERROR.format(error=error_msg))
                return
            
            # Get incident from Redis
            incident = self.incident_manager.get_incident(user_context['incident_id'])
            if not incident:
                await update.message.reply_text(Errors.INCIDENT_NOT_FOUND.format(incident_id=user_context['incident_id']))
                return
            
            # Process photo based on type
            if user_context.get('waiting_for_solution_photo'):
                await self._process_solution_photo(update, context, incident, file_data, file_extension, user_context, user_id)
            else:
                await self._process_incident_photo(update, context, incident, file_data, file_extension, user_context, user_id)
                
        except Exception as e:
            print(f"Ошибка обработки фото: {e}")
            await update.message.reply_text(Errors.GENERAL_ERROR)
    
    async def _process_incident_photo(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        incident: Dict,
        file_data: bytes,
        file_extension: str,
        user_context: Dict,
        user_id: int
    ) -> None:
        """Processes incident photo"""
        print(LogMessages.PHOTO_SAVING)
        
        # Add incident to Google Sheets first
        incident_obj = self._create_incident_object(incident)
        sheets_ok = self.sheets_service.append_incident(incident_obj)
        if not sheets_ok:
            await update.message.reply_text(Errors.SHEETS_ERROR)
            return
        
        # Insert image into Google Sheets
        try:
            problem_description = incident.get('short_description', '')
            success, result = self.sheets_service.insert_image(
                file_data, 
                user_context['incident_id'], 
                problem_description,
                file_extension
            )
            
            if not success:
                await update.message.reply_text(Errors.PHOTO_SAVE_ERROR.format(error=result))
                return
                
        except Exception as e:
            print(f"Ошибка вставки изображения: {e}")
            await update.message.reply_text(Errors.PHOTO_SAVE_ERROR.format(error="Ошибка сохранения фото в таблице"))
            return
        
        # Update incident with photo in Redis
        incident['photo_file_id'] = update.message.photo[-1].file_id
        incident['has_image'] = True
        self.incident_manager.save_incident(incident)
        
        # Update in Google Sheets
        print(LogMessages.SHEETS_UPDATING)
        self.sheets_service.update_incident_with_image(incident)
        
        # Send notifications
        await self._send_incident_notifications(context, incident, file_data)
        
        # Send success response
        deadline_dt = datetime.fromisoformat(incident['deadline'])
        deadline_str = deadline_dt.strftime('%d.%m.%Y %H:%M')
        
        full_response = Messages.PHOTO_SAVED_SUCCESS.format(
            incident_id=incident['id'],
            branch=incident['branch'],
            department=incident['department'],
            priority=incident['priority'],
            deadline=deadline_str
        )
        
        await update.message.reply_text(full_response)
        
        # Save to memory
        self.memory_service.add_message(user_id, "assistant", full_response, {
            "type": "incident_completed",
            "incident_id": incident['id'],
            "branch": incident['branch'],
            "department": incident['department'],
            "priority": incident['priority'],
            "deadline": incident['deadline'],
            "status": "sent_to_managers"
        })
    
    async def _process_solution_photo(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        incident: Dict,
        file_data: bytes,
        file_extension: str,
        user_context: Dict,
        user_id: int
    ) -> None:
        """Processes solution photo"""
        print(LogMessages.PHOTO_SAVING)
        
        # Save solution photo
        success, result = self.sheets_service.insert_solution_image(
            file_data, 
            user_context['incident_id'], 
            user_context['resolution'],
            file_extension
        )
        
        if not success:
            await update.message.reply_text(Errors.PHOTO_SAVE_ERROR.format(error=result))
            return
        
        # Update incident
        incident['solution_photo_file_id'] = update.message.photo[-1].file_id
        incident['has_solution_image'] = True
        incident['status'] = 'RESOLVED'
        self.incident_manager.save_incident(incident)
        
        # Update in Google Sheets
        print(LogMessages.SHEETS_UPDATING)
        self.sheets_service.update_incident_with_image(incident)
        
        # Send completion notification
        await self._send_solution_notification(context, incident, file_data, user_context)
        
        # Send success response
        await update.message.reply_text(Messages.SOLUTION_PHOTO_SAVED)
    
    async def _send_incident_notifications(
        self, 
        context: ContextTypes.DEFAULT_TYPE,
        incident: Dict,
        file_data: bytes
    ) -> None:
        """Sends incident notifications to group and responsible"""
        print(LogMessages.NOTIFICATION_SENDING)
        
        incident_obj = self._create_incident_object(incident)
        
        # Send to group with photo
        try:
            # Convert bytearray to bytes for proper sending
            photo_bytes = bytes(file_data) if isinstance(file_data, bytearray) else file_data
            
            await context.bot.send_photo(
                chat_id=settings.TELEGRAM_GROUP_CHAT_ID,
                photo=photo_bytes,
                caption=incident_obj.to_telegram_message()
            )
            print("✅ Фото отправлено в группу")
        except Exception as e:
            print(f"Ошибка отправки фото в группу: {e}")
            # Fallback to text only
            await self.telegram_service.send_to_group(incident_obj.to_telegram_message())
        
        # Send to responsible with photo
        if incident.get('responsible_id'):
            try:
                deadline_dt = datetime.fromisoformat(incident['deadline'])
                deadline_str = deadline_dt.strftime('%d.%m.%Y %H:%M')
                
                responsible_message = (
                    f"🚨 Вам назначен новый инцидент!\n\n"
                    f"{incident_obj.to_telegram_message(include_deadline=True)}\n\n"
                    f"Пожалуйста, решите проблему до дедлайна.\n"
                    f"После решения отправьте:\n"
                    f"/resolve {incident['id']} [описание решения]"
                )
                
                # Convert bytearray to bytes for proper sending
                photo_bytes = bytes(file_data) if isinstance(file_data, bytearray) else file_data
                
                await context.bot.send_photo(
                    chat_id=incident['responsible_id'],
                    photo=photo_bytes,
                    caption=responsible_message
                )
                print("✅ Фото отправлено ответственному")
            except Exception as e:
                print(f"Не удалось отправить ответственному: {e}")
                # Fallback to text only
                try:
                    await context.bot.send_message(
                        chat_id=incident['responsible_id'],
                        text=responsible_message
                    )
                    print("✅ Текст отправлен ответственному")
                except Exception as e2:
                    print(f"Не удалось отправить ответственному даже текст: {e2}")
    
    async def _send_solution_notification(
        self, 
        context: ContextTypes.DEFAULT_TYPE,
        incident: Dict,
        file_data: bytes,
        user_context: Dict
    ) -> None:
        """Sends solution notification to group"""
        completion_message = (
            f"✅ Инцидент {incident['id']} решен!\n\n"
            f"📍 Филиал: {incident.get('branch', 'Неизвестно')}\n"
            f"🏢 Отдел: {incident.get('department', 'Неизвестно')}\n"
            f"📝 Проблема: {incident.get('short_description', 'Не указано')}\n"
            f"✨ Решение: {user_context['resolution']}\n"
            f"👤 Решил: @{user_context['resolved_by']}"
        )
        
        try:
            # Convert bytearray to bytes for proper sending
            photo_bytes = bytes(file_data) if isinstance(file_data, bytearray) else file_data
            
            await context.bot.send_photo(
                chat_id=settings.TELEGRAM_GROUP_CHAT_ID,
                photo=photo_bytes,
                caption=completion_message
            )
            print("✅ Фото решения отправлено в группу")
        except Exception as e:
            print(f"Ошибка отправки фото решения в группу: {e}")
            await self.telegram_service.send_to_group(completion_message)
            print("✅ Текст решения отправлен в группу")
    
    def _create_incident_object(self, incident: Dict):
        """Creates Incident object from dict"""
        from models.incident import Incident
        
        # Ensure responsible_id is string
        if 'responsible_id' in incident and isinstance(incident['responsible_id'], int):
            incident['responsible_id'] = str(incident['responsible_id'])
        
        return Incident(**incident)
    
    def _detect_file_format(self, file_data: bytes) -> str:
        """Detects file format from magic bytes"""
        from bot.constants import FileHandling
        
        for magic_bytes, extension in FileHandling.MAGIC_BYTES.items():
            if file_data.startswith(magic_bytes):
                if extension == 'webp' and b'WEBP' not in file_data[:12]:
                    continue
                return extension
        return 'jpg'  # Default to JPEG
    
    def _validate_photo(self, file_extension: str, file_size: int) -> Tuple[bool, str]:
        """Validates photo file"""
        from utils.validators import validate_photo
        return validate_photo(file_extension, file_size)
