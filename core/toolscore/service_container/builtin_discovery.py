"""
内置服务发现器
自动发现和配置内置MCP服务
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .models import ServiceConfig, ServiceType, ServiceCapability, InstallMethod

logger = logging.getLogger(__name__)


class BuiltinServiceDiscovery:
    """内置服务自动发现器"""
    
    def __init__(self, mcp_servers_path: str = None):
        self.mcp_servers_path = Path(mcp_servers_path or "mcp_servers")
        self.discovered_services: Dict[str, ServiceConfig] = {}
        
    def discover_all_services(self) -> Dict[str, ServiceConfig]:
        """发现所有内置服务"""
        logger.info(f"🔍 开始发现内置MCP服务: {self.mcp_servers_path}")
        
        if not self.mcp_servers_path.exists():
            logger.warning(f"⚠️ MCP服务器目录不存在: {self.mcp_servers_path}")
            return {}
        
        discovered = {}
        
        # 遍历所有子目录
        for service_dir in self.mcp_servers_path.iterdir():
            if service_dir.is_dir() and not service_dir.name.startswith('.'):
                try:
                    service_config = self._discover_single_service(service_dir)
                    if service_config:
                        discovered[service_config.service_id] = service_config
                        logger.info(f"✅ 发现内置服务: {service_config.name}")
                except Exception as e:
                    logger.error(f"❌ 发现服务失败 {service_dir.name}: {e}")
        
        self.discovered_services = discovered
        logger.info(f"🎯 内置服务发现完成，共发现 {len(discovered)} 个服务")
        
        return discovered
    
    def _discover_single_service(self, service_dir: Path) -> Optional[ServiceConfig]:
        """发现单个服务"""
        service_name = service_dir.name
        
        # 检查必要文件
        main_py = service_dir / "main.py"
        if not main_py.exists():
            logger.debug(f"⏭️ 跳过 {service_name}: 缺少main.py文件")
            return None
        
        # 尝试从service.json加载配置
        service_json = service_dir / "service.json"
        if service_json.exists():
            return self._load_from_service_json(service_json, service_dir)
        
        # 从代码分析生成配置
        return self._analyze_service_from_code(service_dir)
    
    def _load_from_service_json(self, service_json: Path, service_dir: Path) -> Optional[ServiceConfig]:
        """从service.json文件加载配置"""
        try:
            with open(service_json, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 构建端点URL
            port = config_data.get("port")
            host = config_data.get("host", "localhost")
            service_name = config_data.get("service_id", service_dir.name)
            endpoint = None
            if port:
                # 根据服务名称确定协议和路径
                if service_name == "search_tool_server":
                    endpoint = f"ws://{host}:{port}/mcp"
                elif service_name == "deepsearch_server":
                    endpoint = f"ws://{host}:{port}/mcp"
                else:
                    endpoint = f"ws://{host}:{port}"
            
            # 基础配置
            service_config = ServiceConfig(
                service_id=service_name,
                name=config_data.get("name", service_dir.name.replace("_", " ").title()),
                description=config_data.get("description", f"{service_dir.name} MCP服务"),
                version=config_data.get("version", "1.0.0"),
                service_type=ServiceType.BUILTIN,
                install_method=InstallMethod.NONE,
                local_path=str(service_dir),
                entry_point=config_data.get("entry_point", "main.py"),
                host=host,
                port=port,
                endpoint=endpoint,
                tags=config_data.get("tags", []),
                author=config_data.get("author"),
                license=config_data.get("license"),
                documentation_url=config_data.get("documentation_url"),
                created_at=datetime.now()
            )
            
            # 解析能力
            if "capabilities" in config_data:
                service_config.capabilities = [
                    ServiceCapability(
                        name=cap.get("name"),
                        description=cap.get("description", ""),
                        parameters=cap.get("parameters", {}),
                        required_params=cap.get("required_params", []),
                        optional_params=cap.get("optional_params", []),
                        examples=cap.get("examples", [])
                    )
                    for cap in config_data["capabilities"]
                ]
            
            return service_config
            
        except Exception as e:
            logger.error(f"❌ 解析service.json失败 {service_json}: {e}")
            return None
    
    def _analyze_service_from_code(self, service_dir: Path) -> Optional[ServiceConfig]:
        """从代码分析生成服务配置"""
        service_name = service_dir.name
        
        # 预定义的服务配置
        predefined_configs = {
            "search_tool_server": {
                "name": "Search Tool MCP Server",
                "description": "文件内容搜索和代码定义搜索服务",
                "port": 8080,
                "capabilities": [
                    {
                        "name": "search_files",
                        "description": "在指定目录中搜索文件内容",
                        "parameters": {
                            "query": {"type": "string", "description": "搜索查询"},
                            "path": {"type": "string", "description": "搜索路径"},
                            "file_pattern": {"type": "string", "description": "文件模式"}
                        },
                        "required_params": ["query"],
                        "optional_params": ["path", "file_pattern"]
                    },
                    {
                        "name": "find_definition",
                        "description": "查找代码定义",
                        "parameters": {
                            "symbol": {"type": "string", "description": "符号名称"},
                            "language": {"type": "string", "description": "编程语言"}
                        },
                        "required_params": ["symbol"],
                        "optional_params": ["language"]
                    }
                ],
                "tags": ["search", "files", "code"]
            },
            "browser_use_server": {
                "name": "Browser Use MCP Server",
                "description": "AI驱动的浏览器自动化服务",
                "port": 8082,
                "capabilities": [
                    {
                        "name": "browser_use_execute_task",
                        "description": "执行复杂的浏览器任务",
                        "parameters": {
                            "task": {"type": "string", "description": "自然语言任务描述"},
                            "max_steps": {"type": "integer", "description": "最大执行步数"},
                            "use_vision": {"type": "boolean", "description": "启用视觉理解"}
                        },
                        "required_params": ["task"],
                        "optional_params": ["max_steps", "use_vision"]
                    }
                ],
                "tags": ["browser", "automation", "ai"]
            },
            "deepsearch_server": {
                "name": "DeepSearch MCP Server", 
                "description": "深度搜索和分析服务",
                "port": 8086,
                "capabilities": [
                    {
                        "name": "deep_search",
                        "description": "执行深度搜索分析",
                        "parameters": {
                            "query": {"type": "string", "description": "搜索查询"},
                            "depth": {"type": "integer", "description": "搜索深度"},
                            "sources": {"type": "array", "description": "搜索源"}
                        },
                        "required_params": ["query"],
                        "optional_params": ["depth", "sources"]
                    }
                ],
                "tags": ["search", "analysis", "deep"]
            },
            "microsandbox_server": {
                "name": "MicroSandbox MCP Server",
                "description": "安全的代码执行沙盒服务",
                "port": 8090,
                "capabilities": [
                    {
                        "name": "microsandbox_execute",
                        "description": "在沙盒中安全执行代码",
                        "parameters": {
                            "code": {"type": "string", "description": "要执行的代码"},
                            "language": {"type": "string", "description": "编程语言"},
                            "timeout": {"type": "integer", "description": "超时时间"}
                        },
                        "required_params": ["code", "language"],
                        "optional_params": ["timeout"]
                    }
                ],
                "tags": ["sandbox", "execution", "security"]
            }
        }
        
        if service_name not in predefined_configs:
            logger.debug(f"⏭️ 未知内置服务: {service_name}")
            return None
        
        config_data = predefined_configs[service_name]
        
        # 构建端点URL
        port = config_data["port"]
        host = "localhost"
        endpoint = None
        if port:
            # 根据服务名称确定协议和路径
            if service_name == "search_tool_server":
                endpoint = f"ws://{host}:{port}/mcp"
            elif service_name == "deepsearch_server":
                endpoint = f"ws://{host}:{port}/mcp"
            else:
                endpoint = f"ws://{host}:{port}"
        
        # 创建服务配置
        service_config = ServiceConfig(
            service_id=service_name.replace("_server", ""),
            name=config_data["name"],
            description=config_data["description"],
            version="1.0.0",
            service_type=ServiceType.BUILTIN,
            install_method=InstallMethod.NONE,
            local_path=str(service_dir),
            entry_point="main.py",
            host=host,
            port=port,
            endpoint=endpoint,
            protocol="websocket",
            tags=config_data["tags"],
            auto_start=True,
            created_at=datetime.now()
        )
        
        # 添加能力
        service_config.capabilities = [
            ServiceCapability(
                name=cap["name"],
                description=cap["description"],
                parameters=cap["parameters"],
                required_params=cap["required_params"],
                optional_params=cap["optional_params"]
            )
            for cap in config_data["capabilities"]
        ]
        
        return service_config
    
    def create_service_json_files(self) -> None:
        """为所有发现的服务创建service.json配置文件"""
        logger.info("📝 创建服务配置文件...")
        
        for service_id, service_config in self.discovered_services.items():
            service_dir = Path(service_config.local_path)
            service_json = service_dir / "service.json"
            
            if service_json.exists():
                logger.debug(f"⏭️ 配置文件已存在: {service_json}")
                continue
            
            try:
                config_data = {
                    "service_id": service_config.service_id,
                    "name": service_config.name,
                    "description": service_config.description,
                    "version": service_config.version,
                    "entry_point": service_config.entry_point,
                    "host": service_config.host,
                    "port": service_config.port,
                    "capabilities": [
                        {
                            "name": cap.name,
                            "description": cap.description,
                            "parameters": cap.parameters,
                            "required_params": cap.required_params,
                            "optional_params": cap.optional_params,
                            "examples": cap.examples
                        }
                        for cap in service_config.capabilities
                    ],
                    "tags": service_config.tags,
                    "author": service_config.author,
                    "license": service_config.license,
                    "documentation_url": service_config.documentation_url
                }
                
                with open(service_json, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                
                logger.info(f"✅ 创建配置文件: {service_json}")
                
            except Exception as e:
                logger.error(f"❌ 创建配置文件失败 {service_json}: {e}")
    
    def get_service_summary(self) -> Dict[str, Any]:
        """获取服务发现摘要"""
        if not self.discovered_services:
            self.discover_all_services()
        
        return {
            "total_services": len(self.discovered_services),
            "services": [
                {
                    "id": config.service_id,
                    "name": config.name,
                    "description": config.description,
                    "port": config.port,
                    "capabilities_count": len(config.capabilities),
                    "tags": config.tags
                }
                for config in self.discovered_services.values()
            ],
            "discovery_path": str(self.mcp_servers_path),
            "discovery_time": datetime.now().isoformat()
        }