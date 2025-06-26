"""
ToolsCore - 精简版工具注册与调用系统

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
from .core_manager import CoreManager
from .mcp_search_tool import MCPSearchTool
from .tool_gap_detector import ToolGapDetector

# 主要API入口
__all__ = [
    # === 核心类 ===
    "UnifiedToolLibrary",
    "CoreManager",
    
    # === 工具搜索和分析 ===
    "MCPSearchTool",
    "ToolGapDetector",
    
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
    
    # === 接口定义 ===
    "BaseToolAdapter",
    "ToolDiscoveryInterface",
    "ToolExecutionInterface"
]

# 版本信息
__version__ = "2.0.0"  # 精简版本

# 快速使用指南
__doc__ += """

## 快速开始 - 精简版

```python
from core.toolscore import UnifiedToolLibrary, FunctionToolSpec, ToolType

# 创建工具库
async def main():
    async with UnifiedToolLibrary() as tool_library:
        # 自动注册预定义工具（由CoreManager处理）
        await tool_library.initialize()
        
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

### 智能工具搜索（MCP）
- `search_and_install_mcp_server()` - 智能搜索并安装MCP服务器

## 精简版改进

1. **架构简化**：从22个文件精简到11个核心文件
2. **功能整合**：CoreManager整合了分散的管理功能
3. **性能优化**：减少文件间依赖，提升加载速度
4. **维护性**：统一的管理入口，降低复杂度

## 设计原则

1. **纯服务化**：工具库不做智能推荐，Agent自主决策
2. **职责分离**：工具管理与Agent推理完全分离  
3. **无硬编码**：避免关键词匹配等硬编码规则
4. **简单实用**：专注核心功能，预留扩展空间
""" 