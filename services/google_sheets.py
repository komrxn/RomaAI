import os
import io
import base64
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Optional, Tuple
from config.settings import settings
from models.incident import Incident

class GoogleSheetsService:
    """Сервис для работы с Google Sheets"""
    
    def __init__(self):
        self.spreadsheet_id = settings.GOOGLE_SHEETS_ID
        self.sheet_name = settings.SHEET_NAME
        self.service = self._authenticate()
        
    def _authenticate(self):
        """Аутентификация в Google Sheets API"""
        try:
            # Загружаем credentials из файла
            if os.path.exists(settings.GOOGLE_CREDENTIALS_FILE):
                credentials = service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_CREDENTIALS_FILE,
                    scopes=['https://www.googleapis.com/auth/spreadsheets']
                )
            else:
                # Альтернативный способ через переменные окружения
                # Вам нужно будет добавить логику для загрузки credentials из env
                raise FileNotFoundError(f"Файл {settings.GOOGLE_CREDENTIALS_FILE} не найден")
                
            service = build('sheets', 'v4', credentials=credentials)
            return service
            
        except Exception as e:
            print(f"Ошибка аутентификации Google Sheets: {e}")
            raise
            
    def append_incident(self, incident: Incident) -> bool:
        """
        Добавляет инцидент в таблицу
        
        Args:
            incident: Объект инцидента
            
        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            # Подготавливаем данные для вставки
            values = [incident.to_sheet_row()]
            
            # Определяем диапазон (A:L - все колонки включая фото решения)
            range_name = f"{self.sheet_name}!A:L"
            
            # Вставляем данные
            body = {
                'values': values
            }
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',  # Позволяет Google Sheets интерпретировать данные
                insertDataOption='INSERT_ROWS',   # Вставляет новую строку
                body=body
            ).execute()
            
            print(f"Инцидент добавлен: {result.get('updates', {}).get('updatedCells')} ячеек обновлено")
            return True
            
        except HttpError as error:
            print(f"Ошибка при добавлении в Google Sheets: {error}")
            return False
        except Exception as e:
            print(f"Неожиданная ошибка: {e}")
            return False
            
    def get_all_incidents(self) -> Optional[List[List[str]]]:
        """
        Получает все инциденты из таблицы
        
        Returns:
            Список инцидентов или None в случае ошибки
        """
        try:
            range_name = f"{self.sheet_name}!A:L"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                print('Данные не найдены.')
                return []
            
            return values[1:]  # Пропускаем заголовок
            
        except HttpError as error:
            print(f"Ошибка при чтении из Google Sheets: {error}")
            return None
    
    def update_incident_photo(self, incident_id: str, photo_url: str) -> bool:
        """
        Обновляет фото URL для инцидента
        
        Args:
            incident_id: ID инцидента
            photo_url: URL фото в Google Drive
            
        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            # Получаем все инциденты
            incidents = self.get_all_incidents()
            
            if not incidents:
                print("Не удалось получить список инцидентов")
                return False
            
            # Находим нужный по ID
            for i, incident_row in enumerate(incidents):
                if len(incident_row) > 0 and incident_row[0] == incident_id:
                    row_number = i + 2  # +2 так как индексация с 1 и есть заголовок
                    
                    # Обновляем фото URL (колонка K)
                    range_photo = f"{self.sheet_name}!K{row_number}"
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=range_photo,
                        valueInputOption='USER_ENTERED',
                        body={'values': [[photo_url]]}
                    ).execute()
                    
                    print(f"Фото обновлено для инцидента {incident_id}")
                    return True
            
            print(f"Инцидент {incident_id} не найден в таблице")
            return False
            
        except Exception as e:
            print(f"Ошибка обновления фото: {e}")
            return False
    
    def insert_image(self, file_data: bytes, incident_id: str, problem_description: str = "", file_extension: str = 'jpg') -> Tuple[bool, str]:
        """
        Сохраняет изображение локально и добавляет ссылку в Google Sheets
        
        Args:
            file_data: Данные изображения в байтах
            incident_id: ID инцидента
            problem_description: Описание проблемы для имени файла
            file_extension: Расширение файла
            
        Returns:
            Tuple[успех, сообщение]
        """
        try:
            print(f"📸 Сохраняю изображение для инцидента {incident_id}...")
            
            # Создаем структуру папок: photos/incidents/YYYY/MM/DD/
            now = datetime.now()
            year = now.strftime('%Y')
            month = now.strftime('%m')
            day = now.strftime('%d')
            
            photos_dir = os.path.join('photos', 'incidents', year, month, day)
            os.makedirs(photos_dir, exist_ok=True)
            print(f"📁 Создана папка: {photos_dir}")
            
            # Создаем имя файла
            if problem_description:
                clean_description = "".join(c for c in problem_description if c.isalnum() or c in ('-', '_', ' ')).strip()
                clean_description = clean_description.replace(' ', '_')
                if len(clean_description) > 30:
                    clean_description = clean_description[:30]
            else:
                clean_description = incident_id.replace('#', '').replace('-', '_')
            
            # Добавляем timestamp для уникальности
            timestamp = now.strftime('%H%M%S')
            filename = f"{incident_id}_{clean_description}_{timestamp}.{file_extension}"
            
            # Полный путь к файлу
            file_path = os.path.join(photos_dir, filename)
            
            # Сохраняем файл
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            print(f"💾 Фото сохранено: {file_path}")
            
            # Находим строку с нашим инцидентом
            incidents = self.get_all_incidents()
            if not incidents:
                print("❌ Не удалось получить список инцидентов")
                return False, "Не удалось получить список инцидентов"
            
            target_row = None
            for i, incident_row in enumerate(incidents):
                if len(incident_row) > 0 and incident_row[0] == incident_id:
                    target_row = i + 2  # +2 так как индексация с 1 и есть заголовок
                    break
            
            if not target_row:
                print(f"❌ Инцидент {incident_id} не найден в таблице")
                return False, f"Инцидент {incident_id} не найден в таблице"
            
            # Определяем колонку для изображения (K)
            image_column = 'K'
            cell_range = f"{self.sheet_name}!{image_column}{target_row}"
            
            # Вставляем ссылку на файл
            image_text = f"📸 Фото: {file_path}"
            
            # Обновляем ячейку с ссылкой на фото
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=cell_range,
                valueInputOption='USER_ENTERED',
                body={'values': [[image_text]]}
            ).execute()
            
            print(f"✅ Ссылка на фото добавлена в ячейку {cell_range}")
            return True, f"Фото сохранено: {file_path}"
            
        except Exception as e:
            error_msg = f"Ошибка сохранения изображения: {e}"
            print(f"❌ {error_msg}")
            return False, error_msg
    
    def update_incident_with_image(self, incident: dict) -> bool:
        """
        Обновляет инцидент с изображением в Google Sheets
        
        Args:
            incident: Словарь с данными инцидента
            
        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            print(f"🔄 Обновляю инцидент {incident['id']} с изображением...")
            
            # Находим строку с инцидентом
            incidents = self.get_all_incidents()
            if not incidents:
                print("❌ Не удалось получить список инцидентов")
                return False
            
            target_row = None
            for i, incident_row in enumerate(incidents):
                if len(incident_row) > 0 and incident_row[0] == incident['id']:
                    target_row = i + 2  # +2 так как индексация с 1 и есть заголовок
                    break
            
            if not target_row:
                print(f"❌ Инцидент {incident['id']} не найден в таблице")
                return False
            
            # Обновляем только статус (не перезаписываем пути к фото)
            incident_obj = Incident(**incident)
            
            # Обновляем только колонку J (статус)
            status_range = f"{self.sheet_name}!J{target_row}"
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=status_range,
                valueInputOption='USER_ENTERED',
                body={'values': [[settings.INCIDENT_STATUSES[incident_obj.status]]]}
            ).execute()
            
            print(f"✅ Инцидент {incident['id']} обновлен в Google Sheets")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обновления инцидента: {e}")
            return False
    
    def insert_solution_image(self, file_data: bytes, incident_id: str, solution_description: str = "", file_extension: str = 'jpg') -> Tuple[bool, str]:
        """
        Сохраняет фото решения локально и добавляет ссылку в Google Sheets
        
        Args:
            file_data: Данные изображения в байтах
            incident_id: ID инцидента
            solution_description: Описание решения
            file_extension: Расширение файла
            
        Returns:
            Tuple[успех, сообщение]
        """
        try:
            print(f"📸 Сохраняю фото решения для инцидента {incident_id}...")
            
            # Создаем структуру папок: photos/solutions/YYYY/MM/DD/
            now = datetime.now()
            year = now.strftime('%Y')
            month = now.strftime('%m')
            day = now.strftime('%d')
            
            photos_dir = os.path.join('photos', 'solutions', year, month, day)
            os.makedirs(photos_dir, exist_ok=True)
            print(f"📁 Создана папка: {photos_dir}")
            
            # Создаем имя файла
            if solution_description:
                clean_description = "".join(c for c in solution_description if c.isalnum() or c in ('-', '_', ' ')).strip()
                clean_description = clean_description.replace(' ', '_')
                if len(clean_description) > 30:
                    clean_description = clean_description[:30]
            else:
                clean_description = "solution"
            
            # Добавляем timestamp для уникальности
            timestamp = now.strftime('%H%M%S')
            filename = f"{incident_id}_SOLUTION_{clean_description}_{timestamp}.{file_extension}"
            
            # Полный путь к файлу
            file_path = os.path.join(photos_dir, filename)
            
            # Сохраняем файл
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            print(f"💾 Фото решения сохранено: {file_path}")
            
            # Находим строку с нашим инцидентом
            incidents = self.get_all_incidents()
            if not incidents:
                print("❌ Не удалось получить список инцидентов")
                return False, "Не удалось получить список инцидентов"
            
            target_row = None
            for i, incident_row in enumerate(incidents):
                if len(incident_row) > 0 and incident_row[0] == incident_id:
                    target_row = i + 2  # +2 так как индексация с 1 и есть заголовок
                    break
            
            if not target_row:
                print(f"❌ Инцидент {incident_id} не найден в таблице")
                return False, f"Инцидент {incident_id} не найден в таблице"
            
            # Определяем колонку для фото решения (L)
            solution_column = 'L'
            cell_range = f"{self.sheet_name}!{solution_column}{target_row}"
            
            # Вставляем ссылку на файл решения
            solution_text = f"✅ Решение: {file_path}"
            
            # Обновляем ячейку с ссылкой на фото решения
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=cell_range,
                valueInputOption='USER_ENTERED',
                body={'values': [[solution_text]]}
            ).execute()
            
            print(f"✅ Ссылка на фото решения добавлена в ячейку {cell_range}")
            return True, f"Фото решения сохранено: {file_path}"
            
        except Exception as e:
            error_msg = f"Ошибка сохранения фото решения: {e}"
            print(f"❌ {error_msg}")
            return False, error_msg