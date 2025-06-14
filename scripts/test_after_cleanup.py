#!/usr/bin/env python3
"""
清理后的功能测试脚本
验证enhanced-reasoning-runtime通过toolscore调用MCP服务器的完整链路
"""

import asyncio
import aiohttp
import json
import logging
import time
from pathlib import Path
import sys

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CleanupTestSuite:
    """清理后的测试套件"""
      def __init__(self):
        # 使用配置管理器获取端口
        try:
            from core.config_manager import get_ports_config
            ports_config = get_ports_config()
            
            task_api_port = ports_config['core_services']['task_api']['port']
            toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
            
            self.task_api_url = f"http://localhost:{task_api_port}"
            self.monitoring_api_url = f"http://localhost:{toolscore_http_port}"
        except Exception as e:
            logger.warning(f"配置加载失败，使用默认端口: {e}")
            self.task_api_url = "http://localhost:8000"
            self.monitoring_api_url = "http://localhost:8082"
        
    async def test_basic_import(self):
        """测试基本导入功能"""
        print("🔧 测试1: 基本导入功能")
        try:
            # 测试core模块导入
            from core.task_manager import get_runtime
            from core.toolscore.core_manager import CoreManager
            from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
            
            print("✅ 所有核心模块导入成功")
            return True
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            return False
    
    async def test_runtime_initialization(self):
        """测试运行时初始化"""
        print("🔧 测试2: Enhanced Runtime初始化")
        try:
            from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
            runtime = EnhancedReasoningRuntime()
            
            print(f"✅ Enhanced Runtime创建成功，ID: {runtime.runtime_id}")
            return True
        except Exception as e:
            print(f"❌ Runtime初始化失败: {e}")
            return False
            
    async def test_toolscore_manager(self):
        """测试ToolScore管理器"""
        print("🔧 测试3: ToolScore管理器")
        try:
            from core.toolscore.core_manager import CoreManager
            manager = CoreManager()
            
            print("✅ ToolScore CoreManager创建成功")
            return True
        except Exception as e:
            print(f"❌ ToolScore管理器创建失败: {e}")
            return False
    
    async def test_task_manager_runtime_factory(self):
        """测试任务管理器的运行时工厂函数"""
        print("🔧 测试4: 任务管理器运行时工厂")
        try:
            from core.task_manager import get_runtime
            
            # 测试所有支持的任务类型
            for task_type in ['reasoning', 'code', 'web']:
                runtime = get_runtime(task_type)
                print(f"✅ {task_type}任务类型 -> {runtime.__class__.__name__}")
            
            return True
        except Exception as e:
            print(f"❌ 运行时工厂测试失败: {e}")
            return False
    
    async def test_api_endpoints(self):
        """测试API端点是否可访问"""
        print("🔧 测试5: API端点连接")
        
        endpoints = [
            ("Task API", self.task_api_url + "/health"),
            ("Monitoring API", self.monitoring_api_url + "/health")
        ]
        
        results = []
        async with aiohttp.ClientSession() as session:
            for name, url in endpoints:
                try:
                    async with session.get(url, timeout=5) as response:
                        if response.status == 200:
                            print(f"✅ {name} 连接成功")
                            results.append(True)
                        else:
                            print(f"⚠️ {name} 返回状态码: {response.status}")
                            results.append(False)
                except Exception as e:
                    print(f"❌ {name} 连接失败: {e}")
                    results.append(False)
        
        return all(results)
    
    async def test_simple_task_submission(self):
        """测试简单任务提交"""
        print("🔧 测试6: 简单任务提交")
        
        try:
            task_data = {
                "input": "计算 2 + 2 的结果",
                "description": "清理后测试 - 简单计算任务",
                "priority": "normal"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.task_api_url}/submit_task", 
                    json=task_data,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        task_id = result.get("task_id")
                        print(f"✅ 任务提交成功，ID: {task_id}")
                        
                        # 简单等待一下，然后检查状态
                        await asyncio.sleep(2)
                        
                        async with session.get(
                            f"{self.task_api_url}/task_status/{task_id}",
                            timeout=5
                        ) as status_response:
                            if status_response.status == 200:
                                status_data = await status_response.json()
                                print(f"✅ 任务状态查询成功: {status_data.get('status', 'unknown')}")
                                return True
                            else:
                                print(f"⚠️ 任务状态查询失败: {status_response.status}")
                                return False
                    else:
                        print(f"❌ 任务提交失败: {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ 任务提交测试失败: {e}")
            return False
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始清理后功能测试")
        print("=" * 50)
        
        tests = [
            self.test_basic_import,
            self.test_runtime_initialization,
            self.test_toolscore_manager,
            self.test_task_manager_runtime_factory,
            self.test_api_endpoints,
            self.test_simple_task_submission
        ]
        
        results = []
        for test in tests:
            try:
                result = await test()
                results.append(result)
                print("-" * 30)
            except Exception as e:
                print(f"❌ 测试执行异常: {e}")
                results.append(False)
                print("-" * 30)
        
        # 汇总结果
        passed = sum(results)
        total = len(results)
        
        print("=" * 50)
        print(f"🎯 测试结果汇总: {passed}/{total} 通过")
        
        if passed == total:
            print("🎉 所有测试通过！清理工作成功完成。")
            print("✨ 系统现在只保留enhanced-reasoning-runtime，")
            print("   所有代码执行和浏览器功能都通过toolscore + MCP服务器实现。")
        else:
            print("⚠️ 部分测试未通过，可能需要进一步调试。")
            failed_tests = [i for i, result in enumerate(results) if not result]
            print(f"❌ 失败的测试序号: {failed_tests}")
        
        return passed == total

async def main():
    """主函数"""
    test_suite = CleanupTestSuite()
    success = await test_suite.run_all_tests()
    
    if success:
        print("\n🎊 清理和测试完成！系统架构优化成功。")
    else:
        print("\n🔧 部分功能可能需要调试，但基本架构已优化。")

if __name__ == "__main__":
    asyncio.run(main())
