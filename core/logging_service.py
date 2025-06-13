import logging
import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import traceback

class JSONFormatter(logging.Formatter):
    """JSON格式化器"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # 添加额外上下文
        for key, value in record.__dict__.items():
            if key.startswith("ctx_") and key != "ctx_name":
                log_data[key[4:]] = value
        
        return json.dumps(log_data)

class LoggingService:
    """日志服务单例"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.log_dir = "./logs"
        self.app_name = "agent-data-platform"
        self.log_level = logging.INFO
        self.use_json_format = False
        self.root_logger = logging.getLogger()
        self.handlers = {}
        self._initialized = True
    
    def configure(self, 
                  log_level: str = "INFO", 
                  log_dir: Optional[str] = None,
                  app_name: Optional[str] = None,
                  use_json_format: bool = False,
                  log_to_console: bool = True,
                  log_to_file: bool = True):
        """配置日志服务"""
        if log_dir:
            self.log_dir = log_dir
        if app_name:
            self.app_name = app_name
        
        # 设置日志级别
        self.log_level = getattr(logging, log_level.upper())
        self.use_json_format = use_json_format
        
        # 重置根日志器
        self.root_logger.setLevel(self.log_level)
        
        # 移除现有处理器
        for handler in list(self.root_logger.handlers):
            self.root_logger.removeHandler(handler)
        
        # 添加控制台处理器
        if log_to_console:
            self._add_console_handler()
        
        # 添加文件处理器
        if log_to_file:
            self._add_file_handler()
        
        # 设置第三方库的日志级别
        self._configure_third_party_loggers()
    
    def _add_console_handler(self):
        """添加控制台处理器"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        
        if self.use_json_format:
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        console_handler.setFormatter(formatter)
        self.root_logger.addHandler(console_handler)
        self.handlers["console"] = console_handler
    
    def _add_file_handler(self):
        """添加文件处理器"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
        
        log_file = os.path.join(self.log_dir, f"{self.app_name}.log")
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(self.log_level)
        
        if self.use_json_format:
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        file_handler.setFormatter(formatter)
        self.root_logger.addHandler(file_handler)
        self.handlers["file"] = file_handler
    
    def _configure_third_party_loggers(self):
        """配置第三方库的日志级别"""
        # 设置常见第三方库的日志级别为警告或错误
        third_party_loggers = [
            "httpx", "asyncio", "urllib3", "httpcore", "requests", 
            "playwright", "aiohttp", "fastapi", "uvicorn"
        ]
        
        for logger_name in third_party_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取命名日志器"""
        return logging.getLogger(name)
    
    def add_context(self, logger: logging.Logger, **context):
        """向日志记录添加上下文"""
        adapter = logging.LoggerAdapter(logger, context)
        return adapter

# 简单使用示例
def setup_logging(log_level: str = "INFO", 
                 log_dir: Optional[str] = None,
                 app_name: Optional[str] = None,
                 use_json_format: bool = False):
    """设置日志服务的便捷函数"""
    service = LoggingService()
    service.configure(
        log_level=log_level,
        log_dir=log_dir,
        app_name=app_name,
        use_json_format=use_json_format
    )
    return service
