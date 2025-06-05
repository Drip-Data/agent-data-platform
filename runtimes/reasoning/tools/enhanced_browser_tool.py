"""
增强浏览器工具 - 符合新工具注册接口
"""

import logging
from typing import Dict, Any, List
from core.toolscore.interfaces import ToolCapability, ToolType
from .browser_tool import BrowserTool

logger = logging.getLogger(__name__)

class EnhancedBrowserTool:
    """增强浏览器工具 - 符合新接口标准"""
    
    def __init__(self):
        self.browser_tool = BrowserTool()
        
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """统一的工具执行接口"""
        try:
            if action == "browser_navigate":
                url = params.get("url", "")
                return await self.browser_tool.navigate(url)
                
            elif action == "browser_click":
                selector = params.get("selector", "")
                return await self.browser_tool.click(selector)
                
            elif action == "browser_get_text":
                selector = params.get("selector")
                return await self.browser_tool.get_text(selector)
                
            elif action == "browser_fill_form":
                selector = params.get("selector", "")
                value = params.get("value", "")
                return await self.browser_tool.fill_form(selector, value)
                
            elif action == "browser_screenshot":
                path = params.get("path")
                return await self.browser_tool.screenshot(path)
                
            elif action == "browser_extract_links":
                return await self.browser_tool.extract_links()
                
            else:
                return {
                    "success": False,
                    "error": f"Unsupported action: {action}",
                    "error_type": "UnsupportedAction"
                }
                
        except Exception as e:
            logger.error(f"Browser tool execution failed for {action}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "BrowserToolError"
            }
    
    def get_capabilities(self) -> List[ToolCapability]:
        """获取浏览器工具的所有能力"""
        return [
            ToolCapability(
                name="browser_navigate",
                description="导航到指定URL",
                parameters={ # 将parameters_schema改为parameters
                    "url": {
                        "type": "string",
                        "description": "要导航到的完整HTTP/HTTPS URL",
                        "required": True
                    }
                },
                examples=[
                    {"url": "https://www.google.com"},
                    {"url": "https://github.com/search?q=python"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="browser_click",
                description="点击页面上的指定元素",
                parameters={ # 将parameters_schema改为parameters
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器，用于定位要点击的元素",
                        "required": True
                    }
                },
                examples=[
                    {"selector": "button#submit"},
                    {"selector": "a[href='/login']"},
                    {"selector": ".search-button"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="browser_get_text",
                description="提取页面或指定元素的文本内容",
                parameters={ # 将parameters_schema改为parameters
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器，留空则提取整个页面文本",
                        "required": False
                    }
                },
                examples=[
                    {},  # 提取整页文本
                    {"selector": ".article-content"},
                    {"selector": "h1"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="browser_fill_form",
                description="填写表单字段",
                parameters={ # 将parameters_schema改为parameters
                    "selector": {
                        "type": "string",
                        "description": "表单字段的CSS选择器",
                        "required": True
                    },
                    "value": {
                        "type": "string",
                        "description": "要填入的值",
                        "required": True
                    }
                },
                examples=[
                    {"selector": "input[name='email']", "value": "test@example.com"},
                    {"selector": "#password", "value": "password123"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="browser_screenshot",
                description="截取当前页面截图",
                parameters={ # 将parameters_schema改为parameters
                    "path": {
                        "type": "string",
                        "description": "截图保存路径，留空则自动生成",
                        "required": False
                    }
                },
                examples=[
                    {},
                    {"path": "/app/output/screenshot.png"}
                ]
                # 移除 success_indicators 和 common_errors
            ),
            ToolCapability(
                name="browser_extract_links",
                description="提取页面上的所有链接",
                parameters={}, # 将parameters_schema改为parameters
                examples=[{}]
                # 移除 success_indicators 和 common_errors
            )
        ]
    
    def get_tool_type(self) -> ToolType:
        """返回工具类型"""
        return ToolType.FUNCTION # 将BROWSER改为FUNCTION
    
    async def cleanup(self):
        """清理资源"""
        await self.browser_tool.cleanup()

# 创建增强浏览器工具实例
enhanced_browser_tool = EnhancedBrowserTool() 