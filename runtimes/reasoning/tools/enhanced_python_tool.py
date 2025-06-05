"""
增强Python执行器工具 - 符合新工具注册接口
"""

import logging
from typing import Dict, Any, List
from core.toolscore.interfaces import ToolCapability, ToolType
from .python_executor_tool import PythonExecutorTool

logger = logging.getLogger(__name__)

class EnhancedPythonTool:
    """增强Python工具 - 符合新接口标准"""
    
    def __init__(self):
        self.python_tool = PythonExecutorTool()
        
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """统一的工具执行接口"""
        try:
            if action == "python_execute":
                code = params.get("code", "")
                timeout = params.get("timeout", 30)
                return await self.python_tool.execute_code(code, timeout)
                
            elif action == "python_analyze":
                data = params.get("data")
                operation = params.get("operation", "describe")
                return await self.python_tool.analyze_data(data, operation)
                
            elif action == "python_visualize":
                data = params.get("data")
                plot_type = params.get("plot_type", "line")
                title = params.get("title", "Data Visualization")
                save_path = params.get("save_path")
                return await self.python_tool.create_visualization(data, plot_type, title, save_path)
                
            elif action == "python_install_package":
                package_name = params.get("package_name", "")
                return await self.python_tool.install_package(package_name)
                
            else:
                return {
                    "success": False,
                    "error": f"Unsupported action: {action}",
                    "error_type": "UnsupportedAction"
                }
                
        except Exception as e:
            logger.error(f"Python tool execution failed for {action}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "PythonToolError"
            }
    
    def get_capabilities(self) -> List[ToolCapability]:
        """获取Python工具的所有能力"""
        return [
            ToolCapability(
                name="python_execute",
                description="执行Python代码",
                parameters={
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码",
                        "required": True
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "执行超时时间（秒），默认30秒",
                        "required": False
                    }
                },
                examples=[
                    {"code": "print('Hello, World!')"},
                    {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根结果: {result}')"},
                    {"code": "data = [1, 2, 3, 4, 5]\nprint(f'平均值: {sum(data) / len(data)}')", "timeout": 10}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="python_analyze",
                description="使用pandas分析数据",
                parameters={
                    "data": {
                        "type": "any",
                        "description": "要分析的数据（列表、字典或其他格式）",
                        "required": True
                    },
                    "operation": {
                        "type": "string",
                        "description": "分析操作类型：describe(描述统计), info(数据信息), head(前几行), tail(后几行)",
                        "required": False
                    }
                },
                examples=[
                    {"data": [1, 2, 3, 4, 5], "operation": "describe"},
                    {"data": {"name": ["Alice", "Bob"], "age": [25, 30]}, "operation": "info"},
                    {"data": [[1, 2], [3, 4], [5, 6]], "operation": "head"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="python_visualize",
                description="创建数据可视化图表",
                parameters={
                    "data": {
                        "type": "any",
                        "description": "要可视化的数据",
                        "required": True
                    },
                    "plot_type": {
                        "type": "string",
                        "description": "图表类型：line(折线图), bar(柱状图), scatter(散点图), pie(饼图), hist(直方图)",
                        "required": False
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题",
                        "required": False
                    },
                    "save_path": {
                        "type": "string",
                        "description": "图片保存路径",
                        "required": False
                    }
                },
                examples=[
                    {"data": [1, 2, 3, 4, 5], "plot_type": "line", "title": "趋势图"},
                    {"data": {"A": 10, "B": 20, "C": 15}, "plot_type": "bar"},
                    {"data": [[1, 2], [2, 3], [3, 5]], "plot_type": "scatter", "save_path": "/app/output/chart.png"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="python_install_package",
                description="安装Python包",
                parameters={
                    "package_name": {
                        "type": "string",
                        "description": "要安装的包名",
                        "required": True
                    }
                },
                examples=[
                    {"package_name": "requests"},
                    {"package_name": "beautifulsoup4"},
                    {"package_name": "scikit-learn"}
                ]
                # 移除 success_indicators 和 common_errors
            )
        ]
    
    def get_tool_type(self) -> ToolType:
        """返回工具类型"""
        return ToolType.FUNCTION
    
    def cleanup(self):
        """清理资源"""
        self.python_tool.cleanup()

# 创建增强Python工具实例
enhanced_python_tool = EnhancedPythonTool() 