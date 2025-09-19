"""
Main handlers module for Roma Pizza Bot
Refactored following senior-level standards and DRY principles
"""
from typing import Dict, Optional, Any
from telegram import Update
from telegram.ext import ContextTypes

from bot.text_handler import TextMessageHandler
from bot.voice_handler import VoiceMessageHandler
from bot.photo_handler import PhotoMessageHandler
from bot.command_handler import CommandHandler
from bot.constants import Messages


class HandlersManager:
    """Centralized handlers manager following DRY principles"""
    
    def __init__(self):
        self.text_handler = TextMessageHandler()
        self.voice_handler = VoiceMessageHandler()
        self.photo_handler = PhotoMessageHandler()
        self.command_handler = CommandHandler()
        
        # Shared user contexts across all handlers
        self.user_contexts: Dict[str, Dict] = {}
        
        # Set user_contexts for all handlers
        self._set_shared_contexts()
    
    def _set_shared_contexts(self):
        """Sets shared user_contexts for all handlers"""
        self.text_handler.user_contexts = self.user_contexts
        self.voice_handler.user_contexts = self.user_contexts
        self.photo_handler.user_contexts = self.user_contexts
        self.command_handler.user_contexts = self.user_contexts
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles text messages"""
        await self.text_handler.handle(update, context)
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles voice messages"""
        await self.voice_handler.handle(update, context)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles photo messages"""
        await self.photo_handler.handle(update, context)
    
    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles commands"""
        await self.command_handler.handle(update, context)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Centralized error handler"""
        print(f"Error: {context.error}")
        if update and update.effective_message:
            try:
                # Try to get a helpful response from AI
                response = self.text_handler.ai_agent.process_message("произошла ошибка", None)
                await update.effective_message.reply_text(
                    response.get('response', Messages.GENERAL_ERROR)
                )
            except Exception:
                await update.effective_message.reply_text(Messages.GENERAL_ERROR)


# Create global handlers manager instance
handlers_manager = HandlersManager()

# Export handler functions for main.py
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler"""
    await handlers_manager.command_handler.handle_start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Text message handler"""
    await handlers_manager.handle_message(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice message handler"""
    await handlers_manager.handle_voice(update, context)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Photo message handler"""
    await handlers_manager.handle_photo(update, context)

async def rep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rep command handler"""
    await handlers_manager.command_handler.handle_rep(update, context)

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mystats command handler"""
    await handlers_manager.command_handler.handle_mystats(update, context)

async def globalstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Globalstats command handler"""
    await handlers_manager.command_handler.handle_globalstats(update, context)

async def resolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resolve command handler"""
    await handlers_manager.command_handler.handle_resolve(update, context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Status command handler"""
    await handlers_manager.command_handler.handle_status(update, context)

async def myincidents_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Myincidents command handler"""
    await handlers_manager.command_handler.handle_myincidents(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Error handler"""
    await handlers_manager.error_handler(update, context)
