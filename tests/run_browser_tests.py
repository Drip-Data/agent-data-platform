#!/usr/bin/env python3
"""
Browser Use Tool Test Runner
Executes all browser use tool tests and provides debugging capabilities
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

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import test modules
from test_browser_use_tool import BrowserUseToolTester
from test_browser_agent_interactions import BrowserAgentInteractionTester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BrowserTestRunner:
    """Comprehensive browser test runner with debugging capabilities"""
    
    def __init__(self, debug_mode=False, headless=True, timeout=300):
        self.debug_mode = debug_mode
        self.headless = headless
        self.timeout = timeout
        self.test_results = []
        self.start_time = None
        
        # Set environment variables for testing
        os.environ["BROWSER_HEADLESS"] = "true" if headless else "false"
        
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
        
    async def run_basic_functionality_tests(self):
        """Run basic functionality tests"""
        logger.info("🧪 Running basic functionality tests...")
        
        start_time = time.time()
        success = False
        details = {}
        
        try:
            tester = BrowserUseToolTester()
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
            tester = BrowserAgentInteractionTester()
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
        
    async def run_performance_tests(self):
        """Run performance benchmarks"""
        logger.info("⚡ Running performance tests...")
        
        start_time = time.time()
        
        try:
            from test_browser_use_tool import BrowserUseToolTester
            tester = BrowserUseToolTester()
            await tester.setup_test_environment()
            
            # Test navigation performance
            nav_times = []
            for i in range(3):
                nav_start = time.time()
                result = await tester.server.handle_tool_action(
                    "browser_navigate", 
                    {"url": f"https://httpbin.org/json?test={i}"}
                )
                nav_duration = time.time() - nav_start
                if result.get("success"):
                    nav_times.append(nav_duration)
                    
            # Test content extraction performance
            extract_times = []
            for i in range(3):
                extract_start = time.time()
                result = await tester.server.handle_tool_action(
                    "browser_extract_content",
                    {"goal": f"Extract content test {i}"}
                )
                extract_duration = time.time() - extract_start
                if result.get("success"):
                    extract_times.append(extract_duration)
                    
            await tester.cleanup_test_environment()
            
            # Calculate averages
            avg_nav_time = sum(nav_times) / len(nav_times) if nav_times else 0
            avg_extract_time = sum(extract_times) / len(extract_times) if extract_times else 0
            
            # Performance criteria (adjust as needed)
            nav_acceptable = avg_nav_time < 10.0  # 10 seconds max for navigation
            extract_acceptable = avg_extract_time < 5.0  # 5 seconds max for extraction
            
            success = nav_acceptable and extract_acceptable
            
            details = {
                'avg_navigation_time': avg_nav_time,
                'avg_extraction_time': avg_extract_time,
                'navigation_acceptable': nav_acceptable,
                'extraction_acceptable': extract_acceptable,
                'navigation_samples': len(nav_times),
                'extraction_samples': len(extract_times)
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
        
    async def run_stress_tests(self):
        """Run stress tests"""
        logger.info("💪 Running stress tests...")
        
        start_time = time.time()
        
        try:
            from test_browser_use_tool import BrowserUseToolTester
            tester = BrowserUseToolTester()
            await tester.setup_test_environment()
            
            # Rapid action sequence test
            actions = [
                ("browser_get_current_url", {}),
                ("browser_get_page_info", {}),
                ("browser_wait", {"seconds": 0.5}),
                ("browser_screenshot", {}),
                ("browser_get_current_url", {}),
            ]
            
            successful_actions = 0
            failed_actions = 0
            
            for action, params in actions * 5:  # Repeat 5 times
                try:
                    result = await tester.server.handle_tool_action(action, params)
                    if result.get("success"):
                        successful_actions += 1
                    else:
                        failed_actions += 1
                except Exception:
                    failed_actions += 1
                    
            await tester.cleanup_test_environment()
            
            # Stress test criteria
            total_actions = successful_actions + failed_actions
            success_rate = successful_actions / total_actions if total_actions > 0 else 0
            success = success_rate >= 0.8  # 80% success rate required
            
            details = {
                'total_actions': total_actions,
                'successful_actions': successful_actions,
                'failed_actions': failed_actions,
                'success_rate': success_rate
            }
            
        except Exception as e:
            logger.error(f"Stress tests failed: {e}")
            if self.debug_mode:
                traceback.print_exc()
            success = False
            details = {'error': str(e)}
            
        duration = time.time() - start_time
        self.log_test_suite_result("Stress Tests", success, duration, details)
        return success
        
    async def run_dependency_checks(self):
        """Check dependencies and environment"""
        logger.info("🔍 Running dependency checks...")
        
        start_time = time.time()
        checks = {}
        
        try:
            # Check browser-use import
            try:
                import browser_use
                checks['browser_use_import'] = True
                checks['browser_use_version'] = getattr(browser_use, '__version__', 'unknown')
            except ImportError as e:
                checks['browser_use_import'] = False
                checks['browser_use_error'] = str(e)
                
            # Check playwright
            try:
                import playwright
                checks['playwright_import'] = True
                checks['playwright_version'] = getattr(playwright, '__version__', 'unknown')
            except ImportError as e:
                checks['playwright_import'] = False
                checks['playwright_error'] = str(e)
                
            # Check core modules
            try:
                from core.config_manager import ConfigManager
                from core.llm_client import LLMClient
                checks['core_modules_import'] = True
            except ImportError as e:
                checks['core_modules_import'] = False
                checks['core_modules_error'] = str(e)
                
            # Check configuration
            try:
                config_manager = ConfigManager()
                llm_config = config_manager.get_llm_config()
                checks['config_load'] = True
                checks['llm_provider'] = llm_config.provider.value if hasattr(llm_config, 'provider') else 'unknown'
            except Exception as e:
                checks['config_load'] = False
                checks['config_error'] = str(e)
                
            # Overall success
            critical_checks = ['browser_use_import', 'playwright_import', 'core_modules_import']
            success = all(checks.get(check, False) for check in critical_checks)
            
        except Exception as e:
            logger.error(f"Dependency checks failed: {e}")
            success = False
            checks['general_error'] = str(e)
            
        duration = time.time() - start_time
        self.log_test_suite_result("Dependencies", success, duration, checks)
        return success
        
    async def run_all_tests(self, include_performance=True, include_stress=True):
        """Run all test suites"""
        logger.info("🚀 Starting comprehensive browser use tool testing...")
        self.start_time = time.time()
        
        test_suites = []
        
        # Always run dependency checks first
        dependency_success = await self.run_dependency_checks()
        test_suites.append(dependency_success)
        
        if dependency_success:
            # Run core functionality tests
            basic_success = await self.run_basic_functionality_tests()
            test_suites.append(basic_success)
            
            # Run agent interaction tests
            interaction_success = await self.run_agent_interaction_tests()
            test_suites.append(interaction_success)
            
            # Optional performance tests
            if include_performance:
                perf_success = await self.run_performance_tests()
                test_suites.append(perf_success)
                
            # Optional stress tests
            if include_stress and basic_success:
                stress_success = await self.run_stress_tests()
                test_suites.append(stress_success)
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
        print("🎯 COMPREHENSIVE BROWSER USE TOOL TEST REPORT")
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
            print("  🎉 All tests passed! Browser use tool is working correctly.")
        else:
            failed_suites = [r for r in self.test_results if not r['success']]
            for suite in failed_suites:
                suite_name = suite['suite_name']
                if suite_name == "Dependencies":
                    print(f"  ⚠️  Fix dependency issues before running other tests")
                elif suite_name == "Basic Functionality":
                    print(f"  🔧 Check browser use server configuration and dependencies")
                elif suite_name == "Agent Interactions":
                    print(f"  🤖 Review agent integration and MCP server setup")
                elif suite_name == "Performance":
                    print(f"  ⚡ Consider optimizing browser operations or increasing timeouts")
                elif suite_name == "Stress Tests":
                    print(f"  💪 Review resource management and concurrent operation handling")
                    
        # Save comprehensive results
        results_file = project_root / "comprehensive_test_results.json"
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
                    'headless_mode': self.headless,
                    'debug_mode': self.debug_mode,
                    'timeout': self.timeout
                }
            }, f, indent=2)
            
        print(f"\n📁 Comprehensive results saved to: {results_file}")
        print("="*80)


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Browser Use Tool Test Runner")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--timeout", type=int, default=300, help="Test timeout in seconds")
    parser.add_argument("--skip-performance", action="store_true", help="Skip performance tests")
    parser.add_argument("--skip-stress", action="store_true", help="Skip stress tests")
    parser.add_argument("--basic-only", action="store_true", help="Run only basic functionality tests")
    
    args = parser.parse_args()
    
    # Create test runner
    runner = BrowserTestRunner(
        debug_mode=args.debug,
        headless=not args.visible,
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
            include_stress=not args.skip_stress
        )
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())