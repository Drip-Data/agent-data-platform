"""
配置管理模块 - Agent Data Platform
统一管理系统配置，确保架构一致性
"""

import os
import yaml
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class QueueConfig:
    """队列配置"""
    name: str
    description: str
    consumer_group: str = "workers"
    max_length: int = 10000
    retention_policy: str = "7d"

@dataclass
class RuntimeConfig:
    """运行时配置"""
    queue: str
    capabilities: list
    health_check: Dict[str, Any]
    scaling: Dict[str, Any]

@dataclass
class RoutingConfig:
    """路由配置"""
    unified_mode: bool
    queues: Dict[str, QueueConfig]
    task_type_mapping: Dict[str, str]
    runtimes: Dict[str, RuntimeConfig]

class ConfigManager:
    """配置管理器 - 统一配置加载和验证"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._configs = {}
        self._routing_config: Optional[RoutingConfig] = None
        
    def load_routing_config(self) -> RoutingConfig:
        """加载路由配置"""
        if self._routing_config:
            return self._routing_config
            
        try:
            config_path = self.config_dir / "routing_config.yaml"
            if not config_path.exists():
                logger.warning(f"路由配置文件不存在: {config_path}")
                return self._get_default_routing_config()
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 解析队列配置
            queues = {}
            for queue_name, queue_data in config_data.get("queue_mapping", {}).get("queues", {}).items():
                queues[queue_name] = QueueConfig(**queue_data)
            
            # 解析运行时配置  
            runtimes = {}
            for runtime_name, runtime_data in config_data.get("runtimes", {}).items():
                runtimes[runtime_name] = RuntimeConfig(**runtime_data)
            
            self._routing_config = RoutingConfig(
                unified_mode=config_data.get("queue_mapping", {}).get("unified_mode", True),
                queues=queues,
                task_type_mapping=config_data.get("queue_mapping", {}).get("task_type_mapping", {}),
                runtimes=runtimes
            )
            
            logger.info("路由配置加载成功")
            return self._routing_config
            
        except Exception as e:
            logger.error(f"加载路由配置失败: {e}")
            return self._get_default_routing_config()
    
    def _get_default_routing_config(self) -> RoutingConfig:
        """获取默认路由配置"""
        return RoutingConfig(
            unified_mode=True,
            queues={
                "reasoning": QueueConfig(
                    name="tasks:reasoning",
                    description="统一推理队列",
                    consumer_group="reasoning-workers"
                )
            },
            task_type_mapping={
                "CODE": "tasks:reasoning",
                "WEB": "tasks:reasoning", 
                "REASONING": "tasks:reasoning"
            },
            runtimes={
                "enhanced-reasoning": RuntimeConfig(
                    queue="tasks:reasoning",
                    capabilities=[
                        "text_analysis", "logical_reasoning", "planning",
                        "python_executor", "browser_automation", "web_scraping"
                    ],
                    health_check={"enabled": True, "interval": 60, "timeout": 10},
                    scaling={"min_workers": 1, "max_workers": 5}
                )
            }
        )
    
    def load_ports_config(self) -> Dict[str, Any]:
        """加载端口配置"""
        try:
            config_path = self.config_dir / "ports_config.yaml"
            if not config_path.exists():
                return self._get_default_ports_config()
                
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
                
        except Exception as e:
            logger.error(f"加载端口配置失败: {e}")
            return self._get_default_ports_config()
    
    def _get_default_ports_config(self) -> Dict[str, Any]:
        """获取默认端口配置"""
        return {
            "core_services": {
                "task_api": {"port": 8000},
                "redis": {"port": 6379}
            },
            "mcp_servers": {
                "toolscore_mcp": {"port": 8081},
                "toolscore_http": {"port": 8082},
                "python_executor": {"port": 8083},
                "browser_navigator": {"port": 8084}
            }
        }
    
    def get_queue_mapping(self) -> Dict[str, str]:
        """获取任务类型到队列的映射"""
        routing_config = self.load_routing_config()
        return routing_config.task_type_mapping
    
    def get_tool_service_url(self) -> str:
        """获取工具服务URL"""
        ports_config = self.load_ports_config()
        port = ports_config.get("mcp_servers", {}).get("toolscore_http", {}).get("port", 8082)
        return f"http://localhost:{port}"
    
    def get_ports_config(self) -> Dict[str, Any]:
        """获取端口配置"""
        return self.load_ports_config()
    
    def get_fallback_tools_mapping(self) -> Dict[str, list]:
        """获取备选工具映射"""
        try:
            config_path = self.config_dir / "routing_config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                return config_data.get("tool_recommendation", {}).get("fallback_mapping", {})
        except Exception as e:
            logger.error(f"加载备选工具配置失败: {e}")
        
        # 默认配置
        return {
            "CODE": ["python_executor"],
            "WEB": ["browser_navigator", "web_search"],
            "REASONING": ["python_executor", "browser_navigator"]
        }
    
    def validate_config_consistency(self) -> Dict[str, list]:
        """验证配置一致性"""
        issues = []
        warnings = []
        
        try:
            # 检查路由配置
            routing_config = self.load_routing_config()
            ports_config = self.load_ports_config()
            
            # 检查队列映射一致性
            if not routing_config.unified_mode:
                warnings.append("建议启用统一路由模式以简化架构")
            
            # 检查端口冲突
            used_ports = set()
            for service_group in ports_config.values():
                if isinstance(service_group, dict):
                    for service_name, service_config in service_group.items():
                        if isinstance(service_config, dict) and "port" in service_config:
                            port = service_config["port"]
                            if port in used_ports:
                                issues.append(f"端口冲突: {port} 被多个服务使用")
                            used_ports.add(port)
            
            # 检查配置文件存在性
            required_configs = ["routing_config.yaml", "ports_config.yaml"]
            for config_file in required_configs:
                if not (self.config_dir / config_file).exists():
                    warnings.append(f"配置文件缺失: {config_file}")
            
            logger.info(f"配置验证完成: {len(issues)} 个问题, {len(warnings)} 个警告")
            
        except Exception as e:
            issues.append(f"配置验证失败: {e}")
        
        return {
            "issues": issues,
            "warnings": warnings
        }
    
    def export_current_config(self, output_path: str = "config_export.json"):
        """导出当前配置"""
        try:
            config_export = {
                "routing_config": self.load_routing_config().__dict__,
                "ports_config": self.load_ports_config(),
                "fallback_tools": self.get_fallback_tools_mapping(),
                "queue_mapping": self.get_queue_mapping(),
                "tool_service_url": self.get_tool_service_url()
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(config_export, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"配置导出成功: {output_path}")
            
        except Exception as e:
            logger.error(f"配置导出失败: {e}")

# 全局配置管理器实例
config_manager = ConfigManager()

def get_queue_mapping() -> Dict[str, str]:
    """获取队列映射配置"""
    return config_manager.get_queue_mapping()

def get_tool_service_url() -> str:
    """获取工具服务URL"""
    return config_manager.get_tool_service_url()

def get_ports_config() -> Dict[str, Any]:
    """获取端口配置"""
    return config_manager.load_ports_config()

def get_fallback_tools_mapping() -> Dict[str, list]:
    """获取备选工具映射"""
    return config_manager.get_fallback_tools_mapping()

def validate_config() -> Dict[str, list]:
    """验证配置一致性"""
    return config_manager.validate_config_consistency()
