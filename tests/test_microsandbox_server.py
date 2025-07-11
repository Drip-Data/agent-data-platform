#!/usr/bin/env python3
"""
Comprehensive test suite for MicroSandbox Server
Tests all microsandbox actions and agent interactions
"""

import asyncio
import pytest
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os
from datetime import datetime
import uuid

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer, PerformanceMonitor
from core.config_manager import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MicroSandboxServerTester:
    """Comprehensive MicroSandbox Server Tester"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        self.test_results = []
        self.start_time = None
        
    async def setup_test_environment(self):
        """Set up test environment"""
        logger.info("🔧 Setting up MicroSandbox test environment...")
        
        # Initialize the microsandbox server
        self.server = MicroSandboxMCPServer(self.config_manager)
        
        # Set test-specific timeouts
        self.server.default_execution_timeout = 10  # Shorter for tests
        self.server.session_timeout = 300  # 5 minutes for tests
        
        logger.info("✅ MicroSandbox test environment setup complete")
        
    async def cleanup_test_environment(self):
        """Clean up test environment"""
        logger.info("🧹 Cleaning up MicroSandbox test environment...")
        
        if self.server:
            await self.server.cleanup()
            
        logger.info("✅ MicroSandbox test environment cleanup complete")
        
    def log_test_result(self, test_name: str, action: str, success: bool, 
                       duration: float, result: Dict[str, Any] = None, 
                       error: str = None):
        """Log test result"""
        self.test_results.append({
            'test_name': test_name,
            'action': action,
            'success': success,
            'duration': duration,
            'result': result,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} - {action} ({duration:.2f}s)")
        if error:
            logger.error(f"    Error: {error}")
            
    async def test_basic_code_execution(self):
        """Test basic code execution functionality"""
        logger.info("🧪 Testing basic code execution...")
        
        # Test 1: Simple Python execution
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "print('Hello from MicroSandbox!')"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            # Check if output contains expected text
            if success:
                stdout = result.get("data", {}).get("stdout", "")
                success = "Hello from MicroSandbox!" in stdout
            
            self.log_test_result("Basic Execution", "simple_print", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Basic Execution", "simple_print", False, duration, error=str(e))
            
        # Test 2: Mathematical calculation
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "import math\nresult = math.sqrt(16)\nprint(f'Result: {result}')"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            if success:
                stdout = result.get("data", {}).get("stdout", "")
                success = "4.0" in stdout or "4" in stdout
                
            self.log_test_result("Basic Execution", "math_calculation", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Basic Execution", "math_calculation", False, duration, error=str(e))
            
        # Test 3: Error handling
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "undefined_variable + 1"}
            )
            duration = time.time() - start_time
            
            # This should fail, but the server should handle it gracefully
            stderr = result.get("data", {}).get("stderr", "")
            success = "NameError" in stderr or not result.get("success", True)
            
            self.log_test_result("Basic Execution", "error_handling", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Basic Execution", "error_handling", False, duration, error=str(e))
            
    async def test_session_management(self):
        """Test session management functionality"""
        logger.info("🧪 Testing session management...")
        
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        
        # Test 1: Create session and execute code
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {
                    "code": "x = 42\ny = 'hello'",
                    "session_id": session_id
                }
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Session Management", "create_session", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Session Management", "create_session", False, duration, error=str(e))
            
        # Test 2: Use variables from previous execution
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {
                    "code": "print(f'x = {x}, y = {y}')",
                    "session_id": session_id
                }
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            if success:
                stdout = result.get("data", {}).get("stdout", "")
                success = "x = 42" in stdout and "y = hello" in stdout
                
            self.log_test_result("Session Management", "session_persistence", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Session Management", "session_persistence", False, duration, error=str(e))
            
        # Test 3: List active sessions
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_list_sessions",
                {}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            if success:
                sessions = result.get("data", {}).get("sessions", [])
                session_ids = [s.get("session_id") for s in sessions]
                success = session_id in session_ids
                
            self.log_test_result("Session Management", "list_sessions", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Session Management", "list_sessions", False, duration, error=str(e))
            
        # Test 4: Close session
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_close_session",
                {"session_id": session_id}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Session Management", "close_session", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Session Management", "close_session", False, duration, error=str(e))
            
    async def test_package_installation(self):
        """Test package installation functionality"""
        logger.info("🧪 Testing package installation...")
        
        # Test 1: Install a simple package
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "requests"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Package Installation", "install_requests", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Package Installation", "install_requests", False, duration, error=str(e))
            
        # Test 2: Install package with version
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "urllib3", "version": "1.26.0"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Package Installation", "install_with_version", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Package Installation", "install_with_version", False, duration, error=str(e))
            
        # Test 3: Try to install invalid package
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "non_existent_package_xyz123"}
            )
            duration = time.time() - start_time
            # Should fail but handle gracefully
            success = not result.get("success", True)
            self.log_test_result("Package Installation", "invalid_package", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Package Installation", "invalid_package", False, duration, error=str(e))
            
    async def test_performance_monitoring(self):
        """Test performance monitoring functionality"""
        logger.info("🧪 Testing performance monitoring...")
        
        # Test 1: Get performance stats
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_get_performance_stats",
                {}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            if success:
                stats = result.get("data", {}).get("performance_stats", {})
                required_fields = ["uptime_seconds", "total_executions", "success_rate", "current_memory_mb"]
                success = all(field in stats for field in required_fields)
                
            self.log_test_result("Performance Monitoring", "get_stats", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Performance Monitoring", "get_stats", False, duration, error=str(e))
            
        # Test 2: Get health status
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_get_health_status",
                {}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            if success:
                data = result.get("data", {})
                required_fields = ["status", "metrics", "recommendations"]
                success = all(field in data for field in required_fields)
                
            self.log_test_result("Performance Monitoring", "health_status", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Performance Monitoring", "health_status", False, duration, error=str(e))
            
    async def test_timeout_handling(self):
        """Test timeout handling"""
        logger.info("🧪 Testing timeout handling...")
        
        # Test 1: Long running code (should timeout or complete)
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {
                    "code": "import time\ntime.sleep(2)\nprint('Completed')",
                    "timeout": 5
                }
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            
            # Should either complete successfully or timeout gracefully
            if not success:
                error_msg = result.get("error_message", "")
                success = "timeout" in error_msg.lower()
                
            self.log_test_result("Timeout Handling", "long_running_code", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Timeout Handling", "long_running_code", False, duration, error=str(e))
            
    async def test_parameter_validation(self):
        """Test parameter validation and error handling"""
        logger.info("🧪 Testing parameter validation...")
        
        # Test 1: Missing required parameter
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {}  # Missing required code parameter
            )
            duration = time.time() - start_time
            # Should fail with proper error message
            success = not result.get("success", True) and "代码不能为空" in result.get("error_message", "")
            self.log_test_result("Parameter Validation", "missing_code", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "missing_code", False, duration, error=str(e))
            
        # Test 2: Empty code
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": ""}
            )
            duration = time.time() - start_time
            # Should fail with proper error message
            success = not result.get("success", True)
            self.log_test_result("Parameter Validation", "empty_code", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "empty_code", False, duration, error=str(e))
            
        # Test 3: Invalid package name
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "invalid@package!name"}
            )
            duration = time.time() - start_time
            # Should fail with validation error
            success = not result.get("success", True) and "包名格式无效" in result.get("error_message", "")
            self.log_test_result("Parameter Validation", "invalid_package_name", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "invalid_package_name", False, duration, error=str(e))
            
        # Test 4: Invalid session ID for close
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_close_session",
                {"session_id": "non_existent_session"}
            )
            duration = time.time() - start_time
            # Should fail with session not found error
            success = not result.get("success", True) and "会话不存在" in result.get("error_message", "")
            self.log_test_result("Parameter Validation", "invalid_session_id", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "invalid_session_id", False, duration, error=str(e))
            
        # Test 5: Unsupported action
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_invalid_action",
                {}
            )
            duration = time.time() - start_time
            # Should fail with unsupported action error
            success = not result.get("success", True) and "Unsupported action" in result.get("error_message", "")
            self.log_test_result("Parameter Validation", "unsupported_action", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "unsupported_action", False, duration, error=str(e))
            
    async def test_session_cleanup(self):
        """Test session cleanup functionality"""
        logger.info("🧪 Testing session cleanup...")
        
        # Create a test session
        session_id = f"cleanup_test_{uuid.uuid4().hex[:8]}"
        
        # Test 1: Create session
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {
                    "code": "test_var = 'cleanup_test'",
                    "session_id": session_id
                }
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Session Cleanup", "create_test_session", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Session Cleanup", "create_test_session", False, duration, error=str(e))
            
        # Test 2: Cleanup expired sessions
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "microsandbox_cleanup_expired",
                {"max_age": 1}  # Very short age to test cleanup
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Session Cleanup", "cleanup_expired", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Session Cleanup", "cleanup_expired", False, duration, error=str(e))
            
    async def test_fallback_execution(self):
        """Test fallback execution when MicroSandbox is not available"""
        logger.info("🧪 Testing fallback execution...")
        
        # Mock MicroSandbox to simulate failure
        with patch('mcp_servers.microsandbox_server.main.PythonSandbox') as mock_sandbox:
            mock_sandbox.create.side_effect = Exception("MicroSandbox not available")
            
            start_time = time.time()
            try:
                result = await self.server.handle_tool_action(
                    "microsandbox_execute",
                    {"code": "print('Fallback test')"}
                )
                duration = time.time() - start_time
                success = result.get("success", False)
                
                # Should fall back to local executor
                if success:
                    stdout = result.get("data", {}).get("stdout", "")
                    success = "Fallback test" in stdout
                    
                self.log_test_result("Fallback Execution", "local_fallback", success, duration, result)
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result("Fallback Execution", "local_fallback", False, duration, error=str(e))
                
    async def test_concurrent_execution(self):
        """Test concurrent code execution"""
        logger.info("🧪 Testing concurrent execution...")
        
        start_time = time.time()
        try:
            # Execute multiple codes concurrently
            tasks = [
                self.server.handle_tool_action(
                    "microsandbox_execute",
                    {"code": f"import time\ntime.sleep(0.1)\nprint('Task {i}')"}
                ) for i in range(3)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start_time
            
            # Check that all executions completed
            successful_results = 0
            for result in results:
                if isinstance(result, dict) and result.get("success", False):
                    successful_results += 1
                    
            success = successful_results >= 2  # At least 2 should succeed
            
            self.log_test_result("Concurrent Execution", "multiple_tasks", success, duration, {
                "total_tasks": len(tasks),
                "successful": successful_results
            })
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Concurrent Execution", "multiple_tasks", False, duration, error=str(e))
            
    async def test_performance_monitor_integration(self):
        """Test PerformanceMonitor class integration"""
        logger.info("🧪 Testing PerformanceMonitor integration...")
        
        start_time = time.time()
        try:
            # Access the performance monitor
            monitor = self.server.performance_monitor
            
            # Record some test metrics
            monitor.record_execution(1.5, True, 2)
            monitor.record_execution(0.8, False, 2, "TestError")
            
            # Get statistics
            stats = monitor.get_statistics()
            
            duration = time.time() - start_time
            
            # Validate statistics structure
            required_fields = ["uptime_seconds", "total_executions", "success_rate", "current_memory_mb"]
            success = all(field in stats for field in required_fields)
            
            if success:
                success = stats["total_executions"] >= 2
                
            self.log_test_result("Performance Monitor", "integration_test", success, duration, stats)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Performance Monitor", "integration_test", False, duration, error=str(e))
            
    async def run_all_tests(self):
        """Run all tests"""
        logger.info("🚀 Starting comprehensive MicroSandbox Server tests...")
        self.start_time = time.time()
        
        try:
            # Setup environment
            await self.setup_test_environment()
            
            # Run all test suites
            await self.test_basic_code_execution()
            await self.test_session_management()
            await self.test_package_installation()
            await self.test_performance_monitoring()
            await self.test_timeout_handling()
            await self.test_parameter_validation()
            await self.test_session_cleanup()
            await self.test_fallback_execution()
            await self.test_concurrent_execution()
            await self.test_performance_monitor_integration()
            
        finally:
            # Always cleanup
            await self.cleanup_test_environment()
            
        # Generate test report
        self.generate_test_report()
        
    def generate_test_report(self):
        """Generate comprehensive test report"""
        total_time = time.time() - self.start_time if self.start_time else 0
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print("\n" + "="*80)
        print("🧪 MICROSANDBOX SERVER TEST REPORT")
        print("="*80)
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"❌ Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        print(f"⏱️  Total Time: {total_time:.2f}s")
        print()
        
        # Group results by test category
        test_groups = {}
        for result in self.test_results:
            group = result['test_name']
            if group not in test_groups:
                test_groups[group] = []
            test_groups[group].append(result)
            
        # Print detailed results by category
        for group_name, group_results in test_groups.items():
            group_passed = sum(1 for r in group_results if r['success'])
            group_total = len(group_results)
            print(f"📋 {group_name}: {group_passed}/{group_total} passed")
            
            for result in group_results:
                status = "✅" if result['success'] else "❌"
                print(f"  {status} {result['action']} ({result['duration']:.2f}s)")
                if not result['success'] and result['error']:
                    print(f"      Error: {result['error']}")
                    
        # Save detailed results to file
        results_file = project_root / "test_results_microsandbox_server.json"
        with open(results_file, 'w') as f:
            json.dump({
                'test_summary': {
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'success_rate': passed_tests/total_tests*100,
                    'total_time': total_time
                },
                'detailed_results': self.test_results
            }, f, indent=2)
            
        print(f"\n📁 Detailed results saved to: {results_file}")
        print("="*80)
        
        return passed_tests == total_tests


# Test fixtures and pytest integration
@pytest.fixture
async def microsandbox_tester():
    """Pytest fixture for microsandbox tester"""
    tester = MicroSandboxServerTester()
    yield tester
    

@pytest.mark.asyncio
async def test_microsandbox_comprehensive():
    """Comprehensive test runner for pytest"""
    tester = MicroSandboxServerTester()
    success = await tester.run_all_tests()
    assert success, "Some microsandbox server tests failed"


# Standalone execution
async def main():
    """Main function for standalone execution"""
    tester = MicroSandboxServerTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    # Run tests standalone
    asyncio.run(main())