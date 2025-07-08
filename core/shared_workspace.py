#!/usr/bin/env python3
"""
共享工作区管理器 - 解决工具间"信息孤岛"问题
提供安全的跨工具数据传递机制
"""

import os
import json
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import hashlib
import threading
from contextlib import contextmanager
import shutil

logger = logging.getLogger(__name__)

class SharedWorkspaceManager:
    """共享工作区管理器"""
    
    def __init__(self, workspace_root: str = "/tmp/agent_workspace"):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        self.data_dir = self.workspace_root / "data"
        self.temp_dir = self.workspace_root / "temp" 
        self.session_dir = self.workspace_root / "sessions"
        self.export_dir = self.workspace_root / "exports"
        
        for directory in [self.data_dir, self.temp_dir, self.session_dir, self.export_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            
        self._lock = threading.RLock()
        self._active_sessions = {}
        
        logger.info(f"✅ 共享工作区初始化完成: {self.workspace_root}")
    
    def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """创建会话工作区"""
        with self._lock:
            session_path = self.session_dir / session_id
            session_path.mkdir(parents=True, exist_ok=True)
            
            # 创建会话元数据
            session_metadata = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "metadata": metadata or {},
                "active": True,
                "files_created": [],
                "data_exported": []
            }
            
            metadata_file = session_path / "session_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(session_metadata, f, indent=2, ensure_ascii=False)
            
            self._active_sessions[session_id] = session_path
            logger.info(f"📁 创建会话工作区: {session_id} -> {session_path}")
            return session_path
    
    def get_session_path(self, session_id: str) -> Optional[Path]:
        """获取会话路径"""
        session_path = self.session_dir / session_id
        if session_path.exists():
            return session_path
        return None
    
    def save_data(self, session_id: str, data_key: str, data: Any, 
                  file_format: str = "json") -> Path:
        """保存数据到共享工作区"""
        session_path = self.get_session_path(session_id)
        if not session_path:
            session_path = self.create_session(session_id)
        
        # 生成安全的文件名
        safe_key = self._sanitize_filename(data_key)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if file_format == "json":
            filename = f"{safe_key}_{timestamp}.json"
            file_path = session_path / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        elif file_format == "text":
            filename = f"{safe_key}_{timestamp}.txt"
            file_path = session_path / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(data))
        
        elif file_format == "csv":
            filename = f"{safe_key}_{timestamp}.csv"
            file_path = session_path / filename
            if hasattr(data, 'to_csv'):  # pandas DataFrame
                data.to_csv(file_path, index=False)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(str(data))
        
        else:
            raise ValueError(f"不支持的文件格式: {file_format}")
        
        # 更新会话元数据
        self._update_session_metadata(session_id, "files_created", str(file_path))
        
        logger.info(f"💾 数据已保存: {data_key} -> {file_path}")
        return file_path
    
    def load_data(self, session_id: str, data_key: str = None, 
                  file_path: str = None) -> Any:
        """从共享工作区加载数据"""
        session_path = self.get_session_path(session_id)
        if not session_path:
            raise FileNotFoundError(f"会话不存在: {session_id}")
        
        if file_path:
            # 直接使用指定文件路径
            target_file = session_path / file_path
        elif data_key:
            # 查找最新的匹配文件
            safe_key = self._sanitize_filename(data_key)
            pattern = f"{safe_key}_*.json"
            matching_files = list(session_path.glob(pattern))
            if not matching_files:
                # 尝试其他格式
                for ext in ['txt', 'csv']:
                    pattern = f"{safe_key}_*.{ext}"
                    matching_files = list(session_path.glob(pattern))
                    if matching_files:
                        break
            
            if not matching_files:
                raise FileNotFoundError(f"未找到数据: {data_key}")
            
            # 选择最新文件
            target_file = max(matching_files, key=lambda p: p.stat().st_mtime)
        else:
            raise ValueError("必须指定 data_key 或 file_path")
        
        # 根据文件扩展名加载数据
        if target_file.suffix == '.json':
            with open(target_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(target_file, 'r', encoding='utf-8') as f:
                data = f.read()
        
        logger.info(f"📂 数据已加载: {target_file}")
        return data
    
    def list_session_files(self, session_id: str) -> List[Dict[str, Any]]:
        """列出会话中的所有文件"""
        session_path = self.get_session_path(session_id)
        if not session_path:
            return []
        
        files = []
        for file_path in session_path.iterdir():
            if file_path.is_file() and file_path.name != "session_metadata.json":
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": str(file_path.relative_to(session_path)),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "extension": file_path.suffix
                })
        
        return sorted(files, key=lambda x: x['modified'], reverse=True)
    
    def export_for_tool(self, session_id: str, tool_name: str, 
                       data_keys: List[str] = None) -> Dict[str, str]:
        """为特定工具导出数据"""
        session_path = self.get_session_path(session_id)
        if not session_path:
            raise FileNotFoundError(f"会话不存在: {session_id}")
        
        export_map = {}
        
        if data_keys:
            # 导出指定的数据
            for data_key in data_keys:
                try:
                    file_path = self._find_latest_file(session_path, data_key)
                    if file_path:
                        export_map[data_key] = str(file_path)
                except FileNotFoundError:
                    logger.warning(f"未找到数据: {data_key}")
        else:
            # 导出所有数据文件
            for file_path in session_path.iterdir():
                if file_path.is_file() and file_path.name != "session_metadata.json":
                    key = file_path.stem.split('_')[0]  # 提取原始key
                    export_map[key] = str(file_path)
        
        # 更新会话元数据
        export_info = {
            "tool_name": tool_name,
            "exported_at": datetime.now().isoformat(),
            "files": export_map
        }
        self._update_session_metadata(session_id, "data_exported", export_info)
        
        logger.info(f"📤 为工具 {tool_name} 导出了 {len(export_map)} 个文件")
        return export_map
    
    def create_prompt_context(self, session_id: str) -> str:
        """为LLM创建工作区使用提示上下文"""
        session_path = self.get_session_path(session_id)
        if not session_path:
            return "当前没有活跃的工作区会话。"
        
        files = self.list_session_files(session_id)
        
        context = f"""
📁 共享工作区状态 (会话: {session_id})
工作区路径: {session_path}

可用文件:
"""
        if files:
            for file_info in files:
                context += f"  • {file_info['name']} ({file_info['size']} bytes, {file_info['extension']})\n"
        else:
            context += "  暂无文件\n"
        
        context += f"""
💡 工作区使用指南:
- 使用 browser_use 获取的数据会自动保存到工作区
- 在 microsandbox 中可以直接读取这些文件进行分析
- 工作区路径: {session_path}
- 支持的文件格式: JSON, CSV, TXT

示例代码:
```python
# 在 microsandbox 中读取 browser_use 的数据
import json
import pandas as pd
from pathlib import Path

workspace = Path("{session_path}")
# 读取最新的数据文件
data_files = list(workspace.glob("*.json"))
if data_files:
    latest_file = max(data_files, key=lambda p: p.stat().st_mtime)
    with open(latest_file, 'r') as f:
        data = json.load(f)
    print(f"加载数据: {{latest_file.name}}")
```
"""
        return context
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """清理过期会话"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        for session_path in self.session_dir.iterdir():
            if session_path.is_dir():
                metadata_file = session_path / "session_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        
                        created_at = datetime.fromisoformat(metadata['created_at'])
                        if created_at < cutoff_time:
                            shutil.rmtree(session_path)
                            cleaned_count += 1
                            logger.info(f"🗑️ 清理过期会话: {session_path.name}")
                    
                    except Exception as e:
                        logger.error(f"清理会话时出错 {session_path}: {e}")
        
        logger.info(f"✅ 清理完成，共清理 {cleaned_count} 个过期会话")
        return cleaned_count
    
    def _sanitize_filename(self, filename: str) -> str:
        """生成安全的文件名"""
        # 移除或替换不安全字符
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        return ''.join(c if c in safe_chars else '_' for c in filename)
    
    def _find_latest_file(self, session_path: Path, data_key: str) -> Optional[Path]:
        """查找指定key的最新文件"""
        safe_key = self._sanitize_filename(data_key)
        
        for ext in ['json', 'txt', 'csv']:
            pattern = f"{safe_key}_*.{ext}"
            matching_files = list(session_path.glob(pattern))
            if matching_files:
                return max(matching_files, key=lambda p: p.stat().st_mtime)
        
        return None
    
    def _update_session_metadata(self, session_id: str, field: str, value: Any):
        """更新会话元数据"""
        session_path = self.get_session_path(session_id)
        if not session_path:
            return
        
        metadata_file = session_path / "session_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            if field in metadata and isinstance(metadata[field], list):
                metadata[field].append(value)
            else:
                metadata[field] = value
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)


# 全局共享工作区实例
_workspace_manager = None

def get_workspace_manager() -> SharedWorkspaceManager:
    """获取全局共享工作区管理器实例"""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = SharedWorkspaceManager()
    return _workspace_manager


@contextmanager
def workspace_session(session_id: str, metadata: Optional[Dict[str, Any]] = None):
    """工作区会话上下文管理器"""
    manager = get_workspace_manager()
    session_path = manager.create_session(session_id, metadata)
    
    try:
        yield manager
    finally:
        # 可以在这里进行清理操作
        pass