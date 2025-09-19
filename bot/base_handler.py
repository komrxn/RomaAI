"""
Base message handler for Roma Pizza Bot
Provides common functionality for all message types (text, voice, photo)
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, Tuple
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from ai.agent import IncidentAIAgent
from services.google_sheets import GoogleSheetsService
from services.telegram import TelegramService
from services.redis_memory import RedisMemory
from services.incident_manager import IncidentManager
from config.settings import settings


class BaseMessageHandler(ABC):
    """Base class for all message handlers following DRY principles"""
    
    def __init__(self):
        self.ai_agent = IncidentAIAgent()
        self.sheets_service = GoogleSheetsService()
        self.telegram_service = TelegramService()
        self.memory_service = RedisMemory()
        self.incident_manager = IncidentManager()
    
    async def show_typing(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        """Shows typing indicator"""
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
    
    def get_author_info(self, update: Update) -> str:
        """Extracts author information from update"""
        author_username = update.effective_user.username or "Неизвестный"
        author_name = update.effective_user.first_name or "Пользователь"
        return f"@{author_username} ({author_name})"
    
    def is_private_chat(self, update: Update) -> bool:
        """Checks if message is from private chat"""
        return update.effective_chat.type == 'private'
    
    def is_group_chat(self, update: Update) -> bool:
        """Checks if message is from group chat"""
        return str(update.effective_chat.id) == settings.TELEGRAM_GROUP_CHAT_ID
    
    def should_ignore_message(self, update: Update) -> bool:
        """Determines if message should be ignored"""
        return self.is_group_chat(update) or not self.is_private_chat(update)
    
    async def process_incident_creation(
        self, 
        message_text: str, 
        user_id: int, 
        author_info: str,
        user_context: Optional[Dict] = None,
        conversation_history: Optional[list] = None,
        user_summary: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Processes incident creation with AI analysis
        Returns: (is_incident, response_text, incident_data)
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
        
        if ai_response['type'] == 'incident':
            incident_data = ai_response.get('incident_data', {})
            
            if not all([incident_data.get('branch'), incident_data.get('department')]):
                return False, response_text, None
            
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
                incident.responsible_id = incident.get_responsible_id()
                
                # Save incident data
                incident_dict = incident.dict()
                incident_dict['user_id'] = str(user_id)
                self.incident_manager.save_incident(incident_dict)
                
                return True, response_text, {
                    'incident': incident,
                    'deadline_reasoning': deadline_info['reasoning'],
                    'full_message_with_author': full_message_with_author
                }
        
        return False, response_text, None
    
    async def handle_incident_response(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        incident_data: Dict,
        user_id: int,
        author_info: str
    ) -> None:
        """Handles response after incident creation"""
        incident = incident_data['incident']
        deadline_reasoning = incident_data['deadline_reasoning']
        
        # Simple confirmation without details - full info will be after photo
        base_response = (
            f"🟠 Отчет принят!\n\n"
            f"📸 Теперь отправьте фото подтверждение проблемы.\n"
            f"Только после получения фото отчет будет отправлен менеджерам."
        )
        
        await update.message.reply_text(base_response)
        
        # Save to memory
        self.memory_service.add_message(user_id, "assistant", base_response, {
            "type": "incident_created",
            "incident_id": incident.id,
            "status": "waiting_for_photo"
        })
    
    async def handle_clarification_response(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        response_text: str,
        user_id: int,
        author_info: str,
        ai_response: Dict,
        user_context: Optional[Dict] = None
    ) -> None:
        """Handles clarification response"""
        await update.message.reply_text(response_text)
        self.memory_service.add_message(user_id, "assistant", response_text, {"type": "clarification"})
    
    async def handle_non_incident_response(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        response_text: str,
        user_id: int
    ) -> None:
        """Handles non-incident response"""
        await update.message.reply_text(response_text)
        self.memory_service.add_message(user_id, "assistant", response_text)
    
    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Abstract method to handle specific message type"""
        pass
