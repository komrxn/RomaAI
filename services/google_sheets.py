import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Optional
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
            
            # Определяем диапазон (A:I - все колонки кроме отчета менеджера)
            range_name = f"{self.sheet_name}!A:I"
            
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
            range_name = f"{self.sheet_name}!A:I"
            
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