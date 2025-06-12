import asyncio
import uuid
from core.toolscore.interfaces import MCPServerSpec, ToolType, ToolCapability
from core.toolscore.unified_tool_library import UnifiedToolLibrary
from core.toolscore.tool_registry import ToolRegistry # 假设ToolRegistry是可导入的

async def test_register_external_mcp_server():
    """
    测试注册外部MCP服务器的功能。
    """
    print("开始测试 register_external_mcp_server...")

    # 初始化UnifiedToolLibrary
    # 注意：在实际应用中，ToolRegistry和UnifiedDispatcher可能需要更复杂的初始化
    # 这里为了测试简化处理
    unified_tool_library = UnifiedToolLibrary()
    await unified_tool_library.initialize()

    # 模拟一个MCP服务器规范
    server_name = f"TestMCPServer-{uuid.uuid4().hex[:8]}"
    test_server_spec = MCPServerSpec(
        tool_id=f"mcp-server-{uuid.uuid4()}",
        name=server_name,
        description="一个用于测试的模拟MCP服务器",
        tool_type=ToolType.MCP_SERVER,
        endpoint="http://localhost:8080/test-mcp",
        capabilities=[
            ToolCapability(
                name="test_tool_1",
                description="测试工具1",
                parameters={"type": "object", "properties": {"param1": {"type": "string"}}},
                examples=[]
            ),
            ToolCapability(
                name="test_tool_2",
                description="测试工具2",
                parameters={"type": "object", "properties": {"param2": {"type": "number"}}},
                examples=[]
            )
        ],
        server_config={"api_version": "1.0"},
        connection_params={"timeout": 5}
    )

    print(f"尝试注册MCP服务器: {test_server_spec.name} (Endpoint: {test_server_spec.endpoint})")

    # 调用注册方法
    registration_result = await unified_tool_library.register_external_mcp_server(test_server_spec)

    # 验证结果
    if registration_result.success:
        print(f"成功注册MCP服务器: {test_server_spec.name}")
        # 进一步验证：检查是否能在注册中心找到该服务器
        retrieved_spec = await unified_tool_library.get_tool_by_id(test_server_spec.tool_id)
        if retrieved_spec and retrieved_spec.name == test_server_spec.name:
            print(f"通过get_tool_spec成功检索到服务器: {retrieved_spec.name}")
            print("测试通过！")
        else:
            print("错误：无法通过get_tool_spec检索到注册的服务器。")
            print("测试失败！")
    else:
        print(f"注册MCP服务器失败: {registration_result.error}")
        print("测试失败！")

    print("测试结束。")

if __name__ == "__main__":
    asyncio.run(test_register_external_mcp_server())