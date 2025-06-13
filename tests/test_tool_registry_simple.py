from core.toolscore.tool_registry import ToolRegistry
from tools.python_executor_tool import PythonExecutorTool

def test_tool_registry_register_and_list():
    registry = ToolRegistry()
    tool = PythonExecutorTool()
    registry.register_tool_instance(tool)
    tools = asyncio.run(registry.list_tools())
    assert any(t.tool_id == "python_executor" for t in tools)
