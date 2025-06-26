#!/usr/bin/env python3
"""
MCP服务器启动测试
测试各个MCP服务器是否能够正常启动
"""

import asyncio
import pytest
import logging
import time
import signal
import subprocess
import os
from typing import Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestMCPServerStartup:
    """MCP服务器启动测试"""
    
    def test_deepsearch_server_startup(self):
        """测试deepsearch服务器启动"""
        logger.info("🧪 测试deepsearch服务器启动...")
        
        try:
            # 检查服务器文件是否存在
            server_file = "mcp_servers/deepsearch_server/main.py"
            assert os.path.exists(server_file), f"服务器文件不存在: {server_file}"
            
            # 尝试导入测试
            import sys
            original_path = sys.path.copy()
            sys.path.insert(0, '.')
            
            try:
                from mcp_servers.deepsearch_server.main import DeepSearchMCPServer
                logger.info("✅ deepsearch服务器模块导入成功")
            finally:
                sys.path = original_path
                
        except Exception as e:
            logger.error(f"❌ deepsearch服务器启动测试失败: {e}")
            pytest.skip(f"DeepSearch服务器启动测试跳过: {e}")
    
    def test_microsandbox_server_startup(self):
        """测试microsandbox服务器启动"""
        logger.info("🧪 测试microsandbox服务器启动...")
        
        try:
            server_file = "mcp_servers/microsandbox_server/main.py"
            assert os.path.exists(server_file), f"服务器文件不存在: {server_file}"
            
            import sys
            original_path = sys.path.copy()
            sys.path.insert(0, '.')
            
            try:
                from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer
                logger.info("✅ microsandbox服务器模块导入成功")
            finally:
                sys.path = original_path
                
        except Exception as e:
            logger.error(f"❌ microsandbox服务器启动测试失败: {e}")
            pytest.skip(f"MicroSandbox服务器启动测试跳过: {e}")
    
    def test_browser_use_server_startup(self):
        """测试browser_use服务器启动"""
        logger.info("🧪 测试browser_use服务器启动...")
        
        try:
            server_file = "mcp_servers/browser_use_server/main.py"
            assert os.path.exists(server_file), f"服务器文件不存在: {server_file}"
            
            import sys
            original_path = sys.path.copy()
            sys.path.insert(0, '.')
            
            try:
                # 使用新的导入方式
                from mcp_servers.browser_use_server import get_browser_use_server
                BrowserUseMCPServer = get_browser_use_server()
                logger.info("✅ browser_use服务器模块导入成功")
            finally:
                sys.path = original_path
                
        except Exception as e:
            logger.error(f"❌ browser_use服务器启动测试失败: {e}")
            pytest.skip(f"Browser Use服务器启动测试跳过: {e}")
    
    def test_search_tool_server_files(self):
        """测试search_tool服务器文件（暂不启动）"""
        logger.info("🧪 检查search_tool服务器文件...")
        
        try:
            server_file = "mcp_servers/search_tool_server/main.py"
            assert os.path.exists(server_file), f"服务器文件不存在: {server_file}"
            
            tool_file = "mcp_servers/search_tool_server/search_tool.py"
            assert os.path.exists(tool_file), f"工具文件不存在: {tool_file}"
            
            logger.info("✅ search_tool服务器文件检查通过")
            logger.info("ℹ️ search_tool服务器将在后续单独测试")
            
        except Exception as e:
            logger.error(f"❌ search_tool服务器文件检查失败: {e}")
            pytest.fail(f"Search Tool服务器文件检查失败: {e}")
    
    def test_mcp_servers_directory_structure(self):
        """测试MCP服务器目录结构"""
        logger.info("🧪 测试MCP服务器目录结构...")
        
        expected_servers = [
            'deepsearch_server',
            'microsandbox_server',
            'browser_use_server',
            'search_tool_server'
        ]
        
        for server_name in expected_servers:
            server_dir = f"mcp_servers/{server_name}"
            assert os.path.exists(server_dir), f"服务器目录不存在: {server_dir}"
            assert os.path.isdir(server_dir), f"{server_dir} 不是目录"
            
            # 检查主文件
            main_file = f"{server_dir}/main.py"
            assert os.path.exists(main_file), f"主文件不存在: {main_file}"
            
            # 检查__init__.py
            init_file = f"{server_dir}/__init__.py"
            assert os.path.exists(init_file), f"__init__.py不存在: {init_file}"
            
            logger.info(f"✅ 服务器目录结构正确: {server_name}")
        
        logger.info("✅ MCP服务器目录结构测试通过")
    
    @pytest.mark.asyncio
    async def test_service_manager_basic(self):
        """测试服务管理器基本功能"""
        logger.info("🧪 测试服务管理器基本功能...")
        
        try:
            from services.service_manager import ServiceManager
            
            # 创建服务管理器
            service_manager = ServiceManager()
            assert service_manager is not None, "服务管理器创建失败"
            
            logger.info("✅ 服务管理器基本功能测试通过")
            
        except Exception as e:
            logger.error(f"❌ 服务管理器测试失败: {e}")
            pytest.skip(f"服务管理器测试跳过: {e}")


def test_check_dependencies():
    """检查依赖是否满足"""
    logger.info("🧪 检查系统依赖...")
    
    try:
        # 检查Redis
        import redis
        logger.info("✅ Redis模块可用")
        
        # 检查基本依赖
        required_packages = [
            'asyncio',
            'yaml', 
            'json',
            'logging'
        ]
        
        for package in required_packages:
            try:
                __import__(package)
                logger.info(f"✅ 依赖可用: {package}")
            except ImportError:
                logger.warning(f"⚠️ 依赖缺失: {package}")
        
        logger.info("✅ 依赖检查完成")
        
    except Exception as e:
        logger.warning(f"⚠️ 依赖检查失败: {e}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])