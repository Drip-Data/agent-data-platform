import json
from typing import Any

def safe_json_loads(data: str, default: Any = None) -> Any:
    """安全的JSON解析"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default

def safe_json_dumps(data: Any, default: str = "") -> str:
    """安全的JSON序列化"""
    try:
        return json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        return default