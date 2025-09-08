import redis
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from config.settings import settings

class RedisMemory:
    """Сервис для управления памятью диалогов через Redis"""
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
        self.ttl_seconds = settings.MEMORY_TTL_DAYS * 24 * 60 * 60
        
        # Проверяем подключение
        try:
            self.redis_client.ping()
            print("✅ Redis подключен успешно")
        except Exception as e:
            print(f"❌ Ошибка подключения к Redis: {e}")
            raise
    
    def _get_user_key(self, user_id: int) -> str:
        """Генерирует ключ для пользователя"""
        return f"roma_bot:user:{user_id}"
    
    def _get_messages_key(self, user_id: int) -> str:
        """Генерирует ключ для сообщений пользователя"""
        return f"roma_bot:messages:{user_id}"
    
    def _get_stats_key(self, user_id: int) -> str:
        """Генерирует ключ для статистики пользователя"""
        return f"roma_bot:stats:{user_id}"
    
    def add_message(self, user_id: int, role: str, content: str, metadata: Optional[Dict] = None):
        """
        Добавляет сообщение в историю
        
        Args:
            user_id: ID пользователя
            role: 'user' или 'assistant' 
            content: Текст сообщения
            metadata: Дополнительные данные
        """
        messages_key = self._get_messages_key(user_id)
        stats_key = self._get_stats_key(user_id)
        
        # Создаем сообщение
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if metadata:
            message["metadata"] = metadata
            
            # Обновляем статистику
            if metadata.get("type") == "incident":
                self.redis_client.hincrby(stats_key, "incidents_count", 1)
                
                # Инкрементируем счетчики филиалов и отделов
                if metadata.get("branch"):
                    self.redis_client.hincrby(stats_key, f"branch:{metadata['branch']}", 1)
                if metadata.get("department"):
                    self.redis_client.hincrby(stats_key, f"dept:{metadata['department']}", 1)
        
        # Добавляем сообщение в список
        self.redis_client.lpush(messages_key, json.dumps(message, ensure_ascii=False))
        
        # Обрезаем список до максимального размера
        self.redis_client.ltrim(messages_key, 0, settings.MAX_MESSAGES_PER_USER - 1)
        
        # Обновляем TTL
        self.redis_client.expire(messages_key, self.ttl_seconds)
        self.redis_client.expire(stats_key, self.ttl_seconds)
        
        # Обновляем последнюю активность
        user_key = self._get_user_key(user_id)
        self.redis_client.hset(user_key, "last_activity", datetime.now().isoformat())
        self.redis_client.expire(user_key, self.ttl_seconds)
    
    def get_context(self, user_id: int, last_n: int = None) -> List[Dict]:
        """
        Получает контекст последних сообщений
        
        Args:
            user_id: ID пользователя
            last_n: Количество последних сообщений (по умолчанию из настроек)
            
        Returns:
            Список сообщений в хронологическом порядке
        """
        if last_n is None:
            last_n = settings.CONTEXT_MESSAGES
            
        messages_key = self._get_messages_key(user_id)
        
        # Получаем последние N сообщений (они хранятся в обратном порядке)
        raw_messages = self.redis_client.lrange(messages_key, 0, last_n - 1)
        
        # Парсим и разворачиваем в правильном порядке
        messages = []
        for raw_msg in reversed(raw_messages):
            try:
                messages.append(json.loads(raw_msg))
            except:
                continue
                
        return messages
    
    def get_user_summary(self, user_id: int) -> Dict:
        """Получает сводку о пользователе"""
        user_key = self._get_user_key(user_id)
        stats_key = self._get_stats_key(user_id)
        
        # Получаем основную информацию
        user_info = self.redis_client.hgetall(user_key)
        stats = self.redis_client.hgetall(stats_key)
        
        if not stats:
            return {
                "incidents_count": 0,
                "last_activity": None,
                "frequent_branches": [],
                "frequent_departments": []
            }
        
        # Парсим статистику
        incidents_count = int(stats.get("incidents_count", 0))
        
        # Собираем статистику по филиалам
        branches = {}
        departments = {}
        
        for key, value in stats.items():
            if key.startswith("branch:"):
                branch_name = key.replace("branch:", "")
                branches[branch_name] = int(value)
            elif key.startswith("dept:"):
                dept_name = key.replace("dept:", "")
                departments[dept_name] = int(value)
        
        # Сортируем по частоте
        frequent_branches = sorted(branches.items(), key=lambda x: x[1], reverse=True)[:3]
        frequent_departments = sorted(departments.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            "incidents_count": incidents_count,
            "last_activity": user_info.get("last_activity"),
            "frequent_branches": frequent_branches,
            "frequent_departments": frequent_departments,
            "user_info": user_info
        }
    
    def update_user_info(self, user_id: int, info: Dict):
        """Обновляет информацию о пользователе"""
        user_key = self._get_user_key(user_id)
        
        for key, value in info.items():
            self.redis_client.hset(user_key, key, value)
        
        self.redis_client.expire(user_key, self.ttl_seconds)
    
    def get_active_users_count(self, hours: int = 24) -> int:
        """Получает количество активных пользователей за период"""
        # Используем SCAN для подсчета активных пользователей
        count = 0
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for key in self.redis_client.scan_iter(match="roma_bot:user:*"):
            last_activity = self.redis_client.hget(key, "last_activity")
            if last_activity:
                activity_time = datetime.fromisoformat(last_activity)
                if activity_time > cutoff_time:
                    count += 1
        
        return count
    
    def get_global_stats(self) -> Dict:
        """Получает глобальную статистику"""
        total_incidents = 0
        branch_stats = {}
        dept_stats = {}
        
        # Сканируем все статистики пользователей
        for key in self.redis_client.scan_iter(match="roma_bot:stats:*"):
            stats = self.redis_client.hgetall(key)
            
            # Суммируем инциденты
            total_incidents += int(stats.get("incidents_count", 0))
            
            # Суммируем по филиалам и отделам
            for stat_key, value in stats.items():
                if stat_key.startswith("branch:"):
                    branch = stat_key.replace("branch:", "")
                    branch_stats[branch] = branch_stats.get(branch, 0) + int(value)
                elif stat_key.startswith("dept:"):
                    dept = stat_key.replace("dept:", "")
                    dept_stats[dept] = dept_stats.get(dept, 0) + int(value)
        
        return {
            "total_incidents": total_incidents,
            "active_users_24h": self.get_active_users_count(24),
            "branch_stats": dict(sorted(branch_stats.items(), key=lambda x: x[1], reverse=True)),
            "department_stats": dict(sorted(dept_stats.items(), key=lambda x: x[1], reverse=True))
        }