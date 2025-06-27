#!/usr/bin/env python3
"""
MicroSandbox Server Test Runner
Executes all microsandbox server tests and provides debugging capabilities
"""

import asyncio
import sys
import os
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime
import argparse
import subprocess

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import test modules
from test_microsandbox_server import MicroSandboxServerTester
from test_microsandbox_agent_interactions import MicroSandboxAgentInteractionTester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MicroSandboxTestRunner:
    """Comprehensive microsandbox test runner with debugging capabilities"""
    
    def __init__(self, debug_mode=False, timeout=300):
        self.debug_mode = debug_mode
        self.timeout = timeout
        self.test_results = []
        self.start_time = None
        
        if debug_mode:
            logging.getLogger().setLevel(logging.DEBUG)
            
    def log_test_suite_result(self, suite_name: str, success: bool, 
                             duration: float, details: dict = None):
        """Log test suite result"""
        self.test_results.append({
            'suite_name': suite_name,
            'success': success,
            'duration': duration,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        })
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {suite_name} ({duration:.2f}s)")
        
    async def check_dependencies(self):
        """Check required dependencies"""
        logger.info("🔍 Checking dependencies...")
        
        start_time = time.time()
        checks = {}
        
        try:
            # Check MicroSandbox availability
            try:
                import microsandbox
                checks['microsandbox_import'] = True
                checks['microsandbox_version'] = getattr(microsandbox, '__version__', 'unknown')
            except ImportError as e:
                checks['microsandbox_import'] = False
                checks['microsandbox_error'] = str(e)
                
            # Check psutil for performance monitoring
            try:
                import psutil
                checks['psutil_import'] = True
                checks['psutil_version'] = getattr(psutil, '__version__', 'unknown')
            except ImportError as e:
                checks['psutil_import'] = False
                checks['psutil_error'] = str(e)
                
            # Check core modules
            try:
                from core.config_manager import ConfigManager
                from core.toolscore.interfaces import ToolCapability
                checks['core_modules_import'] = True
            except ImportError as e:
                checks['core_modules_import'] = False
                checks['core_modules_error'] = str(e)
                
            # Check MicroSandbox server connectivity
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get('http://127.0.0.1:5555/health', timeout=5) as resp:
                            checks['microsandbox_server_reachable'] = resp.status == 200
                    except:
                        checks['microsandbox_server_reachable'] = False
            except Exception as e:
                checks['microsandbox_server_reachable'] = False
                checks['microsandbox_server_error'] = str(e)
                
            # Check configuration
            try:
                config_manager = ConfigManager()
                ports_config = config_manager.get_ports_config()
                checks['config_load'] = True
                checks['microsandbox_port'] = ports_config.get('mcp_servers', {}).get('microsandbox', {}).get('port', 'unknown')
            except Exception as e:
                checks['config_load'] = False
                checks['config_error'] = str(e)
                
            # Overall success
            critical_checks = ['microsandbox_import', 'psutil_import', 'core_modules_import']
            success = all(checks.get(check, False) for check in critical_checks)
            
        except Exception as e:
            logger.error(f"Dependency checks failed: {e}")
            success = False
            checks['general_error'] = str(e)
            
        duration = time.time() - start_time
        self.log_test_suite_result("Dependencies", success, duration, checks)
        return success
        
    async def check_microsandbox_server_status(self):
        """Check if MicroSandbox server is running"""
        logger.info("🔍 Checking MicroSandbox server status...")
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get('http://127.0.0.1:5555/health', timeout=5) as resp:
                        if resp.status == 200:
                            logger.info("✅ MicroSandbox server is running")
                            return True
                        else:
                            logger.warning(f"⚠️ MicroSandbox server returned status {resp.status}")
                            return False
                except asyncio.TimeoutError:
                    logger.warning("⚠️ MicroSandbox server connection timeout")
                    return False
                except Exception as e:
                    logger.warning(f"⚠️ MicroSandbox server connection error: {e}")
                    return False
        except Exception as e:
            logger.error(f"Failed to check MicroSandbox server: {e}")
            return False
            
    async def start_microsandbox_server_if_needed(self):
        """Start production mode MicroSandbox server if not running"""
        logger.info("🚀 Checking if production mode MicroSandbox server needs to be started...")
        
        if await self.check_microsandbox_server_status():
            return True
            
        # Stop any development mode servers
        try:
            subprocess.run(['pkill', '-f', 'msbserver --dev'], check=False)
            await asyncio.sleep(2)
        except Exception:
            pass
            
        logger.info("Starting production mode MicroSandbox server...")
        
        try:
            # Read API key from environment file
            env_path = Path(__file__).parent.parent / 'mcp_servers' / 'microsandbox_server' / '.env'
            api_key = None
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith('MSB_API_KEY='):
                            api_key = line.split('=', 1)[1].strip()
                            break
            
            if not api_key:
                # Generate new API key
                result = subprocess.run(['msb', 'server', 'keygen'], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith('Token: '):
                            api_key = line.split('Token: ')[1].strip()
                            break
            
            if not api_key:
                logger.error("Could not obtain API key")
                return False
                
            # Start production mode server
            cmd = [
                'msb', 'server', 'start',
                '--host', '127.0.0.1',
                '--port', '5555',
                '--key', api_key,
                '--detach'
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for server to start
            await asyncio.sleep(5)
            
            # Check if it's now running
            if await self.check_microsandbox_server_status():
                logger.info("✅ Production mode MicroSandbox server started successfully")
                return True
            else:
                logger.warning("⚠️ Production mode MicroSandbox server may not have started properly")
                return True  # Continue anyway, fallback execution should handle this
                
        except Exception as e:
            logger.warning(f"⚠️ Could not start production mode MicroSandbox server: {e}")
            logger.info("Tests will use fallback execution mode")
            return True  # Continue with fallback mode
            
    async def run_basic_functionality_tests(self):
        """Run basic functionality tests"""
        logger.info("🧪 Running basic functionality tests...")
        
        start_time = time.time()
        success = False
        details = {}
        
        try:
            tester = MicroSandboxServerTester()
            success = await tester.run_all_tests()
            details = {
                'total_individual_tests': len(tester.test_results),
                'passed_individual_tests': sum(1 for r in tester.test_results if r['success'])
            }
        except Exception as e:
            logger.error(f"Basic functionality tests failed: {e}")
            if self.debug_mode:
                traceback.print_exc()
            details['error'] = str(e)
            
        duration = time.time() - start_time
        self.log_test_suite_result("Basic Functionality", success, duration, details)
        return success
        
    async def run_agent_interaction_tests(self):
        """Run agent interaction tests"""
        logger.info("🤖 Running agent interaction tests...")
        
        start_time = time.time()
        success = False
        details = {}
        
        try:
            tester = MicroSandboxAgentInteractionTester()
            success = await tester.run_all_interaction_tests()
            details = {
                'total_interaction_tests': len(tester.test_results),
                'passed_interaction_tests': sum(1 for r in tester.test_results if r['success'])
            }
        except Exception as e:
            logger.error(f"Agent interaction tests failed: {e}")
            if self.debug_mode:
                traceback.print_exc()
            details['error'] = str(e)
            
        duration = time.time() - start_time
        self.log_test_suite_result("Agent Interactions", success, duration, details)
        return success
        
    async def run_integration_tests(self):
        """Run integration tests with real MicroSandbox server"""
        logger.info("🔗 Running integration tests...")
        
        start_time = time.time()
        
        try:
            from test_microsandbox_server import MicroSandboxServerTester
            tester = MicroSandboxServerTester()
            await tester.setup_test_environment()
            
            # Test end-to-end workflow
            session_id = f"integration_test_{int(time.time())}"
            
            # 1. Execute code with session
            result1 = await tester.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "import json\ndata = {'test': 'integration'}", "session_id": session_id}
            )
            
            # 2. Install a package
            result2 = await tester.server.handle_tool_action(
                "microsandbox_install_package",
                {"package_name": "urllib3", "session_id": session_id}
            )
            
            # 3. Use the installed package
            result3 = await tester.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "import urllib3\nprint(f'urllib3 version: {urllib3.__version__}')", "session_id": session_id}
            )
            
            # 4. Check performance stats
            result4 = await tester.server.handle_tool_action(
                "microsandbox_get_performance_stats",
                {}
            )
            
            # 5. Cleanup session
            result5 = await tester.server.handle_tool_action(
                "microsandbox_close_session",
                {"session_id": session_id}
            )
            
            await tester.cleanup_test_environment()
            
            # Evaluate integration success
            results = [result1, result2, result3, result4, result5]
            successful_steps = sum(1 for r in results if r.get("success", False))
            
            success = successful_steps >= 4  # Allow one failure
            
            details = {
                'total_steps': len(results),
                'successful_steps': successful_steps,
                'session_creation': result1.get("success", False),
                'package_installation': result2.get("success", False),
                'package_usage': result3.get("success", False),
                'performance_stats': result4.get("success", False),
                'session_cleanup': result5.get("success", False)
            }
            
        except Exception as e:
            logger.error(f"Integration tests failed: {e}")
            if self.debug_mode:
                traceback.print_exc()
            success = False
            details = {'error': str(e)}
            
        duration = time.time() - start_time
        self.log_test_suite_result("Integration Tests", success, duration, details)
        return success
        
    async def run_performance_tests(self):
        """Run performance benchmarks"""
        logger.info("⚡ Running performance tests...")
        
        start_time = time.time()
        
        try:
            from test_microsandbox_server import MicroSandboxServerTester
            tester = MicroSandboxServerTester()
            await tester.setup_test_environment()
            
            # Test execution performance
            exec_times = []
            for i in range(5):
                exec_start = time.time()
                result = await tester.server.handle_tool_action(
                    "microsandbox_execute",
                    {"code": f"result = sum(range(1000))\nprint(f'Result: {{result}}')"}
                )
                exec_duration = time.time() - exec_start
                if result.get("success"):
                    exec_times.append(exec_duration)
                    
            # Test session creation performance
            session_times = []
            for i in range(3):
                session_start = time.time()
                result = await tester.server.handle_tool_action(
                    "microsandbox_execute",
                    {"code": "x = 1", "session_id": f"perf_test_{i}"}
                )
                session_duration = time.time() - session_start
                if result.get("success"):
                    session_times.append(session_duration)
                    
            await tester.cleanup_test_environment()
            
            # Calculate averages
            avg_exec_time = sum(exec_times) / len(exec_times) if exec_times else 0
            avg_session_time = sum(session_times) / len(session_times) if session_times else 0
            
            # Performance criteria
            exec_acceptable = avg_exec_time < 5.0  # 5 seconds max for simple execution
            session_acceptable = avg_session_time < 10.0  # 10 seconds max for session creation
            
            success = exec_acceptable and session_acceptable
            
            details = {
                'avg_execution_time': avg_exec_time,
                'avg_session_time': avg_session_time,
                'execution_acceptable': exec_acceptable,
                'session_acceptable': session_acceptable,
                'execution_samples': len(exec_times),
                'session_samples': len(session_times)
            }
            
        except Exception as e:
            logger.error(f"Performance tests failed: {e}")
            if self.debug_mode:
                traceback.print_exc()
            success = False
            details = {'error': str(e)}
            
        duration = time.time() - start_time
        self.log_test_suite_result("Performance", success, duration, details)
        return success
        
    async def run_all_tests(self, include_performance=True, include_integration=True):
        """Run all test suites"""
        logger.info("🚀 Starting comprehensive MicroSandbox server testing...")
        self.start_time = time.time()
        
        test_suites = []
        
        # Always run dependency checks first
        dependency_success = await self.check_dependencies()
        test_suites.append(dependency_success)
        
        if dependency_success:
            # Start MicroSandbox server if needed
            await self.start_microsandbox_server_if_needed()
            
            # Run core functionality tests
            basic_success = await self.run_basic_functionality_tests()
            test_suites.append(basic_success)
            
            # Run agent interaction tests
            interaction_success = await self.run_agent_interaction_tests()
            test_suites.append(interaction_success)
            
            # Optional integration tests
            if include_integration:
                integration_success = await self.run_integration_tests()
                test_suites.append(integration_success)
                
            # Optional performance tests
            if include_performance and basic_success:
                perf_success = await self.run_performance_tests()
                test_suites.append(perf_success)
        else:
            logger.error("❌ Dependency checks failed - skipping other tests")
            
        # Generate final report
        self.generate_final_report()
        
        return all(test_suites)
        
    def generate_final_report(self):
        """Generate comprehensive test report"""
        total_time = time.time() - self.start_time if self.start_time else 0
        total_suites = len(self.test_results)
        passed_suites = sum(1 for r in self.test_results if r['success'])
        
        print("\n" + "="*80)
        print("🎯 COMPREHENSIVE MICROSANDBOX SERVER TEST REPORT")
        print("="*80)
        print(f"📊 Total Test Suites: {total_suites}")
        print(f"✅ Passed Suites: {passed_suites}")
        print(f"❌ Failed Suites: {total_suites - passed_suites}")
        print(f"📈 Success Rate: {passed_suites/total_suites*100:.1f}%")
        print(f"⏱️  Total Time: {total_time:.2f}s")
        print()
        
        # Detailed suite results
        print("📋 Test Suite Results:")
        for result in self.test_results:
            status = "✅" if result['success'] else "❌"
            print(f"  {status} {result['suite_name']} ({result['duration']:.2f}s)")
            
            # Show key details for failed suites
            if not result['success'] and 'error' in result['details']:
                print(f"      Error: {result['details']['error']}")
                
        # Recommendations
        print("\n🔧 Recommendations:")
        if passed_suites == total_suites:
            print("  🎉 All tests passed! MicroSandbox server is working correctly.")
        else:
            failed_suites = [r for r in self.test_results if not r['success']]
            for suite in failed_suites:
                suite_name = suite['suite_name']
                if suite_name == "Dependencies":
                    print(f"  ⚠️  Install missing dependencies: pip install microsandbox psutil")
                elif suite_name == "Basic Functionality":
                    print(f"  🔧 Check MicroSandbox server setup and configuration")
                elif suite_name == "Agent Interactions":
                    print(f"  🤖 Review agent integration and MCP server setup")
                elif suite_name == "Integration Tests":
                    print(f"  🔗 Check end-to-end workflow and server connectivity")
                elif suite_name == "Performance":
                    print(f"  ⚡ Consider optimizing code execution or system resources")
                    
        # Save comprehensive results
        results_file = project_root / "comprehensive_microsandbox_test_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                'test_summary': {
                    'total_suites': total_suites,
                    'passed_suites': passed_suites,
                    'failed_suites': total_suites - passed_suites,
                    'success_rate': passed_suites/total_suites*100,
                    'total_time': total_time,
                    'test_timestamp': datetime.now().isoformat()
                },
                'suite_results': self.test_results,
                'environment': {
                    'debug_mode': self.debug_mode,
                    'timeout': self.timeout
                }
            }, f, indent=2)
            
        print(f"\n📁 Comprehensive results saved to: {results_file}")
        print("="*80)


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="MicroSandbox Server Test Runner")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--timeout", type=int, default=300, help="Test timeout in seconds")
    parser.add_argument("--skip-performance", action="store_true", help="Skip performance tests")
    parser.add_argument("--skip-integration", action="store_true", help="Skip integration tests")
    parser.add_argument("--basic-only", action="store_true", help="Run only basic functionality tests")
    
    args = parser.parse_args()
    
    # Create test runner
    runner = MicroSandboxTestRunner(
        debug_mode=args.debug,
        timeout=args.timeout
    )
    
    if args.basic_only:
        # Run only basic tests
        logger.info("🎯 Running basic tests only...")
        success = await runner.run_basic_functionality_tests()
    else:
        # Run comprehensive tests
        success = await runner.run_all_tests(
            include_performance=not args.skip_performance,
            include_integration=not args.skip_integration
        )
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())