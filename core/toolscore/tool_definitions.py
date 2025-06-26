"""
使用结构化工具系统定义所有MCP工具
替换硬编码的工具描述，实现类型安全和自动校验
"""

from typing import Optional
from pydantic import BaseModel, Field
from .structured_tools import (
    structured_tool, action, BaseParams,
    ResearchParams, CodeExecutionParams, BrowserParams, SearchParams, FileSearchParams
)


# =========================== 深度研究工具 ===========================

@structured_tool(
    tool_id="deepsearch",
    name="网络信息研究工具", 
    description="专门执行在线信息研究和知识综合分析，不涉及工具安装和项目文件操作",
    category="research"
)
class DeepSearchTool:
    """深度研究工具的结构化定义"""
    
    @action(
        name="research",
        description="综合性研究",
        example={"query": "Python asyncio最佳实践", "max_results": 10}
    )
    def research(self, params: ResearchParams) -> str:
        """执行综合性研究"""
        pass
    
    @action(
        name="quick_research", 
        description="快速研究",
        example={"query": "机器学习基础概念", "max_results": 5}
    )
    def quick_research(self, params: ResearchParams) -> str:
        """执行快速研究"""
        pass
    
    @action(
        name="comprehensive_research",
        description="全面深入研究", 
        example={"query": "区块链技术发展趋势", "depth": "comprehensive", "max_results": 15}
    )
    def comprehensive_research(self, params: ResearchParams) -> str:
        """执行全面深入研究"""
        pass


# =========================== 微沙盒工具 ===========================

class PackageInstallParams(BaseParams):
    """包安装参数"""
    package_name: str = Field(..., description="包名")
    version: Optional[str] = Field(None, description="版本号")
    session_id: Optional[str] = Field(None, description="会话ID")


class SessionParams(BaseParams):
    """会话管理参数"""
    session_id: str = Field(..., description="会话ID")


class CleanupParams(BaseParams):
    """清理参数"""
    max_age: Optional[int] = Field(3600, description="最大年龄秒数")


@structured_tool(
    tool_id="microsandbox",
    name="MicroSandbox安全代码执行器",
    description="在安全隔离环境中执行Python代码和管理包",
    category="code_execution"
)
class MicroSandboxTool:
    """微沙盒工具的结构化定义"""
    
    @action(
        name="microsandbox_execute",
        description="执行Python代码",
        example={"code": "print('Hello'); result = 2 + 3; print(result)", "timeout": 30}
    )
    def execute(self, params: CodeExecutionParams) -> str:
        """执行Python代码"""
        pass
    
    @action(
        name="microsandbox_install_package",
        description="安装Python包",
        example={"package_name": "numpy", "version": "1.21.0"}
    )
    def install_package(self, params: PackageInstallParams) -> str:
        """安装Python包"""
        pass
    
    @action(
        name="microsandbox_list_sessions",
        description="列出活跃会话",
        example={}
    )
    def list_sessions(self, params: BaseParams) -> str:
        """列出活跃会话"""
        pass
    
    @action(
        name="microsandbox_close_session",
        description="关闭会话",
        example={"session_id": "my-session"}
    )
    def close_session(self, params: SessionParams) -> str:
        """关闭会话"""
        pass
    
    @action(
        name="microsandbox_cleanup_expired",
        description="清理过期会话",
        example={"max_age": 3600}
    )
    def cleanup_expired(self, params: CleanupParams) -> str:
        """清理过期会话"""
        pass
    
    @action(
        name="microsandbox_get_performance_stats",
        description="获取性能统计",
        example={}
    )
    def get_performance_stats(self, params: BaseParams) -> str:
        """获取性能统计"""
        pass
    
    @action(
        name="microsandbox_get_health_status",
        description="获取健康状态",
        example={}
    )
    def get_health_status(self, params: BaseParams) -> str:
        """获取健康状态"""
        pass


# =========================== 浏览器工具 ===========================

class BrowserTaskParams(BaseParams):
    """浏览器任务参数"""
    task: str = Field(..., description="自然语言任务描述")
    max_steps: Optional[int] = Field(None, description="最大执行步数")
    use_vision: Optional[bool] = Field(None, description="启用视觉理解")


class BrowserNavigateParams(BaseParams):
    """浏览器导航参数"""
    url: str = Field(..., description="目标URL")
    wait_time: Optional[int] = Field(None, description="等待时间（秒）")


class BrowserClickParams(BaseParams):
    """浏览器点击参数"""
    index: int = Field(..., description="元素索引")


class BrowserInputParams(BaseParams):
    """浏览器输入参数"""
    index: int = Field(..., description="输入框索引")
    text: str = Field(..., description="输入文本")


class BrowserExtractParams(BaseParams):
    """浏览器提取参数"""
    selector: Optional[str] = Field(None, description="CSS选择器，空则提取全部内容")


class BrowserSearchParams(BaseParams):
    """浏览器搜索参数"""
    query: str = Field(..., description="搜索查询")


@structured_tool(
    tool_id="browser_use",
    name="智能浏览器操作工具",
    description="自动化网页浏览、交互和内容提取",
    category="web_automation"
)
class BrowserTool:
    """浏览器工具的结构化定义"""
    
    @action(
        name="browser_use_execute_task",
        description="执行复杂的AI浏览器任务",
        example={"task": "打开Python官网并获取最新版本信息", "max_steps": 10, "use_vision": True}
    )
    def execute_task(self, params: BrowserTaskParams) -> str:
        """执行复杂的AI浏览器任务"""
        pass
    
    @action(
        name="browser_navigate",
        description="导航到指定URL",
        example={"url": "https://python.org", "wait_time": 3}
    )
    def navigate(self, params: BrowserNavigateParams) -> str:
        """导航到指定URL"""
        pass
    
    @action(
        name="browser_click_element",
        description="点击页面元素",
        example={"index": 0}
    )
    def click_element(self, params: BrowserClickParams) -> str:
        """点击页面元素"""
        pass
    
    @action(
        name="browser_input_text",
        description="在输入框中输入文本",
        example={"index": 0, "text": "Python tutorial"}
    )
    def input_text(self, params: BrowserInputParams) -> str:
        """在输入框中输入文本"""
        pass
    
    @action(
        name="browser_extract_content",
        description="提取页面内容",
        example={"selector": "h1, p"}
    )
    def extract_content(self, params: BrowserExtractParams) -> str:
        """提取页面内容"""
        pass
    
    @action(
        name="browser_search_google",
        description="在Google中搜索",
        example={"query": "Python asyncio tutorial"}
    )
    def search_google(self, params: BrowserSearchParams) -> str:
        """在Google中搜索"""
        pass


# =========================== 搜索工具 ===========================

class FileContentSearchParams(BaseParams):
    """文件内容搜索参数"""
    file_path: str = Field(..., description="文件路径")
    regex_pattern: str = Field(..., description="正则表达式")


class CodeDefinitionsParams(BaseParams):
    """代码定义参数"""
    file_path: Optional[str] = Field(None, description="文件路径")
    directory_path: Optional[str] = Field(None, description="目录路径")


@structured_tool(
    tool_id="mcp-search-tool",
    name="工具管理和项目文件搜索器",
    description="专门负责工具安装管理、项目内文件搜索和代码分析，不涉及在线信息研究",
    category="tool_management"
)
class SearchTool:
    """搜索工具的结构化定义"""
    
    @action(
        name="search_file_content",
        description="搜索文件内容",
        example={"file_path": "src/main.py", "regex_pattern": "def.*"}
    )
    def search_content(self, params: FileContentSearchParams) -> str:
        """搜索文件内容"""
        pass
    
    @action(
        name="list_code_definitions",
        description="列出代码定义",
        example={"directory_path": "src/"}
    )
    def list_definitions(self, params: CodeDefinitionsParams) -> str:
        """列出代码定义"""
        pass
    
    @action(
        name="analyze_tool_needs",
        description="分析任务的工具需求",
        example={"task_description": "创建数据可视化图表"}
    )
    def analyze_needs(self, params: SearchParams) -> str:
        """分析任务的工具需求"""
        pass
    
    @action(
        name="search_and_install_tools",
        description="搜索并安装新工具",
        example={"task_description": "需要处理PDF文件", "reason": "当前工具不支持PDF操作"}
    )
    def search_and_install(self, params: SearchParams) -> str:
        """搜索并安装新工具"""
        pass


# 自动注册所有工具（通过装饰器已经完成）
# 可以通过 tool_registry.get_all_tools() 获取所有注册的工具