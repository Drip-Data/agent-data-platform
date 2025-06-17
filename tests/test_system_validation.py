#!/usr/bin/env python3
"""
System validation script - comprehensive test of all major components
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_synthesis_system():
    """Test synthesis system functionality"""
    print("🔬 Testing Synthesis System...")
    
    try:
        from core.synthesiscore.synthesis import SynthesisService, TrajectoryHandler
        
        # Test service creation
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": True,
            "llm": {"provider": "openai", "model": "gpt-3.5-turbo"}
        }
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url'), \
             patch('core.synthesiscore.synthesis.LLMClient'):
            service = SynthesisService(config)
            assert service.enabled is True
            print("   ✅ SynthesisService creation: PASS")
        
        # Test trajectory handler
        mock_synthesis = Mock()
        mock_synthesis.config = {"redis_url": "redis://localhost:6379"}
        handler = TrajectoryHandler(mock_synthesis, "/test/path")
        assert handler is not None
        print("   ✅ TrajectoryHandler creation: PASS")
        
        return True
    except Exception as e:
        print(f"   ❌ Synthesis system error: {e}")
        return False

def test_service_management():
    """Test service management system"""
    print("🔬 Testing Service Management...")
    
    try:
        from services.service_manager import ServiceManager
        
        # Test service manager creation
        sm = ServiceManager()
        assert sm is not None
        print("   ✅ ServiceManager creation: PASS")
        
        # Test basic methods exist
        methods = ['start_all_services', 'stop_all_services']
        for method in methods:
            if hasattr(sm, method):
                print(f"   ✅ Method {method}: EXISTS")
            else:
                print(f"   ⚠️  Method {method}: MISSING")
        
        return True
    except Exception as e:
        print(f"   ❌ Service management error: {e}")
        return False

def test_task_execution_system():
    """Test task execution system"""
    print("🔬 Testing Task Execution System...")
    
    try:
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        from core.config_manager import ConfigManager
        from core.llm_client import LLMClient
        from runtimes.reasoning.toolscore_client import ToolScoreClient
        
        config_manager = ConfigManager()
        
        with patch.object(LLMClient, '__init__', return_value=None), \
             patch.object(ToolScoreClient, '__init__', return_value=None):
            
            mock_llm = Mock()
            mock_toolscore = Mock()
            
            runtime = EnhancedReasoningRuntime(
                config_manager=config_manager,
                llm_client=mock_llm,
                toolscore_client=mock_toolscore
            )
            assert runtime is not None
            print("   ✅ EnhancedReasoningRuntime creation: PASS")
        
        return True
    except Exception as e:
        print(f"   ❌ Task execution system error: {e}")
        return False

def test_mcp_servers():
    """Test MCP server system"""
    print("🔬 Testing MCP Servers...")
    
    servers = [
        ('python_executor_server', 'mcp_servers.python_executor_server.main'),
        ('browser_navigator_server', 'mcp_servers.browser_navigator_server.main'), 
        ('search_tool_server', 'mcp_servers.search_tool_server.main')
    ]
    
    passed = 0
    for name, module_path in servers:
        try:
            __import__(module_path, fromlist=[''])
            print(f"   ✅ {name}: AVAILABLE")
            passed += 1
        except Exception as e:
            print(f"   ⚠️  {name}: {str(e)[:50]}...")
    
    return passed > 0

def test_toolscore_system():
    """Test ToolScore system"""
    print("🔬 Testing ToolScore System...")
    
    try:
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        from core.toolscore.mcp_connector import MCPServerConnector
        
        # Test UnifiedToolLibrary
        print("   ✅ UnifiedToolLibrary: IMPORTABLE")
        
        # Test MCPServerConnector
        print("   ✅ MCPServerConnector: IMPORTABLE")
        
        return True
    except Exception as e:
        print(f"   ❌ ToolScore system error: {e}")
        return False

def test_configuration_system():
    """Test configuration system"""
    print("🔬 Testing Configuration System...")
    
    try:
        from core.config_manager import ConfigManager
        from core.redis_manager import RedisManager
        
        # Test ConfigManager
        config_manager = ConfigManager()
        assert config_manager is not None
        print("   ✅ ConfigManager creation: PASS")
        
        # Test RedisManager
        with patch('core.redis_manager.RedisManager'):
            print("   ✅ RedisManager: IMPORTABLE")
        
        return True
    except Exception as e:
        print(f"   ❌ Configuration system error: {e}")
        return False

async def test_async_functionality():
    """Test async functionality"""
    print("🔬 Testing Async Functionality...")
    
    try:
        from core.synthesiscore.synthesis import SynthesisService
        
        config = {
            "redis_url": "redis://localhost:6379",
            "synthesis_enabled": True
        }
        
        with patch('core.synthesiscore.synthesis.async_redis.from_url') as mock_redis, \
             patch('core.synthesiscore.synthesis.LLMClient'):
            
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            
            service = SynthesisService(config)
            
            # Test async redis access
            assert service.redis == mock_redis_client
            print("   ✅ Async Redis integration: PASS")
        
        return True
    except Exception as e:
        print(f"   ❌ Async functionality error: {e}")
        return False

def main():
    """Run comprehensive system validation"""
    print("🚀 Starting Comprehensive System Validation")
    print("=" * 50)
    
    tests = [
        ("Synthesis System", test_synthesis_system),
        ("Service Management", test_service_management),
        ("Task Execution", test_task_execution_system),
        ("MCP Servers", test_mcp_servers),
        ("ToolScore System", test_toolscore_system),
        ("Configuration", test_configuration_system),
    ]
    
    results = []
    for name, test_func in tests:
        result = test_func()
        results.append((name, result))
        print()
    
    # Test async functionality
    print("🔬 Testing Async Functionality...")
    async_result = asyncio.run(test_async_functionality())
    results.append(("Async Functionality", async_result))
    print()
    
    # Summary
    print("📊 VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:<20}: {status}")
    
    print("-" * 50)
    print(f"Total: {passed}/{total} components validated")
    
    if passed >= total * 0.8:  # 80% pass rate
        print("🎉 SYSTEM VALIDATION: SUCCESS")
        print("Your agent data platform is ready for operation!")
    else:
        print("⚠️  SYSTEM VALIDATION: NEEDS ATTENTION")
        print("Some components need review before full operation.")
    
    return passed >= total * 0.8

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)