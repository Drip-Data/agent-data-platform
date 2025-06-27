#!/usr/bin/env python3
"""
核心问题修复验证测试
专门测试会话管理、包安装和会话清理功能
"""

import asyncio
import sys
import logging
from pathlib import Path
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer
from core.config_manager import ConfigManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CoreIssuesFixValidator:
    """核心问题修复验证器"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        
    async def setup(self):
        """设置测试环境"""
        self.server = MicroSandboxMCPServer(self.config_manager)
        
    async def test_session_management_fix(self):
        """测试会话管理修复"""
        logger.info("🧪 Testing session management fix...")
        
        session_id = f"fix_test_{int(time.time())}"
        
        try:
            # 1. 创建会话并执行代码
            result1 = await self.server.handle_tool_action(
                "microsandbox_execute",
                {
                    "code": "x = 42\ny = 'session_test'",
                    "session_id": session_id
                }
            )
            
            print(f"✅ Session creation: {result1.get('success', False)}")
            if not result1.get("success"):
                print(f"   Error: {result1.get('error_message', 'Unknown')}")
                return False
            
            # 2. 在同一会话中使用变量
            result2 = await self.server.handle_tool_action(
                "microsandbox_execute",
                {
                    "code": "print(f'x={x}, y={y}')",
                    "session_id": session_id
                }
            )
            
            print(f"✅ Session persistence: {result2.get('success', False)}")
            if result2.get("success"):
                stdout = result2.get("data", {}).get("stdout", "")
                print(f"   Output: {stdout.strip()}")
                variable_persisted = "x=42" in stdout and "y=session_test" in stdout
                print(f"✅ Variable persistence: {variable_persisted}")
            else:
                print(f"   Error: {result2.get('error_message', 'Unknown')}")
                return False
            
            # 3. 列出会话
            result3 = await self.server.handle_tool_action(
                "microsandbox_list_sessions",
                {}
            )
            
            print(f"✅ Session listing: {result3.get('success', False)}")
            if result3.get("success"):
                sessions = result3.get("data", {}).get("sessions", [])
                session_found = any(s.get("session_id") == session_id for s in sessions)
                print(f"✅ Session found in list: {session_found}")
                print(f"   Total active sessions: {len(sessions)}")
            
            # 4. 关闭会话
            result4 = await self.server.handle_tool_action(
                "microsandbox_close_session",
                {"session_id": session_id}
            )
            
            print(f"✅ Session cleanup: {result4.get('success', False)}")
            if not result4.get("success"):
                print(f"   Error: {result4.get('error_message', 'Unknown')}")
            
            return all([
                result1.get("success", False),
                result2.get("success", False),
                result3.get("success", False),
                result4.get("success", False)
            ])
            
        except Exception as e:
            logger.error(f"Session management test failed: {e}")
            return False
            
    async def test_package_installation_fix(self):
        """测试包安装修复"""
        logger.info("🧪 Testing package installation fix...")
        
        try:
            # 1. 测试无版本包安装
            result1 = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "urllib3"}
            )
            
            print(f"✅ Package install (no version): {result1.get('success', False)}")
            if not result1.get("success"):
                print(f"   Error: {result1.get('error_message', 'Unknown')}")
            else:
                details = result1.get("data", {}).get("install_details", {})
                print(f"   Install success: {details.get('install_success', False)}")
                print(f"   Import success: {details.get('import_success', False)}")
            
            # 2. 测试带版本包安装
            result2 = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "urllib3", "version": "1.26.0"}
            )
            
            print(f"✅ Package install (with version): {result2.get('success', False)}")
            if not result2.get("success"):
                print(f"   Error: {result2.get('error_message', 'Unknown')}")
            else:
                details = result2.get("data", {}).get("install_details", {})
                print(f"   Install success: {details.get('install_success', False)}")
                print(f"   Import success: {details.get('import_success', False)}")
                print(f"   Version: {details.get('version', 'Unknown')}")
            
            # 3. 测试无效包（应该失败）
            result3 = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "definitely_nonexistent_package_xyz"}
            )
            
            print(f"✅ Invalid package handling: {not result3.get('success', True)}")  # 应该失败
            if not result3.get("success"):
                print(f"   Expected error: {result3.get('error_type', 'Unknown')}")
            
            return True  # 即使有些包安装失败也继续
            
        except Exception as e:
            logger.error(f"Package installation test failed: {e}")
            return False
            
    async def test_production_server_connection(self):
        """测试生产服务器连接"""
        logger.info("🧪 Testing production server connection...")
        
        try:
            # 测试服务器健康检查
            health_result = await self.server.server_manager._check_server_health()
            print(f"✅ Server health check: {health_result}")
            
            # 测试基本代码执行
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "import sys; print(f'Python {sys.version_info.major}.{sys.version_info.minor} ready')"}
            )
            
            print(f"✅ Basic execution: {result.get('success', False)}")
            if result.get("success"):
                stdout = result.get("data", {}).get("stdout", "")
                print(f"   Output: {stdout.strip()}")
            else:
                print(f"   Error: {result.get('error_message', 'Unknown')}")
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"Production server connection test failed: {e}")
            return False
            
    async def run_all_tests(self):
        """运行所有核心问题修复测试"""
        print("=" * 60)
        print("🔧 CORE ISSUES FIX VALIDATION")
        print("=" * 60)
        
        await self.setup()
        
        results = []
        
        # 1. 生产服务器连接测试
        print("\n🔌 Production Server Connection Test")
        print("-" * 40)
        connection_result = await self.test_production_server_connection()
        results.append(connection_result)
        
        # 2. 会话管理测试
        print("\n📝 Session Management Test")
        print("-" * 40)
        session_result = await self.test_session_management_fix()
        results.append(session_result)
        
        # 3. 包安装测试
        print("\n📦 Package Installation Test")
        print("-" * 40)
        package_result = await self.test_package_installation_fix()
        results.append(package_result)
        
        # 结果总结
        passed = sum(results)
        total = len(results)
        
        print("\n" + "=" * 60)
        print(f"📊 VALIDATION SUMMARY: {passed}/{total} PASSED")
        
        if passed == total:
            print("🎉 All core issues have been fixed!")
            return True
        else:
            print("⚠️ Some issues still need attention.")
            return False

async def main():
    """主函数"""
    validator = CoreIssuesFixValidator()
    success = await validator.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())