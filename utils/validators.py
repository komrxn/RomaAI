import os
from typing import Tuple, Optional
from config.settings import settings

def validate_photo(file_path: str, file_size: int) -> Tuple[bool, str]:
    """
    Валидирует фото файл
    
    Args:
        file_path: Путь к файлу или расширение (для работы с байтами)
        file_size: Размер файла в байтах
        
    Returns:
        Tuple[валидность, сообщение об ошибке]
    """
    try:
        # Проверяем размер файла
        max_size_bytes = settings.MAX_PHOTO_SIZE_MB * 1024 * 1024
        if file_size > max_size_bytes:
            return False, f"Файл слишком большой. Максимум {settings.MAX_PHOTO_SIZE_MB}MB"
        
        # Проверяем расширение файла
        if '.' in file_path:
            file_extension = os.path.splitext(file_path)[1].lower().lstrip('.')
        else:
            # Если передан только формат (например, "jpg")
            file_extension = file_path.lower()
            
        if file_extension not in settings.ALLOWED_PHOTO_FORMATS:
            allowed_formats = ', '.join(settings.ALLOWED_PHOTO_FORMATS)
            return False, f"Неподдерживаемый формат. Разрешены: {allowed_formats}"
        
        # Если это реальный файл - проверяем существование
        if os.path.sep in file_path and not os.path.exists(file_path):
            return False, "Файл не найден"
        
        return True, "Файл валиден"
        
    except Exception as e:
        return False, f"Ошибка валидации: {str(e)}"

def get_file_extension_from_mime(mime_type: str) -> str:
    """
    Получает расширение файла из MIME типа
    
    Args:
        mime_type: MIME тип файла
        
    Returns:
        str: Расширение файла
    """
    mime_to_ext = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg', 
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp'
    }
    
    return mime_to_ext.get(mime_type, 'jpg')

def format_file_size(size_bytes: int) -> str:
    """
    Форматирует размер файла в читаемый вид
    
    Args:
        size_bytes: Размер в байтах
        
    Returns:
        str: Отформатированный размер
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"