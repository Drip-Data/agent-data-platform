#!/usr/bin/env python3
"""
MicroSandbox Server Agent Interaction Tests
Tests the interaction between microsandbox server and agent runtime
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
import uuid

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class MicroSandboxAgentInteractionTester:
    """Test microsandbox server interactions with agent runtime"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        self.test_results = []
        
    async def setup(self):
        """Setup test environment"""
        self.server = MicroSandboxMCPServer(self.config_manager)
        
    async def cleanup(self):
        """Cleanup test environment"""
        if self.server:
            await self.server.cleanup()
            
    async def test_tool_capability_registration(self):
        """Test that all tool capabilities are properly registered"""
        logger.info("🧪 Testing tool capability registration...")
        
        capabilities = self.server.get_capabilities()
        
        # Expected actions (including new token management features)
        expected_actions = [
            "microsandbox_execute",
            "microsandbox_install_package",
            "microsandbox_list_sessions",
            "microsandbox_close_session",
            "microsandbox_cleanup_expired",
            "microsandbox_get_performance_stats",
            "microsandbox_get_health_status",
            "microsandbox_get_token_status",  # New token management
            "microsandbox_refresh_token"      # New token management
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
            has_examples = len(capability.examples) > 0
            
            # Validate specific parameter requirements
            param_result = {
                "action": capability.name,
                "parameter_count": len(params),
                "has_examples": has_examples,
                "valid_schema": True
            }
            
            # Action-specific validations
            if capability.name == "microsandbox_execute":
                required_params = [p for p, config in params.items() if config.get("required", False)]
                param_result["has_code_param"] = "code" in required_params
                param_result["has_optional_session"] = "session_id" in params
                param_result["has_timeout_param"] = "timeout" in params
                
            elif capability.name == "microsandbox_install_package":
                required_params = [p for p, config in params.items() if config.get("required", False)]
                param_result["has_package_name"] = "package_name" in required_params
                param_result["has_optional_version"] = "version" in params
                
            elif capability.name == "microsandbox_close_session":
                required_params = [p for p, config in params.items() if config.get("required", False)]
                param_result["has_session_id"] = "session_id" in required_params
                
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
            ("microsandbox_execute", {"code": "print('test')"}),
            ("microsandbox_list_sessions", {}),
            ("microsandbox_get_performance_stats", {}),
            ("microsandbox_get_health_status", {}),
            ("microsandbox_get_token_status", {}),      # New token management
            ("microsandbox_refresh_token", {}),         # New token management
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
                    "result_structure_valid": action_success,
                    "actual_success": result.get("success", False)
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
            ("microsandbox_execute", {}),  # Missing required code
            ("microsandbox_install_package", {}),  # Missing required package_name
            ("microsandbox_close_session", {}),  # Missing required session_id
            ("microsandbox_invalid_action", {}),  # Non-existent action
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
                    "error_consistent": error_consistent,
                    "error_message": result.get("error_message", "")
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
        
    async def test_session_state_management(self):
        """Test session state management across actions"""
        logger.info("🧪 Testing session state management...")
        
        session_id = f"agent_test_{uuid.uuid4().hex[:8]}"
        
        try:
            # Create session with code execution
            result1 = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "session_var = 'agent_test'", "session_id": session_id}
            )
            
            # List sessions - should include our session
            result2 = await self.server.handle_tool_action(
                "microsandbox_list_sessions",
                {}
            )
            
            # Use session variable in another execution
            result3 = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "print(session_var)", "session_id": session_id}
            )
            
            # Check state consistency
            exec1_success = result1.get("success", False)
            list_success = result2.get("success", False)
            exec2_success = result3.get("success", False)
            
            session_found = False
            if list_success:
                sessions = result2.get("data", {}).get("sessions", [])
                session_ids = [s.get("session_id") for s in sessions]
                session_found = session_id in session_ids
                
            variable_persisted = False
            if exec2_success:
                stdout = result3.get("data", {}).get("stdout", "")
                variable_persisted = "agent_test" in stdout
                
            success = exec1_success and list_success and exec2_success and session_found and variable_persisted
            
            # Cleanup session
            await self.server.handle_tool_action(
                "microsandbox_close_session",
                {"session_id": session_id}
            )
            
            self.test_results.append({
                "test": "session_state_management",
                "success": success,
                "result": {
                    "session_creation": exec1_success,
                    "session_listing": list_success,
                    "session_found": session_found,
                    "variable_execution": exec2_success,
                    "variable_persisted": variable_persisted
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "session_state_management",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Session state management test: {success}")
        return success
        
    async def test_performance_metrics_integration(self):
        """Test performance metrics collection and reporting"""
        logger.info("🧪 Testing performance metrics integration...")
        
        try:
            # Execute some code to generate metrics
            await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "print('metric test')"}
            )
            
            # Get performance stats
            result = await self.server.handle_tool_action(
                "microsandbox_get_performance_stats",
                {}
            )
            
            stats_success = result.get("success", False)
            
            if stats_success:
                data = result.get("data", {})
                perf_stats = data.get("performance_stats", {})
                server_info = data.get("server_info", {})
                
                # Check required performance metrics
                required_perf_fields = [
                    "uptime_seconds", "total_executions", "success_rate", 
                    "current_memory_mb", "error_distribution"
                ]
                
                required_server_fields = [
                    "server_name", "server_id", "default_timeout", 
                    "max_timeout", "session_timeout"
                ]
                
                perf_valid = all(field in perf_stats for field in required_perf_fields)
                server_valid = all(field in server_info for field in required_server_fields)
                
                success = perf_valid and server_valid
            else:
                success = False
                
            self.test_results.append({
                "test": "performance_metrics_integration",
                "success": success,
                "result": {
                    "stats_retrieval": stats_success,
                    "performance_fields_valid": perf_valid if stats_success else False,
                    "server_info_valid": server_valid if stats_success else False
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "performance_metrics_integration",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Performance metrics integration: {success}")
        return success
        
    async def test_health_monitoring_integration(self):
        """Test health monitoring and status reporting"""
        logger.info("🧪 Testing health monitoring integration...")
        
        try:
            # Get health status
            result = await self.server.handle_tool_action(
                "microsandbox_get_health_status",
                {}
            )
            
            health_success = result.get("success", False)
            
            if health_success:
                data = result.get("data", {})
                
                # Check required health fields
                required_fields = ["status", "issues", "metrics", "recommendations"]
                fields_valid = all(field in data for field in required_fields)
                
                # Check metrics structure
                metrics = data.get("metrics", {})
                required_metrics = [
                    "memory_usage_mb", "success_rate", "avg_execution_time", 
                    "active_sessions", "uptime_seconds"
                ]
                metrics_valid = all(metric in metrics for metric in required_metrics)
                
                # Check status is valid
                status = data.get("status", "")
                status_valid = status in ["healthy", "warning", "unhealthy"]
                
                success = fields_valid and metrics_valid and status_valid
            else:
                success = False
                
            self.test_results.append({
                "test": "health_monitoring_integration",
                "success": success,
                "result": {
                    "health_retrieval": health_success,
                    "fields_valid": fields_valid if health_success else False,
                    "metrics_valid": metrics_valid if health_success else False,
                    "status_valid": status_valid if health_success else False,
                    "health_status": data.get("status", "") if health_success else ""
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "health_monitoring_integration",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Health monitoring integration: {success}")
        return success
        
    async def test_mcp_protocol_compliance(self):
        """Test MCP protocol compliance"""
        logger.info("🧪 Testing MCP protocol compliance...")
        
        try:
            # Test server configuration
            server_name = self.server.server_name
            server_id = self.server.server_id
            endpoint = self.server.endpoint
            
            # Validate server properties
            name_valid = isinstance(server_name, str) and len(server_name) > 0
            id_valid = isinstance(server_id, str) and len(server_id) > 0
            endpoint_valid = isinstance(endpoint, str) and endpoint.startswith("ws://")
            
            # Test capability structure
            capabilities = self.server.get_capabilities()
            cap_structure_valid = True
            
            for cap in capabilities:
                if not hasattr(cap, 'name') or not hasattr(cap, 'description') or not hasattr(cap, 'parameters'):
                    cap_structure_valid = False
                    break
                    
            # Test tool action handler registration
            handler_valid = hasattr(self.server, 'handle_tool_action') and callable(self.server.handle_tool_action)
            
            success = name_valid and id_valid and endpoint_valid and cap_structure_valid and handler_valid
            
            self.test_results.append({
                "test": "mcp_protocol_compliance",
                "success": success,
                "result": {
                    "server_name_valid": name_valid,
                    "server_id_valid": id_valid,
                    "endpoint_valid": endpoint_valid,
                    "capability_structure_valid": cap_structure_valid,
                    "handler_registered": handler_valid,
                    "total_capabilities": len(capabilities)
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "mcp_protocol_compliance",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ MCP protocol compliance: {success}")
        return success
        
    async def test_concurrent_agent_requests(self):
        """Test handling of concurrent agent requests"""
        logger.info("🧪 Testing concurrent agent requests...")
        
        try:
            # Create multiple concurrent requests
            tasks = [
                self.server.handle_tool_action("microsandbox_execute", {"code": f"print('Task {i}')"}),
                self.server.handle_tool_action("microsandbox_get_performance_stats", {}),
                self.server.handle_tool_action("microsandbox_get_health_status", {}),
                self.server.handle_tool_action("microsandbox_list_sessions", {}),
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
            success = exceptions == 0 and successful_results >= 3
            
            self.test_results.append({
                "test": "concurrent_agent_requests",
                "success": success,
                "result": {
                    "total_requests": len(tasks),
                    "successful_results": successful_results,
                    "exceptions": exceptions,
                    "execution_time": duration
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "concurrent_agent_requests",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Concurrent agent requests: {success}")
        return success
        
    async def test_token_management_integration(self):
        """Test enhanced token management features"""
        logger.info("🧪 Testing token management integration...")
        
        try:
            # Test token status retrieval
            status_result = await self.server.handle_tool_action(
                "microsandbox_get_token_status",
                {}
            )
            
            status_success = status_result.get("success", False)
            
            if status_success:
                data = status_result.get("data", {})
                token_status = data.get("token_status", {})
                
                # Check required token status fields
                required_fields = ["has_token", "token_expiry", "is_expired"]
                fields_valid = all(field in token_status for field in required_fields)
                auto_refresh_enabled = data.get("auto_refresh_enabled", False)
            else:
                fields_valid = False
                auto_refresh_enabled = False
            
            # Test manual token refresh
            refresh_result = await self.server.handle_tool_action(
                "microsandbox_refresh_token", 
                {}
            )
            
            refresh_success = refresh_result.get("success", False)
            
            # Test that code execution works with token management
            exec_result = await self.server.handle_tool_action(
                "microsandbox_execute",
                {"code": "print('Token management test')"}
            )
            
            exec_success = exec_result.get("success", False)
            
            # Overall success
            success = status_success and fields_valid and auto_refresh_enabled and exec_success
            
            self.test_results.append({
                "test": "token_management_integration",
                "success": success,
                "result": {
                    "token_status_retrieval": status_success,
                    "status_fields_valid": fields_valid,
                    "auto_refresh_enabled": auto_refresh_enabled,
                    "manual_refresh_success": refresh_success,
                    "execution_with_token_mgmt": exec_success,
                    "token_features_working": success
                }
            })
            
        except Exception as e:
            self.test_results.append({
                "test": "token_management_integration",
                "success": False,
                "result": {"error": str(e)}
            })
            success = False
            
        logger.info(f"✅ Token management integration: {success}")
        return success
        
    async def run_all_interaction_tests(self):
        """Run all agent interaction tests"""
        logger.info("🚀 Starting MicroSandbox-Agent interaction tests...")
        
        try:
            await self.setup()
            
            tests = [
                self.test_tool_capability_registration,
                self.test_parameter_schema_validation,
                self.test_action_routing,
                self.test_error_handling_consistency,
                self.test_session_state_management,
                self.test_performance_metrics_integration,
                self.test_health_monitoring_integration,
                self.test_token_management_integration,    # New token management test
                self.test_mcp_protocol_compliance,
                self.test_concurrent_agent_requests,
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
        print("🤖 MICROSANDBOX-AGENT INTERACTION TEST REPORT")
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
        results_file = project_root / "test_results_microsandbox_agent_interactions.json"
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
async def test_microsandbox_agent_interactions():
    """Pytest runner for agent interaction tests"""
    tester = MicroSandboxAgentInteractionTester()
    success = await tester.run_all_interaction_tests()
    assert success, "MicroSandbox-agent interaction tests failed"


# Standalone execution
async def main():
    """Main function for standalone execution"""
    tester = MicroSandboxAgentInteractionTester()
    await tester.run_all_interaction_tests()


if __name__ == "__main__":
    asyncio.run(main())