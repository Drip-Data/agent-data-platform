import asyncio
from core.toolscore.local_tool_executor import LocalToolExecutor
from core.toolscore.tool_registry import ToolRegistry
from tools.python_executor_tool import PythonExecutorTool

def test_local_tool_executor_python():
    registry = ToolRegistry()
    tool = PythonExecutorTool()
    registry.register_tool_instance(tool)
    executor = LocalToolExecutor()
    async def run():
        result = await executor.execute("python_executor", "execute_code", {"code": "result = 1+1"})
        assert result["success"]
        assert result["result"] == 2 or "result" in result["stdout"]
    asyncio.run(run())
