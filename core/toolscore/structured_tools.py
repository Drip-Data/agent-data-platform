"""
结构化工具描述和自动校验系统
基于Pydantic实现类型安全的工具定义和JSON Schema自动生成
"""

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints
from pydantic import BaseModel, Field, ValidationError, validator
import jsonschema
from functools import wraps

logger = logging.getLogger(__name__)


class ToolAction(BaseModel):
    """工具动作的结构化定义"""
    name: str = Field(..., description="动作名称")
    description: str = Field(..., description="动作描述")
    parameters: Type[BaseModel] = Field(..., description="参数模型类")
    example: Optional[Dict[str, Any]] = Field(None, description="使用示例")
    
    class Config:
        arbitrary_types_allowed = True


class ToolDefinition(BaseModel):
    """工具的结构化定义"""
    id: str = Field(..., description="工具唯一标识符")
    name: str = Field(..., description="工具显示名称")
    description: str = Field(..., description="工具功能描述")
    category: str = Field(..., description="工具分类")
    actions: List[ToolAction] = Field(..., description="支持的动作列表")
    version: str = Field(default="1.0.0", description="工具版本")
    
    def get_action_names(self) -> List[str]:
        """获取所有动作名称"""
        return [action.name for action in self.actions]
    
    def get_action(self, action_name: str) -> Optional[ToolAction]:
        """根据名称获取动作"""
        for action in self.actions:
            if action.name == action_name:
                return action
        return None
    
    def to_llm_description(self) -> str:
        """生成面向LLM的工具描述"""
        action_descriptions = []
        for action in self.actions:
            schema = action.parameters.schema()
            params_desc = self._format_parameters(schema.get('properties', {}))
            example = action.example or {}
            
            action_descriptions.append(
                f"    • {action.name}: {action.description}\n"
                f"      参数: {params_desc}\n"
                f"      示例: {json.dumps(example, ensure_ascii=False)}"
            )
        
        return (
            f"- **{self.id}** ({self.name}): {self.description}\n"
            f"  📋 可用操作:\n" + "\n".join(action_descriptions)
        )
    
    def _format_parameters(self, properties: Dict[str, Any]) -> str:
        """格式化参数描述"""
        if not properties:
            return "无参数"
        
        param_strs = []
        for name, prop in properties.items():
            required = prop.get('required', False)
            desc = prop.get('description', '')
            param_type = prop.get('type', 'any')
            required_mark = '(必需)' if required else '(可选)'
            param_strs.append(f"{name}: {desc}{required_mark}")
        
        return ', '.join(param_strs)


class LLMRequest(BaseModel):
    """LLM请求的结构化定义"""
    thinking: str = Field(..., description="思考过程")
    action: str = Field(..., description="要执行的动作")
    tool_id: str = Field(..., description="工具标识符")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="动作参数")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="置信度")


class ToolValidationError(Exception):
    """工具校验错误"""
    def __init__(self, message: str, tool_id: str = None, action: str = None):
        self.tool_id = tool_id
        self.action = action
        super().__init__(message)


class StructuredToolRegistry:
    """结构化工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._action_schemas: Dict[str, Dict[str, jsonschema.protocols.Validator]] = {}
        
    def register_tool(self, tool_def: ToolDefinition):
        """注册工具"""
        self._tools[tool_def.id] = tool_def
        self._build_action_schemas(tool_def)
        logger.info(f"注册工具: {tool_def.id} - {tool_def.name}")
    
    def _build_action_schemas(self, tool_def: ToolDefinition):
        """构建动作的JSON Schema"""
        self._action_schemas[tool_def.id] = {}
        for action in tool_def.actions:
            schema = action.parameters.schema()
            validator = jsonschema.Draft7Validator(schema)
            self._action_schemas[tool_def.id][action.name] = validator
    
    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(tool_id)
    
    def get_all_tools(self) -> List[ToolDefinition]:
        """获取所有工具"""
        return list(self._tools.values())
    
    def get_all_tool_ids(self) -> List[str]:
        """获取所有工具ID列表"""
        return list(self._tools.keys())
    
    def validate_request(self, request: LLMRequest) -> Dict[str, Any]:
        """
        预校验LLM请求
        在发送到实际工具前进行结构化校验
        """
        try:
            # 1. 基础请求格式校验
            if not isinstance(request, LLMRequest):
                request = LLMRequest(**request)
            
            # 2. 工具存在性校验
            tool_def = self.get_tool(request.tool_id)
            if not tool_def:
                raise ToolValidationError(
                    f"未知工具: {request.tool_id}",
                    tool_id=request.tool_id
                )
            
            # 3. 动作存在性校验
            action = tool_def.get_action(request.action)
            if not action:
                suggested_action = self._suggest_action(tool_def, request.action)
                raise ToolValidationError(
                    f"工具 {request.tool_id} 不支持动作 {request.action}。"
                    f"支持的动作: {tool_def.get_action_names()}。"
                    f"建议使用: {suggested_action}",
                    tool_id=request.tool_id,
                    action=request.action
                )
            
            # 4. 参数Schema校验
            validator = self._action_schemas[request.tool_id][request.action]
            try:
                validator.validate(request.parameters)
            except jsonschema.ValidationError as e:
                raise ToolValidationError(
                    f"参数校验失败: {e.message}",
                    tool_id=request.tool_id,
                    action=request.action
                )
            
            logger.debug(f"✅ 请求校验通过: {request.tool_id}.{request.action}")
            return {
                "valid": True,
                "tool_def": tool_def,
                "action_def": action,
                "validated_request": request
            }
            
        except ToolValidationError:
            raise
        except Exception as e:
            raise ToolValidationError(f"校验过程发生错误: {str(e)}")
    
    def _suggest_action(self, tool_def: ToolDefinition, wrong_action: str) -> str:
        """智能建议正确的动作"""
        import difflib
        action_names = tool_def.get_action_names()
        matches = difflib.get_close_matches(wrong_action, action_names, n=1, cutoff=0.6)
        return matches[0] if matches else action_names[0]
    
    def auto_correct_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        自动纠正请求
        尝试修复常见的工具-动作错配问题
        """
        try:
            request = LLMRequest(**request_data)
            validation_result = self.validate_request(request)
            return validation_result["validated_request"].dict()
        except ToolValidationError as e:
            if e.tool_id and e.action:
                # 尝试自动纠正
                corrected = self._try_auto_correct(request_data, e)
                if corrected:
                    logger.info(f"自动纠正: {e.action} -> {corrected['action']}")
                    return corrected
            
            # 如果无法纠正，重新抛出异常
            raise ToolValidationError(f"无法自动纠正请求: {str(e)}", e.tool_id, e.action)
    
    def _try_auto_correct(self, request_data: Dict[str, Any], error: ToolValidationError) -> Optional[Dict[str, Any]]:
        """尝试自动纠正错误"""
        # 常见错配纠正规则 - 包含动作和参数映射
        correction_rules = {
            "mcp-deepsearch": {
                "search_and_install_tools": {
                    "action": "research",
                    "param_mapping": {"task_description": "query"}
                },
                "analyze_tool_needs": {
                    "action": "research", 
                    "param_mapping": {"task_description": "query"}
                },
                "search": {
                    "action": "research",
                    "param_mapping": {"task_description": "query"}
                }
            },
            "mcp-search-tool": {
                "research": {
                    "action": "search_and_install_tools",
                    "param_mapping": {"query": "task_description"}
                },
                "deepsearch": {
                    "action": "search_and_install_tools",
                    "param_mapping": {"query": "task_description"}
                }
            }
        }
        
        tool_id = error.tool_id
        wrong_action = error.action
        
        if tool_id in correction_rules and wrong_action in correction_rules[tool_id]:
            correction_config = correction_rules[tool_id][wrong_action]
            corrected_action = correction_config["action"]
            param_mapping = correction_config.get("param_mapping", {})
            
            corrected_request = request_data.copy()
            corrected_request["action"] = corrected_action
            
            # 修正参数映射
            if param_mapping and "parameters" in corrected_request:
                old_params = corrected_request["parameters"].copy()
                new_params = {}
                
                for old_key, new_key in param_mapping.items():
                    if old_key in old_params:
                        new_params[new_key] = old_params[old_key]
                
                # 保留没有映射的参数
                for key, value in old_params.items():
                    if key not in param_mapping:
                        new_params[key] = value
                
                corrected_request["parameters"] = new_params
            
            try:
                result = self.validate_request(LLMRequest(**corrected_request))
                logger.debug(f"自动纠正成功: {wrong_action} -> {corrected_action}")
                return result["validated_request"].dict()
            except Exception as e:
                logger.debug(f"自动纠正失败: {e}")
                pass
        
        return None
    
    def generate_llm_tools_description(self) -> str:
        """生成面向LLM的工具描述"""
        if not self._tools:
            return "当前无可用工具"
        
        descriptions = []
        for tool in self._tools.values():
            descriptions.append(tool.to_llm_description())
        
        return "# 已注册的工具\n" + "\n".join(descriptions)


# 全局工具注册表实例
tool_registry = StructuredToolRegistry()


def structured_tool(
    tool_id: str,
    name: str,
    description: str,
    category: str = "general",
    version: str = "1.0.0"
):
    """
    装饰器：注册结构化工具
    
    使用示例：
    @structured_tool("mcp-deepsearch", "网络信息研究工具", "专门执行在线信息研究", "research")
    class DeepSearchTool:
        @action("research", "综合性研究")
        def research(self, params: ResearchParams) -> str:
            pass
    """
    def decorator(cls):
        # 收集动作定义
        actions = []
        for method_name in dir(cls):
            method = getattr(cls, method_name)
            if hasattr(method, '_action_metadata'):
                metadata = method._action_metadata
                actions.append(ToolAction(
                    name=metadata['name'],
                    description=metadata['description'],
                    parameters=metadata['parameters'],
                    example=metadata.get('example')
                ))
        
        # 创建工具定义
        tool_def = ToolDefinition(
            id=tool_id,
            name=name,
            description=description,
            category=category,
            actions=actions,
            version=version
        )
        
        # 注册到全局注册表
        tool_registry.register_tool(tool_def)
        
        # 在类上添加元数据
        cls._tool_definition = tool_def
        cls._tool_id = tool_id
        
        return cls
    
    return decorator


def action(name: str, description: str, example: Dict[str, Any] = None):
    """
    装饰器：定义工具动作
    
    使用示例：
    @action("research", "综合性研究", {"question": "Python最佳实践"})
    def research(self, params: ResearchParams) -> str:
        pass
    """
    def decorator(func):
        # 获取参数类型
        type_hints = get_type_hints(func)
        params_type = type_hints.get('params', BaseModel)
        
        # 存储动作元数据
        func._action_metadata = {
            'name': name,
            'description': description,
            'parameters': params_type,
            'example': example
        }
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# 常用参数模型基类
class BaseParams(BaseModel):
    """基础参数模型"""
    class Config:
        extra = "forbid"  # 禁止额外字段


# 预定义的常用参数模型
class ResearchParams(BaseParams):
    """研究类动作参数"""
    question: str = Field(..., description="研究问题或查询")
    initial_queries: Optional[list] = Field(None, description="初始查询列表")
    max_loops: Optional[int] = Field(None, description="最大循环次数")
    reasoning_model: Optional[str] = Field(None, description="推理模型")
    topic_focus: Optional[str] = Field(None, description="主题焦点")
    # 保持向后兼容
    query: Optional[str] = Field(None, description="研究查询内容（向后兼容）")
    max_results: Optional[int] = Field(10, description="最大结果数量")
    depth: Optional[str] = Field("normal", description="研究深度: quick, normal, comprehensive")


class CodeExecutionParams(BaseParams):
    """代码执行参数"""
    code: str = Field(..., description="要执行的Python代码")
    session_id: Optional[str] = Field(None, description="会话ID")
    timeout: Optional[int] = Field(30, description="超时时间(秒)")


class BrowserParams(BaseParams):
    """浏览器操作参数"""
    url: str = Field(..., description="目标URL")
    wait_time: Optional[int] = Field(3, description="等待时间(秒)")


class SearchParams(BaseParams):
    """搜索相关参数"""
    task_description: str = Field(..., description="任务描述")
    reason: Optional[str] = Field(None, description="需要原因")


class FileSearchParams(BaseParams):
    """文件搜索参数"""
    file_path: Optional[str] = Field(None, description="文件路径")
    directory_path: Optional[str] = Field(None, description="目录路径")
    regex_pattern: Optional[str] = Field(None, description="正则表达式模式")


def get_all_structured_tools() -> List[ToolDefinition]:
    """
    获取所有已注册的结构化工具
    返回工具定义列表，用于Schema管理器获取版本信息
    """
    return tool_registry.get_all_tools()


def get_structured_tool_schemas() -> Dict[str, Dict[str, Any]]:
    """
    获取所有工具的Schema信息
    返回包含工具ID和对应Schema的字典
    """
    schemas = {}
    for tool in tool_registry.get_all_tools():
        tool_schema = {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "version": tool.version,
            "actions": {}
        }
        
        for action in tool.actions:
            action_schema = action.parameters.schema()
            tool_schema["actions"][action.name] = {
                "description": action.description,
                "schema": action_schema,
                "example": action.example
            }
        
        schemas[tool.id] = tool_schema
    
    return schemas


def get_tool_registry() -> StructuredToolRegistry:
    """
    获取全局工具注册表实例
    """
    return tool_registry