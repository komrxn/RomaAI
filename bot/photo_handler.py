"""
Photo message handler
Handles photo message incidents following DRY principles
"""
from typing import Dict, Optional, Any
from telegram import Update
from telegram.ext import ContextTypes

from bot.base_handler import BaseMessageHandler
from services.incident_processor import IncidentProcessor
from bot.constants import Messages, DebugMessages


class PhotoMessageHandler(BaseMessageHandler):
    """Handles photo message incidents"""
    
    def __init__(self):
        super().__init__()
        self.incident_processor = IncidentProcessor()
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles photo message incidents"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Check if message should be ignored
        if self.should_ignore_message(update):
            return
        
        await self.show_typing(context, chat_id)
        
        # Get user context
        user_context = getattr(self, 'user_contexts', {}).get(str(user_id))
        print(DebugMessages.USER_CONTEXT.format(user_context=user_context))
        print(DebugMessages.WAITING_FOR_PHOTO.format(
            waiting_for_photo=user_context.get('waiting_for_photo') if user_context else None
        ))
        print(DebugMessages.WAITING_FOR_PHOTO.format(
            waiting_for_photo=user_context.get('waiting_for_solution_photo') if user_context else None
        ))
        
        if not user_context or (not user_context.get('waiting_for_photo') and not user_context.get('waiting_for_solution_photo')):
            print(DebugMessages.PHOTO_IGNORED)
            await update.message.reply_text(Messages.PHOTO_WITHOUT_CONTEXT)
            return
        
        # Determine photo type
        if user_context.get('waiting_for_solution_photo'):
            print(DebugMessages.PHOTO_RECEIVED.format(type="РЕШЕНИЯ", incident_id=user_context['incident_id']))
        else:
            print(DebugMessages.PHOTO_RECEIVED.format(type="ПРОБЛЕМЫ", incident_id=user_context['incident_id']))
        
        # Process photo through incident processor
        await self.incident_processor.handle_photo_processing(
            update, context, user_context, user_id
        )
        
        # Clear context after processing
        print(DebugMessages.CONTEXT_CLEANING)
        if hasattr(self, 'user_contexts') and str(user_id) in self.user_contexts:
            del self.user_contexts[str(user_id)]
