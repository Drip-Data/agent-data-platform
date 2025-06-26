#!/usr/bin/env python3
"""
Agent Data Platform 端口管理工具
提供端口检查、自动分配、健康监控等功能
"""

import asyncio
import aiohttp
import socket
import yaml
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import subprocess
import sys

logger = logging.getLogger(__name__)

class PortManager:
    """端口管理器"""
    
    def __init__(self, config_path: str = "config/ports_config.yaml"):
        self.config_path = Path(config_path)
        self.config = self.load_config()
        
    def load_config(self) -> Dict:
        """加载端口配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "core_services": {
                "task_api": {"port": 8000, "description": "任务API"},
                "redis": {"port": 6379, "description": "Redis服务"}
            },
            "mcp_servers": {
                "toolscore_mcp": {"port": 8081, "description": "ToolScore MCP"},
                "toolscore_http": {"port": 8082, "description": "ToolScore HTTP"},
                "python_executor": {"port": 8083, "description": "Python执行器"}
            },
            "port_management": {
                "auto_detect": True,
                "port_range_start": 8088,
                "port_range_end": 8200
            }
        }
    
    def check_port_available(self, port: int, host: str = "localhost") -> bool:
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result != 0  # 连接失败说明端口可用
        except Exception:
            return False
    
    def find_available_port(self, start_port: int = 8088, end_port: int = 8200) -> Optional[int]:
        """查找可用端口"""
        for port in range(start_port, end_port + 1):
            if self.check_port_available(port):
                return port
        return None
    
    def get_all_configured_ports(self) -> Dict[str, int]:
        """获取所有配置的端口"""
        ports = {}
        
        # 核心服务端口
        for service, config in self.config.get("core_services", {}).items():
            ports[f"core.{service}"] = config.get("port")
            
        # MCP服务器端口  
        for service, config in self.config.get("mcp_servers", {}).items():
            ports[f"mcp.{service}"] = config.get("port")
            
        return ports
    
    def check_port_conflicts(self) -> List[Tuple[str, int]]:
        """检查端口冲突"""
        conflicts = []
        ports = self.get_all_configured_ports()
        
        for service, port in ports.items():
            if port and not self.check_port_available(port):
                conflicts.append((service, port))
                
        return conflicts
    
    async def check_service_health(self, service: str, config: Dict) -> bool:
        """检查服务健康状态"""
        port = config.get("port")
        health_endpoint = config.get("health_endpoint", "/health")
        protocol = config.get("protocol", "http")
        
        if not port:
            return False
            
        try:
            if protocol == "http":
                url = f"http://localhost:{port}{health_endpoint}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=5) as resp:
                        return resp.status == 200
            else:
                # 对于WebSocket等其他协议，简单检查端口连通性
                return not self.check_port_available(port)
                
        except Exception as e:
            logger.debug(f"健康检查失败 {service}:{port} - {e}")
            return False
    
    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有服务健康状态"""
        results = {}
        
        # 检查核心服务
        for service, config in self.config.get("core_services", {}).items():
            results[f"core.{service}"] = await self.check_service_health(service, config)
            
        # 检查MCP服务器
        for service, config in self.config.get("mcp_servers", {}).items():
            results[f"mcp.{service}"] = await self.check_service_health(service, config)
            
        return results
    
    def generate_port_status_report(self) -> str:
        """生成端口状态报告"""
        report = []
        report.append("🔌 Agent Data Platform 端口状态报告")
        report.append("=" * 50)
        
        # 检查端口冲突
        conflicts = self.check_port_conflicts()
        if conflicts:
            report.append("\n❌ 端口冲突:")
            for service, port in conflicts:
                report.append(f"  - {service}: 端口 {port} 已被占用")
        else:
            report.append("\n✅ 无端口冲突")
            
        # 显示所有配置的端口
        report.append("\n📋 配置的端口:")
        ports = self.get_all_configured_ports()
        for service, port in ports.items():
            status = "🔴 占用" if not self.check_port_available(port) else "🟢 可用"
            report.append(f"  - {service}: {port} {status}")
            
        return "\n".join(report)
    
    def kill_process_on_port(self, port: int) -> bool:
        """杀死占用指定端口的进程"""
        try:
            if sys.platform == "darwin":  # macOS
                cmd = f"lsof -ti tcp:{port}"
            elif sys.platform.startswith("linux"):  # Linux
                cmd = f"fuser -k {port}/tcp"
            else:  # Windows
                cmd = f'netstat -ano | findstr :{port}'
                
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                if sys.platform in ["darwin", "linux"]:
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        subprocess.run(f"kill -9 {pid}", shell=True)
                    return True
                    
        except Exception as e:
            logger.error(f"杀死端口{port}进程失败: {e}")
            
        return False

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent Data Platform 端口管理工具")
    parser.add_argument("--check", action="store_true", help="检查端口状态")
    parser.add_argument("--health", action="store_true", help="健康检查")
    parser.add_argument("--kill-port", type=int, help="杀死指定端口的进程")
    parser.add_argument("--find-free", action="store_true", help="查找可用端口")
    parser.add_argument("--config", default="config/ports_config.yaml", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 创建端口管理器
    port_manager = PortManager(args.config)
    
    if args.check:
        # 生成端口状态报告
        report = port_manager.generate_port_status_report()
        print(report)
        
    elif args.health:
        # 健康检查
        print("🔍 正在进行健康检查...")
        health_results = await port_manager.health_check_all()
        
        print("\n📊 服务健康状态:")
        for service, is_healthy in health_results.items():
            status = "🟢 健康" if is_healthy else "🔴 异常"
            print(f"  - {service}: {status}")
            
    elif args.kill_port:
        # 杀死指定端口进程
        port = args.kill_port
        print(f"⚠️  尝试杀死端口 {port} 的进程...")
        success = port_manager.kill_process_on_port(port)
        if success:
            print(f"✅ 端口 {port} 已释放")
        else:
            print(f"❌ 无法释放端口 {port}")
            
    elif args.find_free:
        # 查找可用端口
        free_port = port_manager.find_available_port()
        if free_port:
            print(f"🆓 可用端口: {free_port}")
        else:
            print("❌ 没有找到可用端口")
            
    else:
        parser.print_help()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main()) 