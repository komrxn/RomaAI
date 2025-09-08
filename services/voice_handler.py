import os
import io
import openai
from config.settings import settings
from typing import Optional, Tuple

class VoiceHandler:
    """Обработчик голосовых сообщений без FFmpeg"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def process_voice_message(self, file_data: bytes, file_name: str) -> Tuple[bool, str]:
        """
        Обрабатывает голосовое сообщение напрямую из байтов
        
        Args:
            file_data: Байты аудиофайла
            file_name: Имя файла
            
        Returns:
            Tuple[успех, текст или сообщение об ошибке]
        """
        try:
            # Создаем временный файл
            temp_path = f"temp_{file_name}"
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # Whisper API принимает OGG напрямую!
            with open(temp_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    # Можно не указывать язык - Whisper сам определит
                    # language="uz"  # или "ru" для русского
                )
            
            # Удаляем временный файл
            os.remove(temp_path)
            
            # Постобработка текста
            text = self._postprocess_text(transcript.text)
            
            return True, text
            
        except Exception as e:
            print(f"Ошибка обработки голоса: {e}")
            return False, "Не удалось распознать голосовое сообщение."
    
    def _postprocess_text(self, text: str) -> str:
        """Постобработка текста"""
        replacements = {
            # Исправления для филиалов
            "новза": "Novza",
            "сергели": "Sergeli",
            "чилонзор": "Chilonzor",
            "бодомзор": "Bodomzor",
            "буюк ипак йули": "Buyul Ipak Yoli",
            "максимка": "Buyul Ipak Yoli",
            "максим горький": "Buyul Ipak Yoli",
            
            # Узбекские слова
            "тугади": "закончилось",
            "бузилди": "сломалось",
            "ишламаяпти": "не работает",
            "йук": "нет",
            "керак": "нужно",
        }
        
        text_lower = text.lower()
        for old, new in replacements.items():
            if old in text_lower:
                # Заменяем с учетом регистра
                import re
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                text = pattern.sub(new, text)
        
        return text