#!/usr/bin/env python3
"""
Docker容器统一管理器
管理synthesis相关的Docker容器和服务
"""

import subprocess
import argparse
import sys
import time
import requests
from typing import List, Dict, Any

class DockerManager:
    def __init__(self):
        self.compose_file = "docker-compose.synthesis.yml"
        self.network_name = "agent-data-platform"
        
    def _run_command(self, cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """执行命令"""
        print(f"🔧 执行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
            if result.stdout:
                print(result.stdout)
            return result
        except subprocess.CalledProcessError as e:
            print(f"❌ 命令执行失败: {e}")
            if e.stderr:
                print(f"错误信息: {e.stderr}")
            if check:
                raise
            return e
    
    def check_docker(self) -> bool:
        """检查Docker是否可用"""
        print("🐳 检查Docker状态...")
        try:
            result = self._run_command(["docker", "--version"], check=False)
            if result.returncode == 0:
                print("✅ Docker可用")
                return True
            else:
                print("❌ Docker不可用")
                return False
        except FileNotFoundError:
            print("❌ Docker未安装")
            return False
    
    def create_network(self) -> None:
        """创建Docker网络"""
        print(f"🌐 创建Docker网络: {self.network_name}")
        
        # 检查网络是否已存在
        result = self._run_command(["docker", "network", "ls", "--filter", f"name={self.network_name}"], check=False)
        if self.network_name in result.stdout:
            print(f"✅ 网络 {self.network_name} 已存在")
            return
        
        # 创建网络
        self._run_command(["docker", "network", "create", self.network_name])
        print(f"✅ 网络 {self.network_name} 创建成功")
    
    def build_images(self) -> None:
        """构建Docker镜像"""
        print("🔨 构建synthesis镜像...")
        self._run_command([
            "docker-compose", "-f", self.compose_file, "build", "--no-cache"
        ])
        print("✅ 镜像构建完成")
    
    def start_services(self, services: List[str] = None) -> None:
        """启动服务"""
        if services is None:
            services = []
        
        print(f"🚀 启动synthesis服务...")
        cmd = ["docker-compose", "-f", self.compose_file, "up", "-d"]
        if services:
            cmd.extend(services)
        
        self._run_command(cmd)
        print("✅ 服务启动完成")
    
    def stop_services(self) -> None:
        """停止服务"""
        print("🛑 停止synthesis服务...")
        self._run_command([
            "docker-compose", "-f", self.compose_file, "down"
        ])
        print("✅ 服务已停止")
    
    def restart_services(self) -> None:
        """重启服务"""
        print("🔄 重启synthesis服务...")
        self.stop_services()
        time.sleep(2)
        self.start_services()
    
    def show_status(self) -> None:
        """显示服务状态"""
        print("📊 服务状态:")
        self._run_command([
            "docker-compose", "-f", self.compose_file, "ps"
        ])
        
        # 检查网络
        print(f"\n🌐 网络状态:")
        self._run_command([
            "docker", "network", "inspect", self.network_name
        ], check=False)
    
    def show_logs(self, service: str = None, follow: bool = False) -> None:
        """显示日志"""
        print(f"📋 显示日志 (服务: {service or '全部'})...")
        cmd = ["docker-compose", "-f", self.compose_file, "logs"]
        if follow:
            cmd.append("-f")
        if service:
            cmd.append(service)
        
        self._run_command(cmd)
    
    def cleanup(self) -> None:
        """清理Docker资源"""
        print("🧹 清理Docker资源...")
        
        # 停止服务
        self.stop_services()
        
        # 删除未使用的镜像和容器
        self._run_command(["docker", "system", "prune", "-f"])
        
        print("✅ 清理完成")
    
    def exec_command(self, service: str, command: str) -> None:
        """在容器中执行命令"""
        print(f"⚡ 在 {service} 容器中执行: {command}")
        self._run_command([
            "docker-compose", "-f", self.compose_file, "exec", service, "sh", "-c", command
        ])
    
    def wait_for_healthy(self, timeout: int = 60) -> bool:
        """等待服务健康"""
        print("⏳ 等待服务健康...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get("http://localhost:8081/health", timeout=5)
                if response.status_code == 200:
                    print("✅ Synthesis服务已就绪")
                    return True
            except requests.exceptions.RequestException:
                pass
            
            print(".", end="", flush=True)
            time.sleep(2)
        
        print("\n❌ 服务健康检查超时")
        return False
    
    def full_deploy(self) -> None:
        """完整部署流程"""
        print("🚀 开始完整部署...")
        
        # 1. 检查Docker
        if not self.check_docker():
            print("❌ Docker检查失败，退出")
            return
        
        # 2. 创建网络
        self.create_network()
        
        # 3. 构建镜像
        self.build_images()
        
        # 4. 启动服务
        self.start_services()
        
        # 5. 等待健康
        if self.wait_for_healthy():
            print("🎉 部署成功！")
            print("📱 可以使用以下命令管理synthesis:")
            print("   python scripts/synthesis_manager.py health")
            print("   python scripts/synthesis_manager.py tasks")
            print("   python scripts/synthesis_manager.py stats")
        else:
            print("❌ 部署失败")
            self.show_logs()

def main():
    parser = argparse.ArgumentParser(description="Docker容器统一管理器")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # Docker检查
    subparsers.add_parser("check", help="检查Docker状态")
    
    # 网络管理
    subparsers.add_parser("network", help="创建Docker网络")
    
    # 镜像构建
    subparsers.add_parser("build", help="构建Docker镜像")
    
    # 服务管理
    start_parser = subparsers.add_parser("start", help="启动服务")
    start_parser.add_argument("services", nargs="*", help="指定服务名称")
    
    subparsers.add_parser("stop", help="停止服务")
    subparsers.add_parser("restart", help="重启服务")
    
    # 状态查看
    subparsers.add_parser("status", help="查看服务状态")
    
    # 日志查看
    logs_parser = subparsers.add_parser("logs", help="查看日志")
    logs_parser.add_argument("service", nargs="?", help="服务名称")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="跟踪日志")
    
    # 容器执行
    exec_parser = subparsers.add_parser("exec", help="在容器中执行命令")
    exec_parser.add_argument("service", help="服务名称")
    exec_parser.add_argument("command", help="要执行的命令")
    
    # 清理
    subparsers.add_parser("cleanup", help="清理Docker资源")
    
    # 完整部署
    subparsers.add_parser("deploy", help="完整部署流程")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = DockerManager()
    
    try:
        if args.command == "check":
            manager.check_docker()
        elif args.command == "network":
            manager.create_network()
        elif args.command == "build":
            manager.build_images()
        elif args.command == "start":
            manager.start_services(args.services)
        elif args.command == "stop":
            manager.stop_services()
        elif args.command == "restart":
            manager.restart_services()
        elif args.command == "status":
            manager.show_status()
        elif args.command == "logs":
            manager.show_logs(args.service, args.follow)
        elif args.command == "exec":
            manager.exec_command(args.service, args.command)
        elif args.command == "cleanup":
            manager.cleanup()
        elif args.command == "deploy":
            manager.full_deploy()
        else:
            print(f"❌ 未知命令: {args.command}")
            parser.print_help()
            
    except KeyboardInterrupt:
        print("\n👋 操作被用户中断")
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 