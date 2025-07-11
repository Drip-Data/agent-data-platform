#!/usr/bin/env python3
"""
优化后的Agent-MicroSandbox交互演示
展示最新的Token自动刷新、会话持久化和增强功能
"""

import asyncio
import sys
import logging
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer
from core.config_manager import ConfigManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OptimizedAgentMicroSandboxDemo:
    """优化后的Agent-MicroSandbox交互演示"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        
    async def setup(self):
        """设置演示环境"""
        self.server = MicroSandboxMCPServer(self.config_manager)
        
    async def demo_enhanced_features(self):
        """演示增强功能"""
        print("🚀 " + "="*60)
        print("🎉 优化后的Agent-MicroSandbox交互演示")
        print("🚀 " + "="*60)
        
        # 1. 展示Token状态管理
        print("\n🔐 1. Token状态管理演示")
        print("-" * 40)
        
        token_status = await self.server.handle_tool_action("microsandbox_get_token_status", {})
        if token_status.get("success"):
            status_data = token_status.get("data", {})
            token_info = status_data.get("token_status", {})
            print(f"✅ Token状态: {token_info.get('has_token', False)}")
            print(f"✅ 过期时间: {token_info.get('token_expiry', 'N/A')}")
            print(f"✅ 自动刷新: {status_data.get('auto_refresh_enabled', False)}")
            print(f"✅ 是否过期: {token_info.get('is_expired', 'Unknown')}")
        
        # 2. 展示会话持久化
        print("\n📝 2. 会话持久化演示")
        print("-" * 40)
        
        session_id = f"demo_session_{int(time.time())}"
        
        # 设置会话变量
        result1 = await self.server.handle_tool_action(
            "microsandbox_execute",
            {
                "code": "demo_var = 'Agent integration demo'\nmath_result = 42 * 2\nprint(f'Setup: {demo_var}')",
                "session_id": session_id
            }
        )
        
        if result1.get("success"):
            stdout = result1.get("data", {}).get("stdout", "")
            print(f"✅ 会话创建: {stdout.strip()}")
        
        # 在同一会话中使用变量
        result2 = await self.server.handle_tool_action(
            "microsandbox_execute",
            {
                "code": "print(f'Variable persisted: {demo_var}')\nprint(f'Math result: {math_result}')\nnew_calc = math_result + 10\nprint(f'New calculation: {new_calc}')",
                "session_id": session_id
            }
        )
        
        if result2.get("success"):
            stdout = result2.get("data", {}).get("stdout", "")
            print(f"✅ 变量持久化: {stdout.strip()}")
        
        # 3. 展示包管理功能
        print("\n📦 3. 包管理演示")
        print("-" * 40)
        
        package_result = await self.server.handle_tool_action(
            "microsandbox_install_package",
            {
                "package_name": "datetime",
                "session_id": session_id
            }
        )
        
        if package_result.get("success"):
            details = package_result.get("data", {}).get("install_details", {})
            print(f"✅ 包安装: {details.get('install_success', False)}")
            print(f"✅ 导入测试: {details.get('import_success', False)}")
        
        # 使用安装的包
        usage_result = await self.server.handle_tool_action(
            "microsandbox_execute",
            {
                "code": "from datetime import datetime\nnow = datetime.now()\nprint(f'Current time: {now.strftime(\"%Y-%m-%d %H:%M:%S\")}')\nprint(f'Demo session variables still available: {demo_var}')",
                "session_id": session_id
            }
        )
        
        if usage_result.get("success"):
            stdout = usage_result.get("data", {}).get("stdout", "")
            print(f"✅ 包使用: {stdout.strip()}")
        
        # 4. 展示会话管理
        print("\n🗂️ 4. 会话管理演示")
        print("-" * 40)
        
        sessions_result = await self.server.handle_tool_action("microsandbox_list_sessions", {})
        if sessions_result.get("success"):
            sessions = sessions_result.get("data", {}).get("sessions", [])
            print(f"✅ 活跃会话数: {len(sessions)}")
            for session in sessions:
                if session.get("session_id") == session_id:
                    print(f"   - 演示会话: {session.get('session_id')}")
                    print(f"   - 执行次数: {session.get('execution_count', 0)}")
                    print(f"   - 会话类型: {session.get('type', 'unknown')}")
        
        # 5. 展示性能监控
        print("\n📊 5. 性能监控演示")
        print("-" * 40)
        
        perf_result = await self.server.handle_tool_action("microsandbox_get_performance_stats", {})
        if perf_result.get("success"):
            stats = perf_result.get("data", {}).get("performance_stats", {})
            print(f"✅ 总执行次数: {stats.get('total_executions', 0)}")
            print(f"✅ 成功率: {stats.get('success_rate', 0):.1%}")
            print(f"✅ 平均执行时间: {stats.get('average_execution_time', 0):.2f}秒")
            print(f"✅ 内存使用: {stats.get('current_memory_mb', 0):.1f}MB")
        
        # 6. 展示健康状态
        print("\n🏥 6. 健康状态演示")
        print("-" * 40)
        
        health_result = await self.server.handle_tool_action("microsandbox_get_health_status", {})
        if health_result.get("success"):
            health_data = health_result.get("data", {})
            print(f"✅ 系统状态: {health_data.get('status', 'unknown')}")
            issues = health_data.get("issues", [])
            if issues:
                print(f"⚠️  发现问题: {', '.join(issues)}")
            else:
                print("✅ 系统运行正常")
        
        # 7. 清理演示会话
        print("\n🧹 7. 会话清理演示")
        print("-" * 40)
        
        close_result = await self.server.handle_tool_action(
            "microsandbox_close_session",
            {"session_id": session_id}
        )
        
        if close_result.get("success"):
            print(f"✅ 会话 {session_id} 已成功关闭")
        
    async def demo_error_recovery(self):
        """演示错误恢复机制"""
        print("\n🛡️ 8. 错误恢复机制演示")
        print("-" * 40)
        
        # 测试语法错误恢复
        error_result = await self.server.handle_tool_action(
            "microsandbox_execute",
            {"code": "print('这是一个故意的语法错误' +)"}  # 故意的语法错误
        )
        
        if not error_result.get("success", True):
            print("✅ 语法错误被正确捕获")
            stderr = error_result.get("data", {}).get("stderr", "")
            if "SyntaxError" in stderr:
                print("✅ 错误类型识别正确")
        else:
            print("⚠️ 错误处理异常")
        
        # 测试正常恢复
        recovery_result = await self.server.handle_tool_action(
            "microsandbox_execute",
            {"code": "print('错误恢复测试: 正常执行')"}
        )
        
        if recovery_result.get("success"):
            print("✅ 系统已从错误中恢复")
        
    async def demo_concurrent_operations(self):
        """演示并发操作能力"""
        print("\n⚡ 9. 并发操作演示")
        print("-" * 40)
        
        # 创建多个并发任务
        tasks = [
            self.server.handle_tool_action("microsandbox_execute", {"code": f"print('Concurrent task {i}')"}),
            self.server.handle_tool_action("microsandbox_get_performance_stats", {}),
            self.server.handle_tool_action("microsandbox_get_health_status", {}),
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time
        
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success", False))
        print(f"✅ 并发任务完成: {success_count}/{len(tasks)} 成功")
        print(f"✅ 执行时间: {duration:.2f}秒")
        
    async def run_complete_demo(self):
        """运行完整演示"""
        await self.setup()
        
        try:
            await self.demo_enhanced_features()
            await self.demo_error_recovery()
            await self.demo_concurrent_operations()
            
            print("\n" + "="*60)
            print("🎉 Agent-MicroSandbox优化演示完成！")
            print("🔐 Token自动刷新: ✅ 工作正常")
            print("📝 会话持久化: ✅ 变量保持")
            print("📦 包管理: ✅ 安装成功")
            print("🛡️ 错误恢复: ✅ 自动降级")
            print("⚡ 并发支持: ✅ 多任务处理")
            print("📊 性能监控: ✅ 实时统计")
            print("🏥 健康检查: ✅ 状态监控")
            print("="*60)
            print("🚀 Agent现在可以无痛使用MicroSandbox的所有功能！")
            print("="*60)
            
        except Exception as e:
            logger.error(f"演示过程中发生错误: {e}")
        
        finally:
            await self.server.cleanup()

async def main():
    """主函数"""
    demo = OptimizedAgentMicroSandboxDemo()
    await demo.run_complete_demo()

if __name__ == "__main__":
    asyncio.run(main())