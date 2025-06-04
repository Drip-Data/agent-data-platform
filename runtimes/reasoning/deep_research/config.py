"""
Configuration module for Deep Research
深度研究模块的配置管理
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from .state import ResearchConfiguration


@dataclass
class DeepResearchConfig:
    """深度研究配置类"""
    
    # API 配置
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_api_url: str = field(default_factory=lambda: os.getenv("GEMINI_API_URL", ""))
    
    # 模型配置
    reasoning_model: str = "gemini-2.0-flash-exp"
    query_generator_model: str = "gemini-2.0-flash-exp"
    
    # 研究参数
    initial_search_query_count: int = 3
    max_research_loops: int = 3
    max_query_length: int = 500
    max_result_length: int = 5000
    
    # 性能配置
    request_timeout: int = 30
    max_retries: int = 2
    temperature: float = 0.7
    
    # 功能开关
    enable_citation_tracking: bool = True
    enable_query_optimization: bool = True
    enable_result_validation: bool = True
    
    # 调试配置
    debug_mode: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    def __post_init__(self):
        """初始化后验证配置"""
        self.validate()
    
    def validate(self):
        """验证配置参数"""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY 环境变量必须设置")
        
        if self.initial_search_query_count < 1 or self.initial_search_query_count > 10:
            raise ValueError("initial_search_query_count 必须在 1-10 之间")
        
        if self.max_research_loops < 1 or self.max_research_loops > 10:
            raise ValueError("max_research_loops 必须在 1-10 之间")
        
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature 必须在 0-2 之间")
    
    def to_research_config(self) -> ResearchConfiguration:
        """转换为研究配置对象"""
        return ResearchConfiguration(
            initial_search_query_count=self.initial_search_query_count,
            max_research_loops=self.max_research_loops,
            reasoning_model=self.reasoning_model,
            query_generator_model=self.query_generator_model
        )
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'DeepResearchConfig':
        """从字典创建配置"""
        return cls(**{k: v for k, v in config_dict.items() if hasattr(cls, k)})
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'gemini_api_key': self.gemini_api_key,
            'gemini_api_url': self.gemini_api_url,
            'reasoning_model': self.reasoning_model,
            'query_generator_model': self.query_generator_model,
            'initial_search_query_count': self.initial_search_query_count,
            'max_research_loops': self.max_research_loops,
            'max_query_length': self.max_query_length,
            'max_result_length': self.max_result_length,
            'request_timeout': self.request_timeout,
            'max_retries': self.max_retries,
            'temperature': self.temperature,
            'enable_citation_tracking': self.enable_citation_tracking,
            'enable_query_optimization': self.enable_query_optimization,
            'enable_result_validation': self.enable_result_validation,
            'debug_mode': self.debug_mode,
            'log_level': self.log_level
        }
    
    def update_from_env(self):
        """从环境变量更新配置"""
        env_mappings = {
            'REASONING_MODEL': 'reasoning_model',
            'QUERY_GENERATOR_MODEL': 'query_generator_model',
            'INITIAL_SEARCH_QUERY_COUNT': 'initial_search_query_count',
            'MAX_RESEARCH_LOOPS': 'max_research_loops',
            'REQUEST_TIMEOUT': 'request_timeout',
            'MAX_RETRIES': 'max_retries',
            'TEMPERATURE': 'temperature'
        }
        
        for env_key, attr_name in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value:
                try:
                    if attr_name in ['initial_search_query_count', 'max_research_loops', 
                                   'request_timeout', 'max_retries']:
                        setattr(self, attr_name, int(env_value))
                    elif attr_name == 'temperature':
                        setattr(self, attr_name, float(env_value))
                    else:
                        setattr(self, attr_name, env_value)
                except (ValueError, TypeError) as e:
                    print(f"警告: 无法解析环境变量 {env_key}={env_value}: {e}")


# 预定义配置模板
class ConfigTemplates:
    """配置模板"""
    
    @staticmethod
    def development() -> DeepResearchConfig:
        """开发环境配置"""
        return DeepResearchConfig(
            initial_search_query_count=2,
            max_research_loops=2,
            debug_mode=True,
            log_level="DEBUG"
        )
    
    @staticmethod
    def production() -> DeepResearchConfig:
        """生产环境配置"""
        return DeepResearchConfig(
            initial_search_query_count=3,
            max_research_loops=3,
            debug_mode=False,
            log_level="INFO"
        )
    
    @staticmethod
    def high_quality() -> DeepResearchConfig:
        """高质量研究配置"""
        return DeepResearchConfig(
            initial_search_query_count=5,
            max_research_loops=5,
            temperature=0.3,
            enable_citation_tracking=True,
            enable_query_optimization=True,
            enable_result_validation=True
        )
    
    @staticmethod
    def fast() -> DeepResearchConfig:
        """快速研究配置"""
        return DeepResearchConfig(
            initial_search_query_count=1,
            max_research_loops=1,
            temperature=1.0,
            request_timeout=15
        )


def load_config(config_type: str = "default") -> DeepResearchConfig:
    """
    加载配置
    
    Args:
        config_type: 配置类型 ("default", "development", "production", "high_quality", "fast")
        
    Returns:
        配置对象
    """
    if config_type == "development":
        config = ConfigTemplates.development()
    elif config_type == "production":
        config = ConfigTemplates.production()
    elif config_type == "high_quality":
        config = ConfigTemplates.high_quality()
    elif config_type == "fast":
        config = ConfigTemplates.fast()
    else:
        config = DeepResearchConfig()
    
    # 从环境变量更新配置
    config.update_from_env()
    
    return config


# 全局配置实例
default_config = load_config()