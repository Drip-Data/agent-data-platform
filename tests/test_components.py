import asyncio
import sys
import types
import unittest
from unittest import mock

class DummyRedis:
    async def ping(self):
        return True

    async def close(self):
        pass

class ComponentHealthCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_sandbox_runtime_health(self):
        try:
            from runtimes.sandbox.runtime import LightweightSandboxRuntime
        except ImportError:
            self.skipTest("SandboxRuntime dependencies not installed")
            return

        dummy = DummyRedis()
        with mock.patch('redis.asyncio.from_url', return_value=dummy), \
             mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            runtime = LightweightSandboxRuntime({'redis_url': 'redis://localhost'})
            runtime.redis = dummy
            healthy = await runtime.health_check()
        self.assertTrue(healthy)

class ResearchTrackerTests(unittest.TestCase):
    def test_tracker_records_loops(self):
        import importlib.util
        import pathlib

        tracker_path = pathlib.Path('runtimes/reasoning/deep_research/tracker.py')
        spec = importlib.util.spec_from_file_location('tracker', tracker_path)
        tracker_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tracker_module)
        ResearchTracker = tracker_module.ResearchTracker

        tracker = ResearchTracker("demo")
        tracker.set_config({})
        start = tracker.record_loop_start(1)
        tracker.record_search_executed(1, "query", 2)
        tracker.record_loop_end(1, start, True, ["next"], "")

        data = tracker.get_trace_data()

        self.assertEqual(data["status"], "completed")
        self.assertEqual(len(data["loops"]), 1)
        self.assertEqual(data["total_queries"], 1)
        self.assertEqual(data["sources_count"], 2)

    async def test_reasoning_runtime_health(self):
        try:
            import types
            sys.modules['langgraph'] = types.ModuleType('langgraph')
            sys.modules['langgraph.graph'] = types.ModuleType('graph')
            sys.modules['langgraph.graph'].StateGraph = object
            sys.modules['langgraph.graph'].START = 'start'
            sys.modules['langgraph.graph'].END = 'end'
            sys.modules['langgraph.graph'].add_messages = lambda *a, **k: None
            sys.modules['langgraph.types'] = types.ModuleType('types')
            sys.modules['langgraph.types'].Send = object
            dummy_module = types.ModuleType('deep_research_tool')
            dummy_module.DeepResearchTool = object
            dummy_module.deep_research_tool = object()
            sys.modules['runtimes.reasoning.tools.deep_research_tool'] = dummy_module
            sys.modules['langchain_core'] = types.ModuleType('langchain_core')
            sys.modules['langchain_core.runnables'] = types.ModuleType('runnables')
            sys.modules['langchain_core.runnables'].RunnableConfig = object
            sys.modules['langchain_core.messages'] = types.ModuleType('messages')
            sys.modules['langchain_core.messages'].AIMessage = object
            sys.modules['langchain_core.messages'].HumanMessage = object
            from runtimes.reasoning.runtime import ReasoningRuntime
        except ImportError:
            self.skipTest("ReasoningRuntime dependencies not installed")
            return

        with mock.patch('core.llm_client.LLMClient.generate_reasoning', new=mock.AsyncMock(return_value='ok')):
            runtime = ReasoningRuntime()
            healthy = await runtime.health_check()
        self.assertTrue(healthy)

    async def test_web_navigator_runtime_health(self):
        from runtimes.web_navigator.runtime import MemoryControlledWebRuntime
        from runtimes.web_navigator import browser_manager as bm
        dummy = DummyRedis()
        with mock.patch('redis.asyncio.from_url', return_value=dummy), \
             mock.patch.object(bm.BrowserManager, 'health_check', new=mock.AsyncMock(return_value=True)), \
             mock.patch.object(bm.BrowserManager, 'cleanup', new=mock.AsyncMock()):
            runtime = MemoryControlledWebRuntime({'redis_url': 'redis://localhost', 'vllm_url': 'http://localhost:8000', 'max_concurrent': 1})
            runtime.redis = dummy
            healthy = await runtime.health_check()
        self.assertTrue(healthy)

if __name__ == '__main__':
    unittest.main()
