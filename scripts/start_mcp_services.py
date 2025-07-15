#!/usr/bin/env python3
"""
MCP服务启动脚本 - 解决轨迹中的连接问题
"""

import subprocess
import sys
import time
import logging
import os
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_service(service_name: str, port: int):
    """启动单个MCP服务"""
    project_root = Path(__file__).parent.parent
    service_path = project_root / "mcp_servers" / f"{service_name}_server" / "main.py"
    
    if not service_path.exists():
        logger.error(f"❌ 服务脚本不存在: {service_path}")
        return False
    
    try:
        logger.info(f"🚀 启动 {service_name} 服务 (端口{port})")
        
        # 设置Python路径以便服务能找到core模块
        env = os.environ.copy()
        env['PYTHONPATH'] = str(project_root)
        
        process = subprocess.Popen(
            [sys.executable, str(service_path)],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待启动
        time.sleep(3)
        
        if process.poll() is None:
            logger.info(f"✅ {service_name} 启动成功 (PID: {process.pid})")
            return True
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ {service_name} 启动失败")
            if stderr:
                logger.error(f"错误: {stderr.decode()}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 启动 {service_name} 异常: {e}")
        return False

def load_mcp_config():
    """从配置文件加载MCP服务端口配置"""
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "mcp_servers.json"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"✅ 成功加载MCP配置: {config_path}")
        return config
    except FileNotFoundError:
        logger.error(f"❌ 配置文件不存在: {config_path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"❌ 配置文件JSON格式错误: {e}")
        return {}

def main():
    """主函数"""
    logger.info("🚀 启动所有MCP服务...")
    
    # 从配置文件动态加载端口配置
    mcp_config = load_mcp_config()
    
    # 构建服务列表，优先使用配置文件中的端口，回退到默认端口
    services = []
    service_mappings = {
        "deepsearch": ("deepsearch_server", 8086),
        "microsandbox": ("microsandbox", 8090),
        "browser_use": ("browser_use_server", 8082),  # 修正为配置文件中的端口
        "search_tool": ("search_tool_server", 8080)
    }
    
    for service_key, (config_key, default_port) in service_mappings.items():
        if config_key in mcp_config:
            port = mcp_config[config_key].get("port", default_port)
            logger.info(f"📍 {service_key} 使用配置文件端口: {port}")
        else:
            port = default_port
            logger.warning(f"⚠️ {service_key} 配置缺失，使用默认端口: {port}")
        
        services.append((service_key, port))
    
    success_count = 0
    for service_name, port in services:
        if start_service(service_name, port):
            success_count += 1
        time.sleep(2)  # 服务间间隔
    
    logger.info(f"\\n📊 启动结果: {success_count}/{len(services)} 服务成功启动")
    
    if success_count >= len(services) * 0.75:
        logger.info("🎉 MCP服务启动成功！")
        return True
    else:
        logger.error("❌ 部分MCP服务启动失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)