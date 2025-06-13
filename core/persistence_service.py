import os
import json
import shutil
import sqlite3
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Tuple
import threading

from core.config_service import ConfigService


logger = logging.getLogger(__name__)

class StorageInterface(ABC):
    """存储接口抽象类"""

    @abstractmethod
    async def save(self, collection: str, key: str, data: Dict[str, Any]) -> bool:
        """保存数据"""
        pass

    @abstractmethod
    async def load(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """加载数据"""
        pass

    @abstractmethod
    async def delete(self, collection: str, key: str) -> bool:
        """删除数据"""
        pass

    @abstractmethod
    async def list(self, collection: str, filter_query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出集合中的数据"""
        pass

    @abstractmethod
    async def close(self):
        """关闭存储"""
        pass

class FileStorage(StorageInterface):
    """文件系统存储实现"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self._locks = {}  # 集合级别的锁

    def _get_collection_dir(self, collection: str) -> str:
        """获取集合目录"""
        collection_dir = os.path.join(self.base_dir, collection)
        os.makedirs(collection_dir, exist_ok=True)
        return collection_dir

    def _get_file_path(self, collection: str, key: str) -> str:
        """获取文件路径"""
        # 确保键是有效的文件名
        safe_key = key.replace('/', '_').replace('\\', '_')
        return os.path.join(self._get_collection_dir(collection), f"{safe_key}.json")

    def _get_lock(self, collection: str) -> threading.Lock:
        """获取集合锁"""
        if collection not in self._locks:
            self._locks[collection] = threading.Lock()
        return self._locks[collection]

    async def save(self, collection: str, key: str, data: Dict[str, Any]) -> bool:
        """保存数据到文件"""
        try:
            file_path = self._get_file_path(collection, key)

            # 如果数据中没有时间戳，添加一个
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now().isoformat()

            # 使用临时文件和原子重命名确保写入安全
            temp_file = f"{file_path}.tmp"

            with self._get_lock(collection):
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # 原子重命名
                os.replace(temp_file, file_path)

            return True
        except Exception as e:
            logger.error(f"保存文件失败 ({collection}/{key}): {e}")
            return False

    async def load(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """从文件加载数据"""
        try:
            file_path = self._get_file_path(collection, key)

            if not os.path.exists(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"加载文件失败 ({collection}/{key}): {e}")
            return None

    async def delete(self, collection: str, key: str) -> bool:
        """删除文件"""
        try:
            file_path = self._get_file_path(collection, key)

            if os.path.exists(file_path):
                with self._get_lock(collection):
                    os.remove(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"删除文件失败 ({collection}/{key}): {e}")
            return False

    async def list(self, collection: str, filter_query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出集合中的所有数据"""
        results = []
        collection_dir = self._get_collection_dir(collection)

        try:
            files = [f for f in os.listdir(collection_dir) if f.endswith('.json')]

            for file_name in files:
                try:
                    key = file_name[:-5]  # 移除 .json 后缀
                    file_path = os.path.join(collection_dir, file_name)

                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # 如果有过滤条件，检查是否符合
                    if filter_query:
                        match = True
                        for k, v in filter_query.items():
                            if k not in data or data[k] != v:
                                match = False
                                break

                        if not match:
                            continue

                    # 添加键值
                    data['_id'] = key
                    results.append(data)
                except Exception as e:
                    logger.warning(f"读取文件失败 ({file_name}): {e}")

            return results
        except Exception as e:
            logger.error(f"列出集合失败 ({collection}): {e}")
            return []

    async def close(self):
        """关闭存储"""
        # 文件存储不需要特殊关闭操作
        pass

class SQLiteStorage(StorageInterface):
    """SQLite存储实现"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None
        self._lock = threading.Lock()

        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir: # Ensure db_dir is not empty, meaning db_path is not just a filename
            os.makedirs(db_dir, exist_ok=True)


        # 初始化数据库
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # 允许跨线程访问
                timeout=30.0  # 设置超时
            )
            # 启用外键约束
            self._conn.execute("PRAGMA foreign_keys = ON")
            # 优化写入性能
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        return self._conn

    def _init_db(self):
        """初始化数据库表"""
        with self._lock:
            conn = self._get_connection()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS data_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (collection_id) REFERENCES collections (id) ON DELETE CASCADE,
                    UNIQUE (collection_id, key)
                )
            ''')

            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_collection_key
                ON data_items (collection_id, key)
            ''')

            conn.commit()

    def _get_collection_id(self, collection: str, create_if_missing: bool = True) -> Optional[int]:
        """获取集合ID"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT id FROM collections WHERE name = ?",
                (collection,)
            )
            result = cursor.fetchone()

            if result:
                return result[0]
            elif create_if_missing:
                cursor = conn.execute(
                    "INSERT INTO collections (name) VALUES (?)",
                    (collection,)
                )
                conn.commit()
                return cursor.lastrowid
            else:
                return None

    async def save(self, collection: str, key: str, data: Dict[str, Any]) -> bool:
        """保存数据到SQLite"""
        try:
            collection_id = self._get_collection_id(collection)
            if collection_id is None: # Should not happen if create_if_missing is True
                return False

            # 如果数据中没有时间戳，添加一个
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now().isoformat()

            json_data = json.dumps(data, ensure_ascii=False)

            with self._lock:
                conn = self._get_connection()

                # 使用UPSERT语法
                conn.execute('''
                    INSERT INTO data_items (collection_id, key, data, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (collection_id, key)
                    DO UPDATE SET data = excluded.data, updated_at = CURRENT_TIMESTAMP
                ''', (collection_id, key, json_data))

                conn.commit()

            return True
        except Exception as e:
            logger.error(f"保存数据失败 ({collection}/{key}): {e}")
            return False

    async def load(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """从SQLite加载数据"""
        try:
            collection_id = self._get_collection_id(collection, False)
            if collection_id is None:
                return None

            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute('''
                    SELECT data FROM data_items
                    WHERE collection_id = ? AND key = ?
                ''', (collection_id, key))

                result = cursor.fetchone()

                if result:
                    return json.loads(result[0])
                return None
        except Exception as e:
            logger.error(f"加载数据失败 ({collection}/{key}): {e}")
            return None

    async def delete(self, collection: str, key: str) -> bool:
        """从SQLite删除数据"""
        try:
            collection_id = self._get_collection_id(collection, False)
            if collection_id is None:
                return False

            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute('''
                    DELETE FROM data_items
                    WHERE collection_id = ? AND key = ?
                ''', (collection_id, key))

                conn.commit()

                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除数据失败 ({collection}/{key}): {e}")
            return False

    async def list(self, collection: str, filter_query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出SQLite集合中的数据"""
        results = []

        try:
            collection_id = self._get_collection_id(collection, False)
            if collection_id is None:
                return []

            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute('''
                    SELECT key, data FROM data_items
                    WHERE collection_id = ?
                    ORDER BY updated_at DESC
                ''', (collection_id,))

                for row in cursor:
                    key_val, data_json = row
                    try:
                        data = json.loads(data_json)

                        # 如果有过滤条件，检查是否符合
                        if filter_query:
                            match = True
                            for k, v_filter in filter_query.items():
                                if k not in data or data[k] != v_filter:
                                    match = False
                                    break

                            if not match:
                                continue

                        # 添加键值
                        data['_id'] = key_val
                        results.append(data)
                    except Exception as e:
                        logger.warning(f"解析数据失败 ({key_val}): {e}")

            return results
        except Exception as e:
            logger.error(f"列出集合失败 ({collection}): {e}")
            return []

    async def close(self):
        """关闭SQLite连接"""
        if self._conn:
            try:
                self._conn.close()
                self._conn = None
            except Exception as e:
                logger.error(f"关闭SQLite连接失败: {e}")

class PersistenceService:
    """持久化服务单例"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PersistenceService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 从配置服务获取存储设置
        config_service_instance = ConfigService()
        config = config_service_instance.get_config().persistence


        self.storage_type = config.storage_type
        self.storage_path = config.storage_path
        self.storage = self._create_storage()
        self._initialized = True

        logger.info(f"持久化服务初始化完成, 类型: {self.storage_type}, 路径: {self.storage_path}")

    def _create_storage(self) -> StorageInterface:
        """创建存储实例"""
        if self.storage_type == "file":
            return FileStorage(self.storage_path)
        elif self.storage_type == "sqlite":
            db_file_path = os.path.join(self.storage_path, "persistence.db")
            return SQLiteStorage(db_file_path)
        else:
            logger.warning(f"不支持的存储类型 {self.storage_type}，使用文件存储")
            return FileStorage(self.storage_path)

    async def save_trajectory(self, trajectory: Dict[str, Any]) -> bool:
        """保存轨迹数据"""
        trajectory_id = trajectory.get("task_id", str(time.time()))
        return await self.storage.save("trajectories", trajectory_id, trajectory)

    async def load_trajectory(self, trajectory_id: str) -> Optional[Dict[str, Any]]:
        """加载轨迹数据"""
        return await self.storage.load("trajectories", trajectory_id)

    async def list_trajectories(self, filter_query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出轨迹数据"""
        return await self.storage.list("trajectories", filter_query)

    async def save_tool_config(self, tool_id: str, config_data: Dict[str, Any]) -> bool:
        """保存工具配置"""
        return await self.storage.save("tool_configs", tool_id, config_data)

    async def load_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """加载工具配置"""
        return await self.storage.load("tool_configs", tool_id)

    async def list_tool_configs(self) -> List[Dict[str, Any]]:
        """列出所有工具配置"""
        return await self.storage.list("tool_configs")

    async def save_setting(self, key: str, value: Dict[str, Any]) -> bool:
        """保存系统设置"""
        return await self.storage.save("settings", key, value)

    async def load_setting(self, key: str) -> Optional[Dict[str, Any]]:
        """加载系统设置"""
        return await self.storage.load("settings", key)

    async def save_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """保存会话数据"""
        return await self.storage.save("sessions", session_id, data)

    async def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话数据"""
        return await self.storage.load("sessions", session_id)

    async def close(self):
        """关闭存储连接"""
        await self.storage.close()
