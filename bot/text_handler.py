"""
Text message handler
Handles text-based incident reports following DRY principles
"""
from typing import Dict, Optional, Any
from telegram import Update
from telegram.ext import ContextTypes

from bot.base_handler import BaseMessageHandler
from services.incident_processor import IncidentProcessor
from bot.constants import Messages, DebugMessages


class TextMessageHandler(BaseMessageHandler):
    """Handles text message incidents"""
    
    def __init__(self):
        super().__init__()
        self.incident_processor = IncidentProcessor()
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles text message incidents"""
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        chat_id = update.effective_chat.id
        
        await self.show_typing(context, chat_id)
        
        # Check if message should be ignored
        if self.should_ignore_message(update):
            return
        
        # Get author info
        author_info = self.get_author_info(update)
        
        # Check for pending incidents
        pending_incident = self.incident_manager.get_pending_incident_for_user_simple(str(user_id))
        print(DebugMessages.USER_ID_CHECK.format(user_id=user_id, pending_incident=pending_incident is not None))
        
        if pending_incident:
            print(DebugMessages.INCIDENT_FOUND.format(
                incident_id=pending_incident['id'], 
                has_image=pending_incident.get('has_image', False)
            ))
        
        # Get user context
        user_context = getattr(self, 'user_contexts', {}).get(str(user_id))
        print(DebugMessages.USER_CONTEXT.format(user_context=user_context))
        
        waiting_for_photo = user_context and user_context.get('waiting_for_photo', False)
        print(DebugMessages.WAITING_FOR_PHOTO.format(waiting_for_photo=waiting_for_photo))
        print(DebugMessages.BLOCKING_CONDITION.format(
            pending_incident=pending_incident is not None, 
            waiting_for_photo=waiting_for_photo
        ))
        
        if pending_incident and not waiting_for_photo:
            # Set context for existing incident
            if not hasattr(self, 'user_contexts'):
                self.user_contexts = {}
            self.user_contexts[str(user_id)] = {
                'waiting_for_photo': True,
                'incident_id': pending_incident['id'],
                'original_message': pending_incident.get('full_message', ''),
                'author_info': author_info
            }
            
            await update.message.reply_text(
                Messages.PENDING_INCIDENT_WARNING.format(incident_id=pending_incident['id'])
            )
            return
        
        # Process incident creation
        response_text, incident_data, response_type = await self.incident_processor.process_text_message(
            message_text, user_id, author_info, user_context
        )
        
        if response_type == 'incident' and incident_data:
            await self.incident_processor.handle_incident_creation(
                update, context, incident_data, user_id, author_info
            )
            
            # Set context for photo waiting
            if not hasattr(self, 'user_contexts'):
                self.user_contexts = {}
            self.user_contexts[str(user_id)] = {
                'waiting_for_photo': True,
                'incident_id': incident_data['incident'].id,
                'original_message': incident_data['full_message_with_author'],
                'author_info': author_info
            }
            
        elif response_type == 'clarification':
            await self.incident_processor.handle_clarification_response(
                update, context, response_text, user_id, author_info, 
                {'type': 'clarification'}, user_context
            )
            
            # Update context
            if not hasattr(self, 'user_contexts'):
                self.user_contexts = {}
            if not user_context:
                self.user_contexts[str(user_id)] = {
                    'original_message': message_text,
                    'partial_analysis': {},
                    'author_info': author_info
                }
            else:
                self.user_contexts[str(user_id)]['original_message'] += f". {message_text}"
                
        else:  # not_incident
            await self.incident_processor.handle_non_incident_response(
                update, context, response_text, user_id
            )
            
            # Clear context
            if hasattr(self, 'user_contexts') and str(user_id) in self.user_contexts:
                del self.user_contexts[str(user_id)]
