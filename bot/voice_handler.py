"""
Voice message handler
Handles voice message incidents following DRY principles
"""
from typing import Dict, Optional, Any
from telegram import Update
from telegram.ext import ContextTypes

from bot.base_handler import BaseMessageHandler
from services.voice_handler import VoiceHandler
from services.incident_processor import IncidentProcessor
from bot.constants import Messages, DebugMessages


class VoiceMessageHandler(BaseMessageHandler):
    """Handles voice message incidents - transcribes and delegates to text processing"""
    
    def __init__(self):
        super().__init__()
        self.voice_handler = VoiceHandler()
        self.incident_processor = IncidentProcessor()
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles voice message incidents following DRY principle"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Check if message should be ignored
        if self.should_ignore_message(update):
            return
        
        await self.show_typing(context, chat_id)
        
        # Send processing notification
        processing_msg = await update.message.reply_text(Messages.VOICE_PROCESSING)
        
        try:
            # Get voice file
            voice_file = await update.message.voice.get_file()
            voice_data = await voice_file.download_as_bytearray()
            file_name = f"voice_{user_id}_{update.message.message_id}.ogg"
            
            # Transcribe voice (ONLY transcription - no duplicate logic)
            success, text = await self.voice_handler.process_voice_message(bytes(voice_data), file_name)
            
            if not success:
                await processing_msg.edit_text(text)
                return
            
            # Show transcribed text
            await processing_msg.edit_text(Messages.VOICE_RECOGNIZED.format(text=text))
            
            # Now process as text message (DRY principle)
            await self.show_typing(context, chat_id)
            
            # Get author info
            author_info = self.get_author_info(update)
            
            # Save voice message to memory
            self.memory_service.add_message(user_id, "user", f"[Голосовое]: {text}")
            
            # Get context and history
            user_context = getattr(self, 'user_contexts', {}).get(str(user_id))
            conversation_history = self.memory_service.get_context(user_id)
            user_summary = self.memory_service.get_user_summary(user_id)
            
            # Process through incident processor (same as text)
            response_text, incident_data, response_type = await self.incident_processor.process_text_message(
                text, user_id, author_info, user_context, conversation_history, user_summary
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
                        'original_message': text,
                        'partial_analysis': {},
                        'author_info': author_info
                    }
                else:
                    self.user_contexts[str(user_id)]['original_message'] += f". {text}"
                    
            else:  # not_incident
                await self.incident_processor.handle_non_incident_response(
                    update, context, response_text, user_id
                )
                
                # Clear context
                if hasattr(self, 'user_contexts') and str(user_id) in self.user_contexts:
                    del self.user_contexts[str(user_id)]
                    
        except Exception as e:
            print(f"Voice processing error: {e}")
            await processing_msg.edit_text(Messages.VOICE_ERROR)
