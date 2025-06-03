#!/usr/bin/env python3
"""
Synthesis服务统一管理器
通过容器化API统一管理所有synthesis操作
"""

import requests
import json
import argparse
import sys
import time
from typing import Dict, Any, Optional

class SynthesisManager:
    def __init__(self, base_url: str = "http://localhost:8081"):
        self.base_url = base_url
        
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送HTTP请求到synthesis API"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API请求失败: {e}")
            return {"success": False, "error": str(e)}
    
    def health_check(self) -> bool:
        """检查服务健康状态"""
        print("🔍 检查synthesis服务状态...")
        result = self._make_request("GET", "/health")
        if result.get("status") == "healthy":
            print("✅ Synthesis服务运行正常")
            print(f"   Redis状态: {result.get('redis', 'unknown')}")
            return True
        else:
            print("❌ Synthesis服务不可用")
            print(f"   错误信息: {result}")
            return False
    
    def init_database(self) -> bool:
        """初始化数据库"""
        print("🗄️ 初始化synthesis数据库...")
        result = self._make_request("POST", "/init-db")
        if result.get("success"):
            print("✅ 数据库初始化成功")
            return True
        else:
            print(f"❌ 数据库初始化失败: {result.get('detail', 'Unknown error')}")
            return False
    
    def view_tasks(self) -> None:
        """查看数据库中的所有任务"""
        print("📊 获取数据库任务...")
        result = self._make_request("GET", "/db/tasks")
        
        if not result.get("success"):
            print(f"❌ 获取任务失败: {result.get('detail', 'Unknown error')}")
            return
        
        summary = result["summary"]
        print(f"\n📈 任务统计:")
        print(f"  - 任务本质: {summary['total_essences']} 个")
        print(f"  - 生成任务: {summary['total_tasks']} 个")
        
        # 显示任务本质
        if result["task_essences"]:
            print(f"\n🧬 任务本质:")
            for i, essence in enumerate(result["task_essences"], 1):
                print(f"  {i}. [{essence['task_type']}] {essence['description']}")
                print(f"     ID: {essence['id']}")
                print(f"     领域: {essence['tool_category']}")
        
        # 显示生成的任务
        if result["generated_tasks"]:
            print(f"\n🎯 生成的任务:")
            for i, task in enumerate(result["generated_tasks"], 1):
                try:
                    task_spec = json.loads(task["task_spec"])
                    print(f"  {i}. [{task_spec.get('task_type', 'unknown')}] {task_spec.get('description', 'No description')}")
                    print(f"     任务ID: {task['task_id']}")
                    print(f"     工具: {', '.join(task_spec.get('expected_tools', []))}")
                    print(f"     步骤: {task_spec.get('max_steps', 'N/A')}")
                except json.JSONDecodeError:
                    print(f"  {i}. [解析错误] 任务ID: {task['task_id']}")
                    print(f"     原始任务规范: {task['task_spec']}")
    
    def get_stats(self) -> None:
        """获取数据库统计信息"""
        print("📊 获取数据库统计...")
        result = self._make_request("GET", "/db/stats")
        
        if "essences" not in result:
            print(f"❌ 获取统计失败: {result.get('detail', 'Unknown error')}")
            return
        
        print(f"\n📈 数据库统计:")
        print(f"  - 任务本质: {result['essences']['total']} 个")
        print(f"  - 生成任务: {result['generated_tasks']['total']} 个")
        print(f"  - 已执行任务: {result['generated_tasks']['executed']} 个")
        print(f"  - 待执行任务: {result['generated_tasks']['pending']} 个")
        
        if result['essences']['by_type']:
            print(f"  - 本质按类型分布: {dict(result['essences']['by_type'])}")
        
        if result['essences']['by_domain']:
            print(f"  - 本质按领域分布: {dict(result['essences']['by_domain'])}")
    
    def export_tasks(self, format: str = "jsonl") -> None:
        """导出任务数据"""
        print(f"📤 导出任务数据 (格式: {format})...")
        result = self._make_request("GET", f"/db/export?format={format}")
        
        if not result.get("success"):
            print(f"❌ 导出失败: {result.get('detail', 'Unknown error')}")
            return
        
        print(f"✅ 成功导出 {result['count']} 个任务")
        
        # 保存到文件
        filename = f"exported_tasks.{format}"
        if format == "jsonl":
            with open(filename, 'w', encoding='utf-8') as f:
                for task in result['data']:
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
        
        print(f"📁 任务已保存到: {filename}")
    
    def clear_database(self) -> bool:
        """清空数据库"""
        confirm = input("⚠️ 确定要清空数据库吗? (y/N): ")
        if confirm.lower() != 'y':
            print("取消操作")
            return False
        
        print("🗑️ 清空数据库...")
        result = self._make_request("POST", "/db/clear")
        
        if result.get("success"):
            print("✅ 数据库清空成功")
            return True
        else:
            print(f"❌ 清空失败: {result.get('detail', 'Unknown error')}")
            return False
    
    def generate_task(self, trajectory_file: str) -> None:
        """生成任务"""
        print(f"🚀 开始轨迹分析和任务生成...")
        
        # 触发完整分析
        result = self._make_request("POST", "/trigger/full", 
                                   json={"trajectory_file": trajectory_file})
        
        if result.get("success"):
            print(f"✅ 任务生成请求已发送")
            print(f"📝 命令已添加到队列: {result.get('message', '')}")
            
            # 等待处理完成
            print("⏳ 等待处理完成...")
            time.sleep(5)  # 给一些时间处理
            
            # 查看结果
            self.view_tasks()
        else:
            print(f"❌ 任务生成失败: {result.get('detail', 'Unknown error')}")
    
    def status(self) -> None:
        """查看服务状态"""
        result = self._make_request("GET", "/status")
        if result.get("success"):
            print("📋 服务状态:")
            print(f"  - Redis队列: {'正常' if result.get('redis_connected') else '异常'}")
            print(f"  - 数据库: {'正常' if result.get('db_accessible') else '异常'}")
        else:
            print("❌ 无法获取服务状态")

def main():
    parser = argparse.ArgumentParser(description="Synthesis服务统一管理器")
    parser.add_argument("--url", default="http://localhost:8081", 
                       help="Synthesis API地址")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 健康检查
    subparsers.add_parser("health", help="检查服务健康状态")
    
    # 初始化数据库
    subparsers.add_parser("init", help="初始化数据库")
    
    # 查看任务
    subparsers.add_parser("tasks", help="查看所有任务")
    
    # 统计信息
    subparsers.add_parser("stats", help="查看数据库统计")
    
    # 导出任务
    export_parser = subparsers.add_parser("export", help="导出任务数据")
    export_parser.add_argument("--format", default="jsonl", 
                              help="导出格式 (默认: jsonl)")
    
    # 清空数据库
    subparsers.add_parser("clear", help="清空数据库")
    
    # 生成任务
    generate_parser = subparsers.add_parser("generate", help="生成任务")
    generate_parser.add_argument("trajectory_file", 
                                help="轨迹文件路径")
    
    # 服务状态
    subparsers.add_parser("status", help="查看服务状态")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = SynthesisManager(args.url)
    
    try:
        if args.command == "health":
            manager.health_check()
        elif args.command == "init":
            manager.init_database()
        elif args.command == "tasks":
            manager.view_tasks()
        elif args.command == "stats":
            manager.get_stats()
        elif args.command == "export":
            manager.export_tasks(args.format)
        elif args.command == "clear":
            manager.clear_database()
        elif args.command == "generate":
            manager.generate_task(args.trajectory_file)
        elif args.command == "status":
            manager.status()
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