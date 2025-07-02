#!/usr/bin/env python3
"""
Deepsearch MCP Server
专业级深度搜索服务，通过MCP协议与toolscore通信
"""

import asyncio
import logging
import os
import socket
from typing import Dict, Any, List
from uuid import uuid4

from core.toolscore.interfaces import ToolCapability, ToolType
from core.toolscore.mcp_server import MCPServer
from mcp_servers.deepsearch_server.deepsearch_tool_unified import DeepSearchToolUnified
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

def find_free_port(start_port, end_port=None):
    """查找一个空闲端口"""
    if end_port is None:
        end_port = start_port + 100  # 限制搜索范围
    
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('localhost', port))
                logger.info(f"找到空闲端口: {port}")
                return port
        except OSError:
            # 端口被占用，继续尝试下一个
            continue
    
    raise IOError(f"No free ports found in range {start_port}-{end_port}")

from core.unified_tool_manager import UnifiedToolManager

class DeepSearchMCPServer:
    """深度搜索MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager, tool_manager: UnifiedToolManager):
        # 获取LLM配置并初始化工具
        llm_config = config_manager.get_llm_config()
        
        # 确保GEMINI_API_KEY环境变量设置
        if llm_config.get('gemini', {}).get('api_key'):
            os.environ['GEMINI_API_KEY'] = llm_config['gemini']['api_key']
            logger.info("✅ GEMINI_API_KEY set from config")
        
        self.deepsearch_tool = DeepSearchToolUnified(llm_config, tool_manager=tool_manager)
        self.server_name = "deepsearch_server"
        self.server_id = "deepsearch"
        self.config_manager = config_manager
        self.tool_manager = tool_manager
        
        # 从配置中获取端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查是否有动态分配的端口
        dynamic_port = os.getenv('DEEPSEARCH_SERVER_PORT')
        if dynamic_port:
            deepsearch_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {deepsearch_port}")
        else:
            # 使用默认端口或从配置文件获取
            default_port = ports_config.get('mcp_servers', {}).get('deepsearch_server', {}).get('port', 8086)
            try:
                deepsearch_port = find_free_port(default_port)
                if deepsearch_port != default_port:
                    logger.warning(f"端口 {default_port} 被占用，使用新端口 {deepsearch_port}")
                else:
                    logger.info(f"使用配置文件端口: {deepsearch_port}")
            except IOError as e:
                logger.error(f"无法找到空闲端口: {e}")
                raise
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']

        # 监听地址设置
        listen_host = os.getenv("DEEPSEARCH_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("DEEPSEARCH_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{deepsearch_port}/mcp"
        self._listen_host = listen_host
        self._listen_port = deepsearch_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')

        # 动作分发映射
        self._action_handlers = {
            "research": self._research_wrapper,
            "quick_research": self._quick_research_wrapper,
            "comprehensive_research": self._comprehensive_research_wrapper,
            "get_cache_stats": self._get_cache_stats,
            "clear_cache": self._clear_cache,
            "get_health_status": self._get_health_status,
            "get_optimization_stats": self._get_optimization_stats,
        }
        self._validate_actions()

    def _validate_actions(self):
        """验证所有在配置中声明的动作都有对应的处理函数。"""
        try:
            declared_actions = set(self.tool_manager.get_tool_actions(self.server_name))
            implemented_actions = set(self._action_handlers.keys())

            missing = declared_actions - implemented_actions
            if missing:
                raise NotImplementedError(f"服务器 {self.server_name} 在配置中声明了动作 {missing}，但没有实现对应的处理函数！")

            extra = implemented_actions - declared_actions
            if extra:
                logging.warning(f"服务器 {self.server_name} 实现了多余的动作 {extra}，这些动作未在配置中声明。")
            
            logger.info(f"✅ {self.server_name} 的所有动作已验证。")
        except Exception as e:
            logger.error(f"动作验证失败: {e}", exc_info=True)
            raise

    async def _research_wrapper(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        question = parameters.get("question") or parameters.get("query") or parameters.get("task_description", "")
        if not question:
            return {"success": False, "error_message": "Question parameter is required"}
        kwargs = {k: v for k, v in parameters.items() if k not in ["question", "query", "task_description"]}
        return await self.deepsearch_tool.research(question, **kwargs)

    async def _quick_research_wrapper(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        question = parameters.get("question") or parameters.get("query") or parameters.get("task_description", "")
        if not question:
            return {"success": False, "error_message": "Question parameter is required"}
        return await self.deepsearch_tool.quick_research(question)

    async def _comprehensive_research_wrapper(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        question = parameters.get("question") or parameters.get("query") or parameters.get("task_description", "")
        if not question:
            return {"success": False, "error_message": "Question parameter is required"}
        topic_focus = parameters.get("topic_focus")
        return await self.deepsearch_tool.comprehensive_research(question, topic_focus)

    async def _get_cache_stats(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        cache_stats = self.deepsearch_tool.cache.get_cache_stats()
        return {"success": True, "data": cache_stats}

    async def _clear_cache(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        await self.deepsearch_tool.cache.clear_cache()
        return {"success": True, "data": {"message": "Cache cleared successfully"}}

    async def _get_health_status(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        health_status = self.deepsearch_tool.get_health_status()
        return {"success": True, "data": health_status}

    async def _get_optimization_stats(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        optimization_stats = self.deepsearch_tool.get_optimization_stats()
        return {"success": True, "data": optimization_stats}

    def get_capabilities(self) -> List[ToolCapability]:
        """获取深度搜索工具的所有能力"""
        tool_info = self.tool_manager.get_tool_info(self.server_name)
        capabilities = []
        for action_name, action_def in tool_info.get('actions', {}).items():
            capabilities.append(ToolCapability(
                name=action_name,
                description=action_def.get('description', ''),
                parameters=action_def.get('parameters', {}),
                examples=action_def.get('examples', [])
            ))
        return capabilities
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        logger.info(f"Executing DeepSearch tool action: {action} with params: {parameters}")
        handler = self._action_handlers.get(action)
        if handler:
            try:
                result = await handler(parameters)
                # 统一包装返回格式
                return {
                    "success": result.get("success", False),
                    "data": result.get("output", result.get("data", {})),
                    "error_message": result.get("error_message", ""),
                    "error_type": result.get("error_type", "")
                }
            except Exception as e:
                import traceback
                error_details = {
                    "exception_type": type(e).__name__,
                    "exception_message": str(e) if str(e) else "No error message provided",
                    "action": action,
                    "parameters": {k: "***" if "key" in k.lower() or "token" in k.lower() else str(v)[:100] for k, v in parameters.items()},
                    "traceback": traceback.format_exc()[-500:],
                    "structured": True
                }
                error_message = f"DeepSearch tool internal error: {str(e) or 'Unknown internal error'}"
                logger.error(f"DeepSearch tool execution failed for {action}: {error_message}", exc_info=True)
                return {"success": False, "data": None, "error_message": error_message, "error_type": "InternalError", "error_details": error_details}
        else:
            return {"success": False, "data": None, "error_message": f"Unsupported action: {action}", "error_type": "UnsupportedAction"}

    async def run(self):
        """启动MCP服务器"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="专业级深度搜索和研究工具服务器，基于LangGraph实现的多轮迭代搜索代理",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 设置监听地址
        os.environ["DEEPSEARCH_BIND_HOST"] = self._listen_host
        await mcp_server.start()

async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 初始化ConfigManager和UnifiedToolManager
    from core.config_manager import ConfigManager
    from core.unified_tool_manager import UnifiedToolManager
    config_manager = ConfigManager()
    tool_manager = UnifiedToolManager()
    
    server = DeepSearchMCPServer(config_manager, tool_manager)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())