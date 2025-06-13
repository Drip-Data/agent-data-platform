from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Dict, Any, Optional, List
import os
import json

class LLMSettings(BaseSettings):
    provider: str = Field("gemini", description="LLM提供商")
    api_key: str = Field("", description="API密钥")
    api_url: str = Field("", description="API URL")
    model: str = Field("gemini-1.5-flash", description="模型名称")
    
    class Config:
        env_prefix = "LLM_"

class PersistenceSettings(BaseSettings):
    storage_type: str = Field("file", description="存储类型: file, sqlite, mongodb")
    storage_path: str = Field("./data", description="存储路径")
    
    class Config:
        env_prefix = "STORAGE_"

class ToolSettings(BaseSettings):
    registry_path: str = Field("./tools", description="工具注册表路径")
    tool_server_port: int = Field(8080, description="工具服务器端口")
    
    class Config:
        env_prefix = "TOOL_"

class AgentSettings(BaseSettings):
    max_steps: int = Field(10, description="最大执行步骤数")
    timeout: int = Field(300, description="执行超时时间(秒)")
    
    class Config:
        env_prefix = "AGENT_"

class ApplicationConfig(BaseSettings):
    app_name: str = Field("Agent Data Platform", description="应用名称")
    debug: bool = Field(False, description="调试模式")
    log_level: str = Field("INFO", description="日志级别")
    
    llm: LLMSettings = Field(default_factory=LLMSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    tools: ToolSettings = Field(default_factory=ToolSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    
    # 自定义项支持从文件加载
    custom: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('custom', pre=True)
    def load_custom_config(cls, v):
        config_file = os.environ.get('CONFIG_FILE', '')
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return v or {}
    
    class Config:
        env_prefix = "APP_"

class ConfigService:
    """配置服务单例"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigService, cls).__new__(cls)
            cls._instance.config = ApplicationConfig()
            cls._instance.runtime_overrides = {}
        return cls._instance
    
    def get_config(self) -> ApplicationConfig:
        """获取合并后的配置"""
        # 创建配置副本，避免修改原始配置
        merged_config = ApplicationConfig.parse_obj(self.config.dict())
        
        # 应用运行时覆盖
        for key, value in self.runtime_overrides.items():
            # 处理嵌套属性，如 "llm.api_key"
            if "." in key:
                parts = key.split(".")
                obj = merged_config
                for part in parts[:-1]:
                    if hasattr(obj, part):
                        obj = getattr(obj, part)
                if hasattr(obj, parts[-1]):
                    setattr(obj, parts[-1], value)
            elif hasattr(merged_config, key):
                setattr(merged_config, key, value)
        
        return merged_config
    
    def override(self, key: str, value: Any):
        """运行时覆盖配置项"""
        self.runtime_overrides[key] = value
    
    def from_file(self, file_path: str) -> bool:
        """从文件加载配置"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    config_data = json.load(f)
                    # 更新配置
                    self.config = ApplicationConfig.parse_obj(config_data)
                    return True
            return False
        except Exception as e:
            print(f"配置加载错误: {e}")
            return False
    
    def to_file(self, file_path: str) -> bool:
        """保存配置到文件"""
        try:
            with open(file_path, 'w') as f:
                json.dump(self.config.dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"配置保存错误: {e}")
            return False
