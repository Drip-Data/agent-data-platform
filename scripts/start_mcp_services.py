#!/usr/bin/env python3
"""
MCP服务启动脚本 - 解决轨迹中的连接问题
"""

import subprocess
import sys
import time
import logging
import os
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

def main():
    """主函数"""
    logger.info("🚀 启动所有MCP服务...")
    
    services = [
        ("deepsearch", 8086),
        ("microsandbox", 8090),
        ("browser_use", 8084),
        ("search_tool", 8080)
    ]
    
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