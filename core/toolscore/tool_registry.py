import os
import json
import logging
import time
from typing import Dict, Any, Optional, List, Union, Callable, Awaitable
import importlib.util
import inspect
import asyncio
from functools import wraps

from core.interfaces import LocalToolSpec, LocalToolInterface
from core.persistence_service import PersistenceService
from core.config_service import ConfigService


logger = logging.getLogger(__name__)

# 工具函数类型别名
ToolFunc = Callable[..., Any]
AsyncToolFunc = Callable[..., Awaitable[Any]]

def tool_function(name: str, description: str, version: str = "1.0.0", **metadata):
    """用于装饰Python函数以将其注册为工具的装饰器"""
    def decorator(func):
        # 保持函数签名不变
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # 添加工具元数据
        wrapper.__tool_spec__ = {
            "name": name,
            "description": description,
            "version": version,
            "metadata": metadata
        }
        return wrapper
    return decorator

class ToolRegistry:
    """工具注册表：管理本地工具的注册、发现和执行"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.config_service = ConfigService()
        self.config = self.config_service.get_config().tools
        self.persistence = PersistenceService()

        # 工具字典：{tool_id: tool_spec}
        self.tools: Dict[str, LocalToolSpec] = {}

        # 工具实例字典：{tool_id: tool_instance}
        self.tool_instances: Dict[str, LocalToolInterface] = {}

        # 工具函数字典：{tool_id: function}
        self.tool_functions: Dict[str, Union[ToolFunc, AsyncToolFunc]] = {}

        # 初始化注册表
        self._initialized = True
        # asyncio.create_task(self._load_tools()) # Defer loading to an explicit call or after event loop starts

        logger.info("工具注册表初始化完成")

    async def load_tools_async(self):
        """Asynchronously load tools. Call this after event loop starts."""
        if not hasattr(self, '_tools_loaded') or not self._tools_loaded:
            await self._load_tools()
            self._tools_loaded = True


    async def _load_tools(self):
        """从持久化存储加载工具配置"""
        try:
            # 加载已保存的工具配置
            tool_configs = await self.persistence.list_tool_configs()
            for config in tool_configs:
                tool_id = config.get("_id")
                if tool_id:
                    try:
                        tool_spec = LocalToolSpec.from_dict(config)
                        self.tools[tool_id] = tool_spec
                        logger.debug(f"从存储加载工具: {tool_id}")
                    except Exception as e:
                        logger.error(f"从字典创建ToolSpec失败 {tool_id}: {e}, data: {config}")


            # 加载工具目录中的工具
            registry_path = self.config.registry_path
            if os.path.exists(registry_path) and os.path.isdir(registry_path):
                self._load_tools_from_directory(registry_path)
            else:
                logger.warning(f"工具注册表路径不存在或不是目录: {registry_path}")


            logger.info(f"工具加载完成，共 {len(self.tools)} 个工具可用")
        except Exception as e:
            logger.error(f"加载工具配置失败: {e}")

    def _load_tools_from_directory(self, directory: str):
        """从目录加载工具模块"""
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py') and not file.startswith('_'):
                    try:
                        file_path = os.path.join(root, file)
                        module_name = f"tools_module_{file[:-3]}" # Ensure unique module name

                        # 动态加载模块
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            # Add module to sys.modules before exec_module to handle circular imports if any
                            # and to make it findable by other imports within the loaded module
                            # sys.modules[module_name] = module # Be cautious with this globally
                            spec.loader.exec_module(module)

                            # 查找工具类
                            for name, obj in inspect.getmembers(module):
                                if (inspect.isclass(obj) and
                                    issubclass(obj, LocalToolInterface) and
                                    obj != LocalToolInterface):
                                    try:
                                        tool_instance = obj() # Assuming constructor takes no args
                                        self.register_tool_instance(tool_instance) # This is async, but called from sync
                                        logger.debug(f"从文件加载工具类: {tool_instance.tool_spec.tool_id}")
                                    except Exception as e:
                                        logger.error(f"初始化工具类失败 {name} from {file}: {e}")

                            # 查找工具函数
                            for name, obj in inspect.getmembers(module):
                                if inspect.isfunction(obj) and hasattr(obj, '__tool_spec__'):
                                    try:
                                        self.register_tool_function(obj) # This is async
                                        logger.debug(f"从文件加载工具函数: {obj.__name__} from {file}")
                                    except Exception as e:
                                        logger.error(f"注册工具函数失败 {obj.__name__} from {file}: {e}")
                    except Exception as e:
                        logger.error(f"加载模块失败 {file}: {e}")

    def register_tool_instance(self, tool: LocalToolInterface) -> bool:
        """注册工具实例 (can be called from sync context, schedules async save)"""
        try:
            tool_spec = tool.tool_spec
            tool_id = tool_spec.tool_id

            # 更新注册表
            self.tools[tool_id] = tool_spec
            self.tool_instances[tool_id] = tool

            # 保存到持久化存储
            asyncio.create_task(self._save_tool_spec(tool_spec))

            logger.info(f"工具实例注册成功: {tool_id}")
            return True
        except Exception as e:
            logger.error(f"工具实例注册失败: {e}")
            return False

    def register_tool_function(self, func: Union[ToolFunc, AsyncToolFunc]) -> bool:
        """注册工具函数 (can be called from sync context, schedules async save)"""
        if not hasattr(func, '__tool_spec__'):
            logger.error(f"函数 {func.__name__} 不是有效的工具函数，缺少 __tool_spec__")
            return False

        try:
            # 从函数元数据创建工具规范
            tool_meta = getattr(func, '__tool_spec__')
            func_name = func.__name__

            # 生成工具ID
            module_name = func.__module__
            # Ensure module_name is filesystem-friendly if used in paths, though here it's for ID
            safe_module_name = module_name.replace('.', '_')
            tool_id = f"{safe_module_name}_{func_name}"


            # 检查参数并创建工具规范
            sig = inspect.signature(func)
            parameters_spec = {}

            for name, param in sig.parameters.items():
                if name == 'self':  # 跳过类方法的self参数
                    continue

                param_type_str = "string"  # 默认类型
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == int:
                        param_type_str = "integer"
                    elif param.annotation == float:
                        param_type_str = "number"
                    elif param.annotation == bool:
                        param_type_str = "boolean"
                    elif param.annotation == list or param.annotation == List:
                        param_type_str = "array"
                    elif param.annotation == dict or param.annotation == Dict:
                        param_type_str = "object"
                    # Add more type mappings if needed

                parameters_spec[name] = {
                    "type": param_type_str,
                    "description": f"{name} parameter", # Placeholder description
                    "required": param.default == inspect.Parameter.empty
                }
                if param.default != inspect.Parameter.empty:
                    parameters_spec[name]["default"] = param.default


            # 创建工具规范
            tool_spec = LocalToolSpec(
                tool_id=tool_id,
                name=tool_meta.get("name", func_name),
                description=tool_meta.get("description", inspect.getdoc(func) or ""),
                version=tool_meta.get("version", "1.0.0"),
                actions=[{
                    "name": "execute", # Default action name for functions
                    "description": tool_meta.get("description", inspect.getdoc(func) or ""),
                    "parameters": parameters_spec
                }],
                type="function",
                metadata=tool_meta.get("metadata", {})
            )

            # 更新注册表
            self.tools[tool_id] = tool_spec
            self.tool_functions[tool_id] = func

            # 保存到持久化存储
            asyncio.create_task(self._save_tool_spec(tool_spec))

            logger.info(f"工具函数注册成功: {tool_id}")
            return True
        except Exception as e:
            logger.error(f"工具函数注册失败 {func.__name__}: {e}")
            return False

    async def _save_tool_spec(self, tool_spec: LocalToolSpec) -> bool:
        """保存工具规范到持久化存储"""
        try:
            return await self.persistence.save_tool_config(
                tool_spec.tool_id,
                tool_spec.to_dict()
            )
        except Exception as e:
            logger.error(f"保存工具配置失败 {tool_spec.tool_id}: {e}")
            return False

    async def unregister_tool(self, tool_id: str) -> bool:
        """注销工具"""
        if tool_id not in self.tools:
            return False

        try:
            # 从注册表移除
            tool_spec = self.tools.pop(tool_id, None)

            # 如果有实例，调用shutdown方法并移除
            if tool_id in self.tool_instances:
                try:
                    tool_instance = self.tool_instances.pop(tool_id)
                    if hasattr(tool_instance, 'shutdown') and asyncio.iscoroutinefunction(tool_instance.shutdown):
                        await tool_instance.shutdown()
                    elif hasattr(tool_instance, 'shutdown'):
                        tool_instance.shutdown() # type: ignore
                except Exception as e:
                    logger.warning(f"关闭工具实例失败 {tool_id}: {e}")

            # 移除工具函数
            self.tool_functions.pop(tool_id, None)

            # 从持久化存储中删除
            await self.persistence.storage.delete("tool_configs", tool_id)

            logger.info(f"工具注销成功: {tool_id}")
            return True
        except Exception as e:
            logger.error(f"工具注销失败 {tool_id}: {e}")
            # 恢复工具规范
            if tool_spec:
                self.tools[tool_id] = tool_spec
            return False

    async def get_tool(self, tool_id: str) -> Optional[LocalToolSpec]:
        """获取工具规范"""
        return self.tools.get(tool_id)

    async def list_tools(self, filter_type: Optional[str] = None) -> List[LocalToolSpec]:
        """列出所有工具，可选按类型筛选"""
        if filter_type:
            return [tool for tool in self.tools.values() if tool.type == filter_type]
        return list(self.tools.values())

    async def search_tools(self, query: str) -> List[LocalToolSpec]:
        """按关键词搜索工具"""
        query_lower = query.lower()
        results = []

        for tool in self.tools.values():
            # 匹配名称、描述和元数据
            if (query_lower in tool.name.lower() or
                query_lower in tool.description.lower() or
                any(query_lower in str(v).lower() for v in tool.metadata.values())):
                results.append(tool)

        return results

    async def execute_tool(self, tool_id: str, action: str,
                                  parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具动作"""
        start_time = time.time()

        try:
            # 检查工具是否存在
            if tool_id not in self.tools:
                return {
                    "success": False,
                    "error": f"工具不存在: {tool_id}",
                    "execution_time": time.time() - start_time
                }

            # 获取工具规范
            tool_spec = self.tools[tool_id]

            # 执行不同类型的工具
            if tool_id in self.tool_instances:
                # 使用工具实例执行
                tool_instance = self.tool_instances[tool_id]
                result = await tool_instance.execute(action, parameters)
            elif tool_id in self.tool_functions:
                # 使用工具函数执行
                func = self.tool_functions[tool_id]
                if action != "execute": # Assuming function tools have a default 'execute' action
                    return {
                        "success": False,
                        "error": f"函数工具只支持'execute'动作，不支持: {action}",
                        "execution_time": time.time() - start_time
                    }

                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(**parameters)
                else:
                    # 在线程池中执行同步函数
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, lambda: func(**parameters)
                    )

                # 包装结果
                if not isinstance(result, dict):
                    result = {"result": result}

                # 确保成功标志
                if "success" not in result: # Assume success if not specified and no error
                    result["success"] = True
            else:
                # 工具类型不支持直接执行
                return {
                    "success": False,
                    "error": f"不支持的工具类型或工具未正确加载: {tool_spec.type}",
                    "execution_time": time.time() - start_time
                }

            # 添加执行时间
            if isinstance(result, dict):
                 result["execution_time"] = time.time() - start_time
            return result
        except Exception as e:
            logger.error(f"工具执行失败 {tool_id}.{action}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"执行错误: {str(e)}",
                "execution_time": time.time() - start_time
            }

    async def close(self):
        """关闭工具注册表及所有工具实例"""
        for tool_id, tool_instance in list(self.tool_instances.items()):
            try:
                if hasattr(tool_instance, 'shutdown') and asyncio.iscoroutinefunction(tool_instance.shutdown):
                    await tool_instance.shutdown()
                elif hasattr(tool_instance, 'shutdown'):
                    tool_instance.shutdown() # type: ignore
                logger.debug(f"工具实例关闭: {tool_id}")
            except Exception as e:
                logger.warning(f"关闭工具实例失败 {tool_id}: {e}")

        self.tool_instances.clear()
        logger.info("工具注册表关闭")