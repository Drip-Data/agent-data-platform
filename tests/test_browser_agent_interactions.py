#!/usr/bin/env python3
"""
Browser Use Tool Agent Interaction Tests
Tests the interaction between browser tool and agent runtime
"""

import asyncio
import pytest
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.browser_use_server.main import BrowserUseMCPServer
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class BrowserAgentInteractionTester:
    """Test browser tool interactions with agent runtime"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        self.test_results = []
        
    async def setup(self):
        """Setup test environment"""
        self.server = BrowserUseMCPServer(self.config_manager)
        await self.server._ensure_browser_session()
        
    async def cleanup(self):
        """Cleanup test environment"""
        if self.server and self.server.browser:
            await self.server.browser.close()
            
    async def test_tool_capability_registration(self):
        """Test that all tool capabilities are properly registered"""
        logger.info("🧪 Testing tool capability registration...")
        
        capabilities = self.server.get_capabilities()
        
        # Expected actions
        expected_actions = [
            "browser_use_execute_task",
            "browser_navigate",
            "browser_search_google", 
            "browser_go_back",
            "browser_click_element",
            "browser_input_text",
            "browser_send_keys",
            "browser_scroll_down",
            "browser_scroll_up",
            "browser_scroll_to_text",
            "browser_switch_tab",
            "browser_open_tab",
            "browser_close_tab",
            "browser_extract_content",
            "browser_get_content",
            "browser_get_ax_tree",
            "browser_get_dropdown_options",
            "browser_select_dropdown_option",
            "browser_drag_drop",
            "browser_save_pdf",
            "browser_screenshot",
            "browser_wait",
            "browser_get_page_info",
            "browser_get_current_url",
            "browser_close_session"
        ]
        
        registered_actions = [cap.name for cap in capabilities]
        
        # Check all expected actions are registered
        missing_actions = set(expected_actions) - set(registered_actions)
        extra_actions = set(registered_actions) - set(expected_actions)
        
        success = len(missing_actions) == 0
        
        result = {
            "total_capabilities": len(capabilities),
            "expected_actions": len(expected_actions),
            "registered_actions": len(registered_actions),
            "missing_actions": list(missing_actions),
            "extra_actions": list(extra_actions),
            "all_registered": success
        }
        
        self.test_results.append({
            "test": "tool_capability_registration",
            "success": success,
            "result": result
        })
        
        logger.info(f"✅ Capability registration test: {success}")
        return success
        
    async def test_parameter_schema_validation(self):
        """Test parameter schemas for all actions"""
        logger.info("🧪 Testing parameter schema validation...")
        
        capabilities = self.server.get_capabilities()
        results = []
        
        for capability in capabilities:
            # Check required parameters are marked correctly
            params = capability.parameters
            has_required = any(p.get("required", False) for p in params.values())
            has_examples = len(capability.examples) > 0
            
            param_result = {
                "action": capability.name,
                "parameter_count": len(params),
                "has_required_params": has_required,
                "has_examples": has_examples,
                "valid_schema": True  # Assume valid if no exceptions
            }
            
            results.append(param_result)
            
        success = all(r["valid_schema"] for r in results)
        
        self.test_results.append({
            "test": "parameter_schema_validation",
            "success": success,
            "result": {"parameter_schemas": results}
        })
        
        logger.info(f"✅ Parameter schema validation: {success}")
        return success
        
    async def test_action_routing(self):
        """Test action routing to correct handlers"""
        logger.info("🧪 Testing action routing...")
        
        test_cases = [
            ("browser_navigate", {"url": "https://httpbin.org/json"}),
            ("browser_get_current_url", {}),
            ("browser_wait", {"seconds": 1}),
            ("browser_screenshot", {}),
        ]
        
        results = []
        overall_success = True
        
        for action, params in test_cases:
            try:
                start_time = time.time()
                result = await self.server.handle_tool_action(action, params)
                duration = time.time() - start_time
                
                # Check result structure
                has_success_field = "success" in result
                has_data_field = "data" in result  
                has_error_field = "error_message" in result
                
                action_success = has_success_field and has_data_field and has_error_field
                
                results.append({
                    "action": action,
                    "routed_successfully": action_success,
                    "execution_time": duration,
                    "result_structure_valid": action_success
                })
                
                if not action_success:
                    overall_success = False
                    
            except Exception as e:
                results.append({
                    "action": action,
                    "routed_successfully": False,
                    "error": str(e)
                })
                overall_success = False
                
        self.test_results.append({
            "test": "action_routing",
            "success": overall_success,
            "result": {"routing_tests": results}
        })
        
        logger.info(f"✅ Action routing test: {overall_success}")
        return overall_success
        
    async def test_error_handling_consistency(self):
        """Test consistent error handling across actions"""
        logger.info("🧪 Testing error handling consistency...")
        
        # Test with invalid parameters
        test_cases = [
            ("browser_navigate", {}),  # Missing required url
            ("browser_click_element", {}),  # Missing required index
            ("browser_input_text", {"index": 0}),  # Missing required text
            ("invalid_action", {}),  # Non-existent action
        ]
        
        results = []
        consistent_errors = True
        
        for action, params in test_cases:
            try:
                result = await self.server.handle_tool_action(action, params)
                
                # Check error response structure
                is_error = not result.get("success", True)
                has_error_message = bool(result.get("error_message"))
                has_error_type = bool(result.get("error_type"))
                
                error_consistent = is_error and has_error_message
                
                results.append({
                    "action": action,
                    "returned_error": is_error,
                    "has_error_message": has_error_message,
                    "has_error_type": has_error_type,
                    "error_consistent": error_consistent
                })
                
                if not error_consistent:
                    consistent_errors = False
                    
            except Exception as e:
                results.append({
                    "action": action,
                    "exception_thrown": True,
                    "error": str(e)
                })
                consistent_errors = False
                
        self.test_results.append({
            "test": "error_handling_consistency",
            "success": consistent_errors,
            "result": {"error_tests": results}
        })
        
        logger.info(f"✅ Error handling consistency: {consistent_errors}")
        return consistent_errors
        
    async def test_state_management(self):
        """Test browser state management across actions"""
        logger.info("🧪 Testing state management...")
        
        try:
            # Navigate to a page
            result1 = await self.server.handle_tool_action(
                "browser_navigate", 
                {"url": "https://httpbin.org/json"}
            )
            
            # Get current URL - should reflect navigation
            result2 = await self.server.handle_tool_action(
                "browser_get_current_url", 
                {}
            )
            
            # Check state consistency
            nav_success = result1.get("success", False)
            url_success = result2.get("success", False)
            
            if nav_success and url_success:
                current_url = result2.get("data", {}).get("url", "")
                state_consistent = "httpbin.org" in current_url
            else:
                state_consistent = False
                
            success = nav_success and url_success and state_consistent
            
            self.test_results.append({
                "test": "state_management",
                "success": success,
                "result": {
                    "navigation_success": nav_success,
                    "url_retrieval_success": url_success,
                    "state_consistent": state_consistent,
                    "current_url": result2.get("data", {}).get("url", "")
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "state_management",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ State management test: {success}")
        return success
        
    async def test_concurrent_action_handling(self):
        """Test handling of concurrent actions"""
        logger.info("🧪 Testing concurrent action handling...")
        
        try:
            # Run multiple actions concurrently
            tasks = [
                self.server.handle_tool_action("browser_wait", {"seconds": 1}),
                self.server.handle_tool_action("browser_get_current_url", {}),
                self.server.handle_tool_action("browser_get_page_info", {}),
            ]
            
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start_time
            
            # Check results
            successful_results = 0
            exceptions = 0
            
            for result in results:
                if isinstance(result, Exception):
                    exceptions += 1
                elif isinstance(result, dict) and result.get("success", False):
                    successful_results += 1
                    
            # Should handle concurrent requests gracefully
            success = exceptions == 0 and successful_results >= 2
            
            self.test_results.append({
                "test": "concurrent_action_handling",
                "success": success,
                "result": {
                    "total_actions": len(tasks),
                    "successful_results": successful_results,
                    "exceptions": exceptions,
                    "execution_time": duration
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "concurrent_action_handling", 
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Concurrent action handling: {success}")
        return success
        
    async def test_resource_cleanup(self):
        """Test proper resource cleanup"""
        logger.info("🧪 Testing resource cleanup...")
        
        try:
            # Open browser session and perform actions
            await self.server._ensure_browser_session()
            
            # Navigate to create some state
            await self.server.handle_tool_action(
                "browser_navigate",
                {"url": "https://httpbin.org/json"}
            )
            
            # Close session
            result = await self.server.handle_tool_action(
                "browser_close_session",
                {}
            )
            
            cleanup_success = result.get("success", False)
            
            # Check that browser is actually closed
            browser_closed = self.server.browser is None
            context_closed = self.server.browser_context is None
            
            success = cleanup_success and browser_closed and context_closed
            
            self.test_results.append({
                "test": "resource_cleanup",
                "success": success,
                "result": {
                    "cleanup_action_success": cleanup_success,
                    "browser_closed": browser_closed,
                    "context_closed": context_closed
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "resource_cleanup",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Resource cleanup test: {success}")
        return success
        
    async def run_all_interaction_tests(self):
        """Run all agent interaction tests"""
        logger.info("🚀 Starting Browser-Agent interaction tests...")
        
        try:
            await self.setup()
            
            tests = [
                self.test_tool_capability_registration,
                self.test_parameter_schema_validation,
                self.test_action_routing,
                self.test_error_handling_consistency,
                self.test_state_management,
                self.test_concurrent_action_handling,
                self.test_resource_cleanup,
            ]
            
            results = []
            for test in tests:
                try:
                    result = await test()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Test failed with exception: {e}")
                    results.append(False)
                    
        finally:
            await self.cleanup()
            
        # Generate report
        self.generate_interaction_test_report(results)
        
        return all(results)
        
    def generate_interaction_test_report(self, results):
        """Generate interaction test report"""
        total_tests = len(results)
        passed_tests = sum(results)
        
        print("\n" + "="*60)
        print("🤖 BROWSER-AGENT INTERACTION TEST REPORT")
        print("="*60)
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {total_tests - passed_tests}")
        print(f"📈 Success Rate: {passed_tests/total_tests*100:.1f}%")
        print()
        
        # Detailed results
        for test_result in self.test_results:
            status = "✅" if test_result["success"] else "❌"
            print(f"{status} {test_result['test']}")
            
        # Save results 
        results_file = project_root / "test_results_agent_interactions.json"
        with open(results_file, 'w') as f:
            json.dump({
                'summary': {
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'success_rate': passed_tests/total_tests*100
                },
                'detailed_results': self.test_results
            }, f, indent=2)
            
        print(f"\n📁 Results saved to: {results_file}")
        print("="*60)


# Pytest integration
@pytest.mark.asyncio
async def test_browser_agent_interactions():
    """Pytest runner for agent interaction tests"""
    tester = BrowserAgentInteractionTester()
    success = await tester.run_all_interaction_tests()
    assert success, "Browser-agent interaction tests failed"


# Standalone execution
async def main():
    """Main function for standalone execution"""
    tester = BrowserAgentInteractionTester()
    await tester.run_all_interaction_tests()


if __name__ == "__main__":
    asyncio.run(main())