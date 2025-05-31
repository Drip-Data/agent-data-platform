import json
import logging
import time
from typing import Any, Dict, List, Optional
import hashlib
import uuid

logger = logging.getLogger(__name__)

def generate_task_id() -> str:
    """生成唯一任务ID"""
    return str(uuid.uuid4())

def hash_content(content: str) -> str:
    """生成内容哈希"""
    return hashlib.md5(content.encode()).hexdigest()

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

def format_duration(seconds: float) -> str:
    """格式化持续时间"""
    if seconds < 1:
        return f"{seconds*1000:.1f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m{secs:.1f}s"

def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def validate_task_spec(task_data: Dict) -> List[str]:
    """验证任务规范"""
    errors = []
    
    required_fields = ['task_id', 'task_type', 'description']
    for field in required_fields:
        if field not in task_data:
            errors.append(f"Missing required field: {field}")
    
    if 'task_type' in task_data:
        valid_types = ['code', 'web', 'reasoning']
        if task_data['task_type'] not in valid_types:
            errors.append(f"Invalid task_type: {task_data['task_type']}. Must be one of {valid_types}")
    
    if 'timeout' in task_data:
        try:
            timeout = int(task_data['timeout'])
            if timeout <= 0 or timeout > 3600:
                errors.append("Timeout must be between 1 and 3600 seconds")
        except (ValueError, TypeError):
            errors.append("Timeout must be a valid integer")
    
    return errors

def setup_logging(level: str = "INFO", format_string: Optional[str] = None) -> None:
    """设置日志配置"""
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def get_current_timestamp() -> float:
    """获取当前时间戳"""
    return time.time()

def timestamp_to_str(timestamp: float) -> str:
    """时间戳转字符串"""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))

class RateLimiter:
    """简单的速率限制器"""
    
    def __init__(self, max_calls: int, time_window: int):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def is_allowed(self) -> bool:
        """检查是否允许调用"""
        now = time.time()
        
        # 清理过期的调用记录
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < self.time_window]
        
        # 检查是否超过限制
        if len(self.calls) >= self.max_calls:
            return False
        
        # 记录本次调用
        self.calls.append(now)
        return True
    
    def time_until_next_call(self) -> float:
        """距离下次可调用的时间"""
        if len(self.calls) < self.max_calls:
            return 0
        
        oldest_call = min(self.calls)
        return self.time_window - (time.time() - oldest_call)

class CircuitBreaker:
    """简单的熔断器"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        """通过熔断器调用函数"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """成功时的处理"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """失败时的处理"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"