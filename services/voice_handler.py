import os
import re
import openai
from config.settings import settings
from typing import Optional, Tuple
from bot.constants import Messages


class VoiceHandler:
    """Voice message handler following DRY principles - only transcribes and delegates"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self._text_replacements = self._init_text_replacements()
    
    def _init_text_replacements(self) -> dict:
        """Initialize text replacement mappings"""
        return {
            # Branch name corrections
            "новза": "Novza",
            "сергели": "Sergeli", 
            "чилонзор": "Chilonzor",
            "бодомзор": "Bodomzor",
            "буюк ипак йули": "Buyul Ipak Yoli",
            "максимка": "Buyul Ipak Yoli",
            "максим горький": "Buyul Ipak Yoli",
            
            # Uzbek words
            "тугади": "закончилось",
            "бузилди": "сломалось", 
            "ишламаяпти": "не работает",
            "йук": "нет",
            "керак": "нужно",
        }
    
    async def process_voice_message(self, file_data: bytes, file_name: str) -> Tuple[bool, str]:
        """
        Processes voice message - ONLY transcribes and returns text
        Following DRY principle - no duplicate incident processing logic
        
        Args:
            file_data: Audio file bytes
            file_name: File name
            
        Returns:
            Tuple[success, transcribed_text_or_error_message]
        """
        try:
            # Create temporary file
            temp_path = f"temp_{file_name}"
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # Whisper API accepts OGG directly
            with open(temp_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    # Let Whisper auto-detect language
                )
            
            # Clean up temporary file
            os.remove(temp_path)
            
            # Post-process text
            text = self._postprocess_text(transcript.text)
            
            return True, text
            
        except Exception as e:
            print(f"Voice processing error: {e}")
            return False, Messages.VOICE_ERROR
    
    def _postprocess_text(self, text: str) -> str:
        """Post-processes transcribed text with replacements"""
        text_lower = text.lower()
        
        for old, new in self._text_replacements.items():
            if old in text_lower:
                # Replace with case preservation
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                text = pattern.sub(new, text)
        
        return text