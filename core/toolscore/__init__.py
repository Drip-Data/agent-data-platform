"""
ToolsCore - 新一代工具注册与调用系统

设计理念：
- 纯服务化：工具库仅提供工具管理服务，Agent负责智能决策
- 职责分离：工具管理与Agent推理完全分离
- 无硬编码：不包含场景匹配等硬编码逻辑
- 简单实用：专注核心功能，为将来扩展预留空间
"""

from .interfaces import (
    # 工具规范类
    ToolSpec,
    FunctionToolSpec, 
    MCPServerSpec,
    ToolCapability,
    
    # 工具类型
    ToolType,
    
    # 执行结果
    ExecutionResult,
    RegistrationResult,
    
    # 适配器接口
    BaseToolAdapter,
    ToolDiscoveryInterface,
    ToolExecutionInterface
)

from .unified_tool_library import UnifiedToolLibrary
from .tool_registry import ToolRegistry
from .description_engine import DescriptionEngine
from .unified_dispatcher import UnifiedDispatcher
from .adapters import FunctionToolAdapter, MCPServerAdapter

# 主要API入口
__all__ = [
    # === 核心类 ===
    "UnifiedToolLibrary",
    
    # === 工具规范 ===
    "ToolSpec",
    "FunctionToolSpec", 
    "MCPServerSpec",
    "ToolCapability",
    
    # === 工具类型 ===
    "ToolType",
    
    # === 结果类型 ===
    "ExecutionResult",
    "RegistrationResult",
    
    # === 内部组件（高级用户） ===
    "ToolRegistry",
    "DescriptionEngine", 
    "UnifiedDispatcher",
    "FunctionToolAdapter",
    "MCPServerAdapter",
    
    # === 接口定义 ===
    "BaseToolAdapter",
    "ToolDiscoveryInterface",
    "ToolExecutionInterface"
]

# 版本信息
__version__ = "1.0.0"

# 快速使用指南
__doc__ += """

## 快速开始

```python
from core.toolscore import UnifiedToolLibrary, FunctionToolSpec, ToolType

# 创建工具库
async def main():
    async with UnifiedToolLibrary() as tool_library:
        # 快速注册预定义工具
        await tool_library.quick_register_browser_tool()
        await tool_library.quick_register_python_tool()
        
        # 获取所有工具描述（供Agent使用）
        description = await tool_library.get_all_tools_description_for_agent()
        print(description)
        
        # 执行工具调用
        result = await tool_library.execute_tool(
            tool_id="browser_navigator",
            action="navigate", 
            parameters={"url": "https://www.google.com"}
        )
        print(result)
```

## 核心API

### 工具管理
- `register_function_tool()` - 注册Function Tool
- `register_mcp_server()` - 注册MCP Server  
- `get_all_tools()` - 获取所有工具
- `get_tool_by_id()` - 获取特定工具

### Agent友好API
- `get_all_tools_description_for_agent()` - 获取Agent可理解的工具描述
- `get_tool_description_for_agent()` - 获取单个工具的Agent描述

### 工具执行
- `execute_tool()` - 执行单个工具
- `batch_execute_tools()` - 批量执行工具

## 设计原则

1. **纯服务化**：工具库不做智能推荐，Agent自主决策
2. **职责分离**：工具管理与Agent推理完全分离  
3. **无硬编码**：避免关键词匹配等硬编码规则
4. **简单实用**：专注核心功能，预留扩展空间
""" 