import json
import re
import openai
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime, timedelta
from config.settings import settings
from models.incident import Incident
from zoneinfo import ZoneInfo

class IncidentAIAgent:
    """AI агент для анализа и обработки инцидентов"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
    def process_message(self, message: str, user_context: Optional[Dict] = None, 
                       conversation_history: Optional[List[Dict]] = None,
                       user_summary: Optional[Dict] = None) -> Dict:
        """
        Обрабатывает сообщение с учетом полной истории и контекста пользователя
        """
        try:
            # Формируем контекст для AI
            context_info = ""
            
            # Добавляем информацию о пользователе
            if user_summary and user_summary.get("incidents_count", 0) > 0:
                context_info += f"\n\nИнформация о пользователе:"
                context_info += f"\n- Всего инцидентов: {user_summary['incidents_count']}"
                
                if user_summary.get("frequent_branches"):
                    branches = ", ".join([f"{b[0]} ({b[1]})" for b in user_summary["frequent_branches"]])
                    context_info += f"\n- Частые филиалы: {branches}"
            
            # Добавляем историю диалога
            if conversation_history:
                context_info += "\n\nПоследние сообщения:"
                for msg in conversation_history[-5:]:  # Последние 5 для краткости
                    role = "Пользователь" if msg["role"] == "user" else "Ассистент"
                    content_preview = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
                    context_info += f"\n{role}: {content_preview}"
            
            # Добавляем текущий контекст инцидента
            if user_context:
                context_info += f"\n\nТекущий контекст:"
                context_info += f"\nПредыдущее сообщение: {user_context.get('original_message', '')}"
                if user_context.get('partial_analysis'):
                    context_info += f"\nЧастичные данные: {json.dumps(user_context.get('partial_analysis', {}), ensure_ascii=False)}"
            
            system_prompt = f"""Ты - умный ассистент для управления инцидентами Roma Pizza.

ДОСТУПНЫЕ ФИЛИАЛЫ: {', '.join(settings.BRANCHES)}
ВАЖНО: "Максимка", "Максим Горький", "Максим горки" = "Buyul Ipak Yoli" (это один и тот же филиал!)

ДОСТУПНЫЕ ОТДЕЛЫ: {', '.join(settings.DEPARTMENTS)}

ВАЖНО! ЛОГИКА ОПРЕДЕЛЕНИЯ ОТДЕЛА (используй СТРОГО эти правила):
- IT: проблемы с кассами, POS-терминалами, компьютерами, интернетом, программным обеспечением, сетью
- Стандартизация и сервис: кондиционеры, вентиляция, освещение, холодильники, оборудование (кроме IT), электрика
- Закуп и снабжение: нехватка продуктов (тесто, соусы, ингредиенты), проблемы с поставками, закончились товары
- HR: проблемы с персоналом, конфликты, нехватка сотрудников, опоздания, прогулы
- Контроль качества: жалобы клиентов на еду или сервис, нарушения стандартов обслуживания
- Marketing: проблемы с рекламой, акциями, вывесками, промо-материалами
- Бухгалтерия: финансовые вопросы, проблемы с оплатой, кассовые расхождения
- Доставка и Колл-центр: проблемы с доставкой и кол центр
- Главный офис: глобальные проблемы не привязанные к какому то филлиалу

ПРИОРИТЕТЫ:
- Критический: пожар, отравление, авария, воровство, драки, угроза жизни
- Высокий: поломка критического оборудования (касса, холодильник с продуктами), отсутствие ключевых продуктов,какой либо из отделов не работает, испорченные,то без чего работа не может продолжаться в штатном порядке
- Средний: некритичные поломки, жалобы клиентов
- Низкий: предложения по улучшению, мелкие неполадки

ТВОЯ ЗАДАЧА:
1. Внимательно анализируй проблему и ПРАВИЛЬНО определяй отдел согласно логике выше
2. ВСЕГДА преобразуй "Максимка", "Максим Горький" в "Buyul Ipak Yoli"
3. Учитывай историю диалога и предпочтения пользователя
4. Если пользователь часто из одного филиала - можешь предположить его
5. Будь персонализированным и дружелюбным
6. Если информации недостаточно - вежливо попроси уточнить
7. Если это не инцидент - объясни что принимаешь только отчеты о проблемах

ВАЖНО ДЛЯ УЗБЕКСКОГО ЯЗЫКА:
- Пользователи могут писать на узбекском латиницей или кириллицей
- Частые узбекские слова:
  * "buzildi" / "бузилди" = сломалось
  * "tugadi" / "тугади" = закончилось  
  * "ishlamayapti" / "ишламаяпти" = не работает
  * "kerak" / "керак" = нужно
- Узбекские названия филиалов могут быть написаны по-разному
- Будь готов к смешанному русско-узбекскому тексту

ВСЕГДА отвечай в формате JSON:
{{
    "type": "incident" | "clarification" | "not_incident",
    "response": "персонализированный дружелюбный ответ",
    "incident_data": {{ // только для type="incident" или "clarification"
        "branch": "филиал из списка (помни про Максимка = Buyul Ipak Yoli)",
        "department": "отдел из списка согласно логике выше", 
        "short_description": "краткое описание проблемы (макс 50 символов)",
        "priority": "Критический|Высокий|Средний|Низкий",
        "explanation": "развернутое но короткое описание проблемы и её последствий"
    }},
    "missing_info": ["branch" или "details"] // только для type="clarification"
}}

КРИТИЧЕСКИ ВАЖНО: 
- Часто могут неправильно писать названия филлиалов, будь готов например к "но вза", это Новза
- !!!Очень внимательно относись к глобальным пробелмам, не пропусти их и отправлял инцидент сразу в главный офис!!!
- Анализируй суть проблемы и выбирай правильный отдел
- "Свет выключили" = "Стандартизация и сервис" 
- "Тесто кончилось" = "Закуп и снабжение" 
- "Полы грязные" = "Стандартизация и сервис"
- Общайся на языке в котором с тобой начал говорить пользователь, если он поменял, ты тоже меняй 
- "Максимка" или "Максим Горький" ВСЕГДА = филлиал "Buyul Ipak Yoli" """
            

            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Сообщение пользователя: {message}{context_info}"}
                ],
                temperature=0.3,  # Снижаем для более точного следования инструкциям
            )
            
            content = response.choices[0].message.content.strip()
            
            # Парсим JSON
            if content.startswith('{'):
                result = json.loads(content)
            else:
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError("JSON не найден в ответе")
            
            # Проверяем корректность отдела
            if result.get('incident_data', {}).get('department') not in settings.DEPARTMENTS and result.get('incident_data', {}).get('department') is not None:
                print(f"Предупреждение: AI выбрал несуществующий отдел: {result['incident_data']['department']}")
                # Пытаемся исправить на основе ключевых слов
                result['incident_data']['department'] = self._fix_department(message, result.get('incident_data', {}).get('short_description', ''))
            
            return result
            
        except Exception as e:
            print(f"Ошибка обработки: {e}")
            if 'content' in locals():
                print(f"Ответ AI: {content}")
            return {
                "type": "not_incident",
                "response": "Извините, произошла ошибка. Пожалуйста, опишите проблему еще раз."
            }
    
    def _fix_department(self, message: str, description: str) -> str:
        """Исправляет отдел на основе ключевых слов"""
        text = (message + " " + description).lower()
        
        # Ключевые слова для отделов
        department_keywords = {
            "IT": ["касса", "pos", "терминал", "компьютер", "интернет", "сеть", "программа"],
            "Стандартизация и сервис": ["свет", "электричество", "кондиционер", "холодильник", "вентиляция", "оборудование"],
            "Закуп и снабжение": ["кончилось", "закончилось", "нет", "нехватка", "тесто", "продукты", "ингредиенты"],
            "HR": ["сотрудник", "персонал", "опоздал", "не пришел", "конфликт"],
            "Контроль качества": ["жалоба", "клиент", "качество", "невкусно"],
            "Marketing": ["реклама", "вывеска", "акция", "промо"],
            "Бухгалтерия": ["деньги", "оплата", "касса не сходится", "расхождение"],
            "Доставка и Колл-центр": ["доставка, кол центр"],
            "Главный офис": ["Централизованно"]
        }
        
        for dept, keywords in department_keywords.items():
            if any(keyword in text for keyword in keywords):
                return dept
        
        # По умолчанию для неопределенных проблем
        return "Стандартизация и сервис"
    
    def create_incident_from_data(self, incident_data: Dict, original_message: str) -> Optional[Incident]:
        """Создает инцидент из данных AI"""
        try:
            # Дополнительная проверка отдела
            if incident_data.get('department') not in settings.DEPARTMENTS:
                print(f"Ошибка: неверный отдел {incident_data.get('department')}")
                incident_data['department'] = self._fix_department(original_message, incident_data.get('short_description', ''))
            
            full_description = f"{original_message}"
            if incident_data.get('explanation'):
                full_description += f"\n\n— {incident_data['explanation']}"
            
            incident = Incident(
                id=Incident.create_id(),
                date=Incident.get_current_date(),
                time=Incident.get_current_time(),
                branch=incident_data['branch'],
                department=incident_data['department'],
                short_description=incident_data['short_description'][:50],  # Обрезаем до 50 символов
                priority=incident_data['priority'],
                full_message=full_description,
                manager_report=""
            )
            return incident
            
        except Exception as e:
            print(f"Ошибка создания инцидента: {e}")
            return None
    
    def calculate_smart_deadline(self, incident_data: Dict, original_message: str) -> Dict:
        """Рассчитывает умный дедлайн с учетом контекста и рабочего времени"""
        try:
            current_time = datetime.now(ZoneInfo('Asia/Tashkent'))
            
            deadline_prompt = f"""Ты эксперт по управлению временем в ресторанном бизнесе Roma Pizza.

РАБОЧЕЕ ВРЕМЯ: 08:00 - 23:00 (Ташкент, UTC+5)
ТЕКУЩЕЕ ВРЕМЯ: {current_time.strftime('%Y-%m-%d %H:%M')}

ИНЦИДЕНТ:
- Приоритет: {incident_data.get('priority')}
- Проблема: {incident_data.get('short_description')}
- Полное описание: {original_message}
- Филиал: {incident_data.get('branch')}
- Отдел: {incident_data.get('department')}

ПРАВИЛА РАСЧЕТА ДЕДЛАЙНА:
1. Критические проблемы (пожар, отравление, драка) - максимум 1-2 часа даже ночью
2. Если сейчас нерабочее время (23:00-08:00):
   - Критические - решаются сразу
   - Остальные - переносятся на начало рабочего дня (08:00)
3. Учитывай реальное время решения:
   - Замена оборудования: минимум 4-8 часов (нужно найти и привезти)
   - Доставка продуктов: 2-4 часа в рабочее время
   - IT проблемы: 1-4 часа в зависимости от сложности
   - Проблемы с персоналом: 2-24 часа (найти замену)
4. Если до конца рабочего дня (23:00) меньше 2 часов и проблема не критическая - перенеси на утро
5. Учитывай контекст: "срочно нужно сегодня" - постарайся уложиться в текущий день

ВАЖНО: Будь реалистичен! Лучше дать больше времени чем поставить невыполнимый дедлайн.

Ответь ТОЛЬКО валидным JSON без дополнительного текста:
{{
    "deadline_hours": число часов от текущего момента (может быть дробным),
    "deadline_datetime": "YYYY-MM-DD HH:MM" (точное время дедлайна в формате 24ч),
    "reasoning": "краткое объяснение почему именно такой дедлайн на русском языке"
}}"""

            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты эксперт по расчету реалистичных дедлайнов. Отвечай ТОЛЬКО валидным JSON без дополнительного текста."},
                    {"role": "user", "content": deadline_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}  # Форсируем JSON ответ
            )
            
            content = response.choices[0].message.content.strip()
            
            # Парсим JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"Ошибка парсинга JSON от AI: {content}")
                print(f"Детали ошибки: {e}")
                # Пробуем извлечь JSON из текста
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError("Не удалось извлечь JSON из ответа")
            
            # Валидация и корректировка
            deadline_dt = datetime.strptime(result['deadline_datetime'], '%Y-%m-%d %H:%M')
            deadline_dt = deadline_dt.replace(tzinfo=ZoneInfo('Asia/Tashkent'))
            
            # Для некритических - проверяем рабочее время
            if incident_data.get('priority') != 'Критический':
                if deadline_dt.hour >= 23 or deadline_dt.hour < 8:
                    # Переносим на 8 утра
                    if deadline_dt.hour >= 23:
                        next_day = deadline_dt.replace(hour=8, minute=0) + timedelta(days=1)
                    else:
                        next_day = deadline_dt.replace(hour=8, minute=0)
                        
                    deadline_dt = next_day
                    result['reasoning'] += " (скорректировано на рабочее время)"
            
            return {
                'deadline': deadline_dt.isoformat(),
                'reasoning': result['reasoning'],
                'hours': result.get('deadline_hours', 24)
            }
            
        except Exception as e:
            print(f"Ошибка расчета умного дедлайна: {e}")
            # Fallback логика без DEADLINES
            current_time = datetime.now(ZoneInfo('Asia/Tashkent'))
            priority_hours = {
                'Критический': 1,
                'Высокий': 4,
                'Средний': 24,
                'Низкий': 72
            }
            hours = priority_hours.get(incident_data.get('priority', 'Средний'), 24)
            deadline = current_time + timedelta(hours=hours)
            
            # Корректируем на рабочее время для некритических
            if incident_data.get('priority') != 'Критический' and (deadline.hour >= 23 or deadline.hour < 8):
                if deadline.hour >= 23:
                    deadline = deadline.replace(hour=8, minute=0) + timedelta(days=1)
                else:
                    deadline = deadline.replace(hour=8, minute=0)
                    
            return {
                'deadline': deadline.isoformat(),
                'reasoning': f'Стандартный срок {hours}ч для приоритета {incident_data.get("priority")}',
                'hours': hours
            }
    
    def analyze_incidents_data(self, incidents: List[List[str]], query: str, 
                              global_stats: Optional[Dict] = None) -> str:
        """Анализирует инциденты с учетом глобальной статистики"""
        try:
            # Форматируем данные инцидентов
            incidents_data = []
            for inc in incidents:
                if len(inc) >= 8:
                    try:
                        date_obj = datetime.strptime(inc[1], '%Y-%m-%d')
                        incidents_data.append({
                            'id': inc[0],
                            'date': inc[1],
                            'date_obj': date_obj,
                            'time': inc[2],
                            'branch': inc[3],
                            'department': inc[4],
                            'short_description': inc[5],
                            'priority': inc[6],
                            'full_message': inc[7]
                        })
                    except:
                        continue
            
            # Сортируем по дате
            incidents_data.sort(key=lambda x: x['date_obj'], reverse=True)
            
            # Удаляем date_obj перед отправкой в AI
            for inc in incidents_data:
                inc.pop('date_obj', None)
            
            incidents_json = json.dumps(incidents_data, ensure_ascii=False, indent=2)
            
            # Добавляем глобальную статистику если есть
            stats_info = ""
            if global_stats:
                stats_info = f"\n\nГЛОБАЛЬНАЯ СТАТИСТИКА СИСТЕМЫ:"
                stats_info += f"\n- Всего инцидентов в системе: {global_stats.get('total_incidents', 0)}"
                stats_info += f"\n- Активных пользователей за 24ч: {global_stats.get('active_users_24h', 0)}"
                
                if global_stats.get('branch_stats'):
                    stats_info += "\n- Топ филиалов по инцидентам:"
                    for branch, count in list(global_stats['branch_stats'].items())[:3]:
                        stats_info += f"\n  • {branch}: {count}"
            
            prompt = f"""Проанализируй инциденты Roma Pizza и ответь на запрос.

ДАННЫЕ ИНЦИДЕНТОВ:
{incidents_json}
{stats_info}

ЗАПРОС: {query}

Дай развернутый ответ с:
- Конкретными цифрами и статистикой
- Выявленными трендами и паттернами
- Сравнением с глобальными показателями (если применимо)
- Практическими рекомендациями
- Используй эмодзи для наглядности

Сегодняшняя дата: {datetime.now().strftime('%Y-%m-%d')}"""

            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты аналитик инцидентов Roma Pizza. Отвечай подробно и структурированно."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Ошибка анализа: {e}")
            return "❌ Произошла ошибка при анализе данных."