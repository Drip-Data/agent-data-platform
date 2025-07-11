#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🔧 MCP服务器自动注册模块
==============================

目的：解决MCP服务器启动后没有正确注册到工具库的问题
- 自动发现并注册内置MCP服务器
- 确保工具ID映射的一致性
- 解决"工具未找到"的执行错误

作者：Agent Data Platform Team
创建时间：2025-06-25
版本：v1.0.0 - 修复工具执行问题
"""

import logging
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from .interfaces import MCPServerSpec, ToolType, ToolCapability
from .unified_tool_library import UnifiedToolLibrary
from ..unified_tool_manager import get_tool_manager

logger = logging.getLogger(__name__)

@dataclass
class MCPServerInfo:
    """MCP服务器信息"""
    name: str
    service_id: str
    description: str
    host: str
    port: int
    capabilities: List[Dict]
    tags: List[str]

class MCPAutoRegistration:
    """MCP服务器自动注册器"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.mcp_servers_dir = self.project_root / "mcp_servers"
        self.tool_library: Optional[UnifiedToolLibrary] = None
        
        # 内置服务器配置（作为备用）- 与config/mcp_servers.json保持一致
        self.builtin_servers = {
            'microsandbox_server': {
                'service_id': 'microsandbox',
                'port': 8090,
                'description': '在隔离环境中安全执行Python代码'
            },
            'browser_use_server': {
                'service_id': 'browser_use', 
                'port': 8082,  # 修复：使用正确的端口8082
                'description': 'AI驱动的浏览器自动化工具'
            },
            'deepsearch_server': {
                'service_id': 'deepsearch',
                'port': 8086,
                'description': 'AI驱动的深度网络研究工具'
            },
            'search_tool_server': {
                'service_id': 'mcp-search-tool',
                'port': 8080,
                'description': '项目文件内容搜索和工具需求分析器'
            }
        }
    
    async def discover_and_register_all(self, tool_library: UnifiedToolLibrary) -> Dict[str, bool]:
        """发现并注册所有MCP服务器"""
        self.tool_library = tool_library
        registration_results = {}
        
        logger.info("🔍 开始自动发现和注册MCP服务器...")
        
        # 发现所有服务器
        discovered_servers = await self._discover_servers()
        logger.info(f"🎯 发现 {len(discovered_servers)} 个MCP服务器")
        
        # 注册每个服务器
        for server_info in discovered_servers:
            try:
                success = await self._register_server(server_info)
                registration_results[server_info.service_id] = success
                
                if success:
                    logger.info(f"✅ 成功注册MCP服务器: {server_info.service_id}")
                else:
                    logger.error(f"❌ 注册MCP服务器失败: {server_info.service_id}")
                    
            except Exception as e:
                logger.error(f"❌ 注册服务器 {server_info.service_id} 时异常: {e}")
                registration_results[server_info.service_id] = False
        
        # 统计结果
        successful = sum(1 for success in registration_results.values() if success)
        total = len(registration_results)
        
        logger.info(f"📊 MCP服务器注册完成: {successful}/{total} 成功")
        
        return registration_results
    
    async def _discover_servers(self) -> List[MCPServerInfo]:
        """发现所有MCP服务器"""
        discovered_servers = []
        
        # 从文件系统发现
        if self.mcp_servers_dir.exists():
            for server_dir in self.mcp_servers_dir.iterdir():
                if server_dir.is_dir():
                    server_info = await self._parse_server_config(server_dir)
                    if server_info:
                        discovered_servers.append(server_info)
        
        # 如果没有发现服务器，使用内置配置
        if not discovered_servers:
            logger.warning("⚠️ 没有从文件系统发现MCP服务器，使用内置配置")
            for server_name, config in self.builtin_servers.items():
                server_info = MCPServerInfo(
                    name=server_name,
                    service_id=config['service_id'],
                    description=config['description'],
                    host='localhost',
                    port=config['port'],
                    capabilities=[],
                    tags=['builtin', 'mcp']
                )
                discovered_servers.append(server_info)
        
        return discovered_servers
    
    async def _parse_server_config(self, server_dir: Path) -> Optional[MCPServerInfo]:
        """解析服务器配置文件"""
        try:
            service_json_path = server_dir / "service.json"
            
            if not service_json_path.exists():
                logger.debug(f"⚠️ 服务器目录 {server_dir.name} 缺少 service.json")
                return None
            
            with open(service_json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 提取基本信息
            service_id = config.get('service_id')
            if not service_id:
                logger.warning(f"⚠️ 服务器 {server_dir.name} 配置缺少 service_id")
                return None
            
            name = config.get('name', server_dir.name)
            description = config.get('description', '无描述')
            host = config.get('host', 'localhost')
            port = config.get('port', 8080)
            capabilities = config.get('capabilities', [])
            tags = config.get('tags', [])
            
            return MCPServerInfo(
                name=name,
                service_id=service_id,
                description=description,
                host=host,
                port=port,
                capabilities=capabilities,
                tags=tags
            )
            
        except Exception as e:
            logger.error(f"❌ 解析服务器配置失败 {server_dir.name}: {e}")
            return None
    
    async def _register_server(self, server_info: MCPServerInfo) -> bool:
        """注册单个MCP服务器"""
        try:
            # 🔧 关键修复：使用统一工具管理器确保ID一致性
            tool_manager = get_tool_manager()
            
            # 确保使用标准化的工具ID
            try:
                standard_tool_id = tool_manager.get_standard_id(server_info.service_id)
            except ValueError:
                # 如果无法标准化，使用原始ID
                standard_tool_id = server_info.service_id
                logger.warning(f"⚠️ 无法标准化工具ID: {server_info.service_id}，使用原始ID")
            
            # 构建endpoint
            endpoint = f"ws://{server_info.host}:{server_info.port}/websocket"
            
            # 转换capabilities为ToolCapability对象
            tool_capabilities = []
            for cap in server_info.capabilities:
                if isinstance(cap, dict):
                    capability = ToolCapability(
                        name=cap.get('name', ''),
                        description=cap.get('description', ''),
                        parameters=cap.get('parameters', {}),
                        examples=cap.get('examples', [])
                    )
                    tool_capabilities.append(capability)
            
            # 创建MCPServerSpec
            server_spec = MCPServerSpec(
                tool_id=standard_tool_id,  # 使用标准化ID
                name=server_info.name,
                description=server_info.description,
                tool_type=ToolType.MCP_SERVER,
                capabilities=tool_capabilities,
                tags=server_info.tags,
                endpoint=endpoint,
                connection_params={"timeout": 30, "retry_count": 3}
            )
            
            # 注册到工具库
            if self.tool_library:
                registration_result = await self.tool_library.register_external_mcp_server(server_spec)
                return registration_result.success
            else:
                logger.error("⚠️ 工具库未初始化，无法注册服务器")
                return False
                
        except Exception as e:
            logger.error(f"❌ 注册服务器 {server_info.service_id} 失败: {e}")
            return False
    
    async def verify_registrations(self, tool_library: UnifiedToolLibrary) -> Dict[str, bool]:
        """验证所有服务器是否正确注册"""
        verification_results = {}
        
        logger.info("🔍 验证MCP服务器注册状态...")
        
        for server_name, config in self.builtin_servers.items():
            service_id = config['service_id']
            
            try:
                # 检查工具是否存在
                tool_spec = await tool_library.get_tool_by_id(service_id)
                is_registered = tool_spec is not None
                
                verification_results[service_id] = is_registered
                
                if is_registered:
                    logger.info(f"✅ 服务器 {service_id} 注册验证通过")
                else:
                    logger.error(f"❌ 服务器 {service_id} 未正确注册")
                    
            except Exception as e:
                logger.error(f"❌ 验证服务器 {service_id} 时异常: {e}")
                verification_results[service_id] = False
        
        return verification_results

# 全局实例
_auto_registrar: Optional[MCPAutoRegistration] = None

def get_auto_registrar() -> MCPAutoRegistration:
    """获取自动注册器实例"""
    global _auto_registrar
    if _auto_registrar is None:
        _auto_registrar = MCPAutoRegistration()
    return _auto_registrar

async def auto_register_mcp_servers(tool_library: UnifiedToolLibrary) -> bool:
    """自动注册所有MCP服务器的便捷函数"""
    registrar = get_auto_registrar()
    results = await registrar.discover_and_register_all(tool_library)
    
    # 返回是否所有服务器都注册成功
    return all(results.values())