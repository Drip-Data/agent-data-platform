#!/usr/bin/env python3
"""
Comprehensive test suite for Browser Use Tool
Tests all browser use tool actions and agent interactions
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
import aiohttp

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.browser_use_server.main import BrowserUseMCPServer, BrowserUseLLMAdapter
from core.config_manager import ConfigManager
from core.llm_client import LLMClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BrowserUseToolTester:
    """Comprehensive Browser Use Tool Tester"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        self.test_results = []
        self.start_time = None
        
    async def setup_test_environment(self):
        """Set up test environment"""
        logger.info("🔧 Setting up test environment...")
        
        # Initialize the browser use server
        self.server = BrowserUseMCPServer(self.config_manager)
        
        # Ensure browser session is initialized
        await self.server._ensure_browser_session()
        
        logger.info("✅ Test environment setup complete")
        
    async def cleanup_test_environment(self):
        """Clean up test environment"""
        logger.info("🧹 Cleaning up test environment...")
        
        if self.server and self.server.browser:
            await self.server.browser.close()
            
        logger.info("✅ Test environment cleanup complete")
        
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
            
    async def test_basic_navigation(self):
        """Test basic navigation actions"""
        logger.info("🧪 Testing basic navigation actions...")
        
        # Test 1: Navigate to Google
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_navigate", 
                {"url": "https://www.google.com"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Basic Navigation", "browser_navigate", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Basic Navigation", "browser_navigate", False, duration, error=str(e))
            
        # Test 2: Get current URL
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_get_current_url", 
                {}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Basic Navigation", "browser_get_current_url", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Basic Navigation", "browser_get_current_url", False, duration, error=str(e))
            
        # Test 3: Get page info
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_get_page_info", 
                {}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Basic Navigation", "browser_get_page_info", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Basic Navigation", "browser_get_page_info", False, duration, error=str(e))
            
    async def test_content_extraction(self):
        """Test content extraction capabilities"""
        logger.info("🧪 Testing content extraction...")
        
        # First navigate to a test page
        await self.server.handle_tool_action(
            "browser_navigate", 
            {"url": "https://example.com"}
        )
        
        # Test 1: Extract basic content
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_extract_content", 
                {"goal": "Extract main content from the page"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Content Extraction", "browser_extract_content", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Content Extraction", "browser_extract_content", False, duration, error=str(e))
            
        # Test 2: Extract content with links
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_extract_content", 
                {"goal": "Extract content with links", "include_links": True}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Content Extraction", "browser_extract_content_with_links", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Content Extraction", "browser_extract_content_with_links", False, duration, error=str(e))
            
        # Test 3: Get accessibility tree
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_get_ax_tree", 
                {"number_of_elements": 20}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Content Extraction", "browser_get_ax_tree", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Content Extraction", "browser_get_ax_tree", False, duration, error=str(e))
            
    async def test_element_interaction(self):
        """Test element interaction capabilities"""
        logger.info("🧪 Testing element interaction...")
        
        # Navigate to Google for search testing
        await self.server.handle_tool_action(
            "browser_navigate", 
            {"url": "https://www.google.com"}
        )
        
        # Test 1: Click element (search button)
        start_time = time.time()
        try:
            # First try to click on search input
            result = await self.server.handle_tool_action(
                "browser_click_element", 
                {"index": 0}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Element Interaction", "browser_click_element", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Element Interaction", "browser_click_element", False, duration, error=str(e))
            
        # Test 2: Input text
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_input_text", 
                {"index": 0, "text": "browser automation test"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Element Interaction", "browser_input_text", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Element Interaction", "browser_input_text", False, duration, error=str(e))
            
        # Test 3: Send keys
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_send_keys", 
                {"keys": "Enter"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Element Interaction", "browser_send_keys", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Element Interaction", "browser_send_keys", False, duration, error=str(e))
            
    async def test_scrolling_operations(self):
        """Test scrolling operations"""
        logger.info("🧪 Testing scrolling operations...")
        
        # Navigate to a page with content
        await self.server.handle_tool_action(
            "browser_navigate", 
            {"url": "https://news.ycombinator.com"}
        )
        
        # Test 1: Scroll down
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_scroll_down", 
                {"amount": 500}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Scrolling Operations", "browser_scroll_down", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Scrolling Operations", "browser_scroll_down", False, duration, error=str(e))
            
        # Test 2: Scroll up
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_scroll_up", 
                {"amount": 300}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Scrolling Operations", "browser_scroll_up", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Scrolling Operations", "browser_scroll_up", False, duration, error=str(e))
            
        # Test 3: Scroll to text
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_scroll_to_text", 
                {"text": "comments"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Scrolling Operations", "browser_scroll_to_text", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Scrolling Operations", "browser_scroll_to_text", False, duration, error=str(e))
            
    async def test_tab_management(self):
        """Test tab management operations"""
        logger.info("🧪 Testing tab management...")
        
        # Test 1: Open new tab
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_open_tab", 
                {"url": "https://httpbin.org/json"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Tab Management", "browser_open_tab", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Tab Management", "browser_open_tab", False, duration, error=str(e))
            
        # Test 2: Switch tab
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_switch_tab", 
                {"page_id": 0}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Tab Management", "browser_switch_tab", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Tab Management", "browser_switch_tab", False, duration, error=str(e))
            
    async def test_ai_task_execution(self):
        """Test AI task execution capability"""
        logger.info("🧪 Testing AI task execution...")
        
        # Test simple AI task
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_use_execute_task", 
                {
                    "task": "Navigate to Google and search for 'Python tutorial'",
                    "max_steps": 5,
                    "use_vision": True
                }
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("AI Task Execution", "browser_use_execute_task", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("AI Task Execution", "browser_use_execute_task", False, duration, error=str(e))
            
    async def test_utility_functions(self):
        """Test utility functions"""
        logger.info("🧪 Testing utility functions...")
        
        # Test 1: Screenshot
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_screenshot", 
                {"filename": "test_screenshot.png"}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Utility Functions", "browser_screenshot", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Utility Functions", "browser_screenshot", False, duration, error=str(e))
            
        # Test 2: Wait
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_wait", 
                {"seconds": 2}
            )
            duration = time.time() - start_time
            success = result.get("success", False)
            self.log_test_result("Utility Functions", "browser_wait", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Utility Functions", "browser_wait", False, duration, error=str(e))
            
        # Test 3: Save PDF
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_save_pdf", 
                {}
            )
            duration = time.time() - start_time  
            success = result.get("success", False)
            self.log_test_result("Utility Functions", "browser_save_pdf", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Utility Functions", "browser_save_pdf", False, duration, error=str(e))
            
    async def test_parameter_validation(self):
        """Test parameter validation and error handling"""
        logger.info("🧪 Testing parameter validation...")
        
        # Test 1: Missing required parameter
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_navigate", 
                {}  # Missing required url parameter
            )
            duration = time.time() - start_time
            # Should fail with proper error message
            success = not result.get("success", True) and "url" in result.get("error_message", "")
            self.log_test_result("Parameter Validation", "missing_required_param", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "missing_required_param", False, duration, error=str(e))
            
        # Test 2: Invalid parameter type
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_click_element", 
                {"index": "invalid"}  # Should be integer
            )
            duration = time.time() - start_time
            # Should handle gracefully
            success = True  # Any result is acceptable as long as it doesn't crash
            self.log_test_result("Parameter Validation", "invalid_param_type", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "invalid_param_type", False, duration, error=str(e))
            
        # Test 3: Unsupported action
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_invalid_action", 
                {}
            )
            duration = time.time() - start_time
            # Should fail with unsupported action error
            success = not result.get("success", True) and "Unsupported action" in result.get("error_message", "")
            self.log_test_result("Parameter Validation", "unsupported_action", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Parameter Validation", "unsupported_action", False, duration, error=str(e))
            
    async def test_llm_adapter_integration(self):
        """Test LLM adapter integration"""
        logger.info("🧪 Testing LLM adapter integration...")
        
        # Test LLM adapter initialization
        start_time = time.time()
        try:
            llm_config = self.config_manager.get_llm_config()
            llm_client = LLMClient(llm_config)
            adapter = BrowserUseLLMAdapter(llm_client)
            
            # Test basic functionality
            result = adapter._llm_type
            success = isinstance(result, str) and len(result) > 0
            duration = time.time() - start_time
            self.log_test_result("LLM Integration", "adapter_initialization", success, duration)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("LLM Integration", "adapter_initialization", False, duration, error=str(e))
            
    async def test_error_recovery(self):
        """Test error recovery mechanisms"""
        logger.info("🧪 Testing error recovery...")
        
        # Test navigation to invalid URL
        start_time = time.time()
        try:
            result = await self.server.handle_tool_action(
                "browser_navigate", 
                {"url": "https://invalid-url-that-does-not-exist.com"}
            )
            duration = time.time() - start_time
            # Should handle error gracefully
            success = not result.get("success", True)
            self.log_test_result("Error Recovery", "invalid_url_navigation", success, duration, result)
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Error Recovery", "invalid_url_navigation", False, duration, error=str(e))
            
    async def run_all_tests(self):
        """Run all tests"""
        logger.info("🚀 Starting comprehensive Browser Use Tool tests...")
        self.start_time = time.time()
        
        try:
            # Setup environment
            await self.setup_test_environment()
            
            # Run all test suites
            await self.test_basic_navigation()
            await self.test_content_extraction()
            await self.test_element_interaction()
            await self.test_scrolling_operations()
            await self.test_tab_management()
            await self.test_utility_functions()
            await self.test_parameter_validation()
            await self.test_llm_adapter_integration()
            await self.test_error_recovery()
            
            # Skip AI task execution test if no LLM available
            try:
                await self.test_ai_task_execution()
            except Exception as e:
                logger.warning(f"Skipping AI task execution test: {e}")
                
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
        print("🧪 BROWSER USE TOOL TEST REPORT")
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
        results_file = project_root / "test_results_browser_use.json"
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
async def browser_tester():
    """Pytest fixture for browser tester"""
    tester = BrowserUseToolTester()
    yield tester
    

@pytest.mark.asyncio
async def test_browser_use_comprehensive():
    """Comprehensive test runner for pytest"""
    tester = BrowserUseToolTester()
    success = await tester.run_all_tests()
    assert success, "Some browser use tool tests failed"


# Standalone execution
async def main():
    """Main function for standalone execution"""
    tester = BrowserUseToolTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    # Run tests standalone
    asyncio.run(main())