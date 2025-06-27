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
from .deepsearch_tool_unified import DeepSearchToolUnified
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

class DeepSearchMCPServer:
    """深度搜索MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager):
        # 获取LLM配置并初始化工具
        llm_config = config_manager.get_llm_config()
        
        # 确保GEMINI_API_KEY环境变量设置
        if llm_config.get('gemini', {}).get('api_key'):
            os.environ['GEMINI_API_KEY'] = llm_config['gemini']['api_key']
            logger.info("✅ GEMINI_API_KEY set from config")
        
        self.deepsearch_tool = DeepSearchToolUnified(llm_config)
        self.server_name = "deepsearch_server"
        self.server_id = "deepsearch"
        self.config_manager = config_manager
        
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
        
    def get_capabilities(self) -> List[ToolCapability]:
        """获取深度搜索工具的所有能力"""
        capabilities_data = self.deepsearch_tool.get_capabilities()
        
        capabilities = []
        for cap_data in capabilities_data:
            capability = ToolCapability(
                name=cap_data["name"],
                description=cap_data["description"],
                parameters=cap_data["parameters"],
                examples=cap_data.get("examples", [])
            )
            capabilities.append(capability)
        
        return capabilities
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        try:
            logger.info(f"Executing DeepSearch tool action: {action} with params: {parameters}")

            result = {}
            if action == "research":
                # 支持多种参数名称：question, query, task_description
                question = parameters.get("question") or parameters.get("query") or parameters.get("task_description", "")
                if not question:
                    return {
                        "success": False,
                        "data": None,
                        "error_message": "Question parameter is required (use 'question', 'query', or 'task_description')",
                        "error_type": "InvalidParameters"
                    }
                
                # 获取可选参数
                kwargs = {}
                if "initial_queries" in parameters:
                    kwargs["initial_queries"] = parameters["initial_queries"]
                if "max_loops" in parameters:
                    kwargs["max_loops"] = parameters["max_loops"]
                if "reasoning_model" in parameters:
                    kwargs["reasoning_model"] = parameters["reasoning_model"]
                
                result = await self.deepsearch_tool.research(question, **kwargs)
                
            elif action == "quick_research":
                # 支持多种参数名称：question, query, task_description
                question = parameters.get("question") or parameters.get("query") or parameters.get("task_description", "")
                if not question:
                    return {
                        "success": False,
                        "data": None,
                        "error_message": "Question parameter is required (use 'question', 'query', or 'task_description')",
                        "error_type": "InvalidParameters"
                    }
                
                result = await self.deepsearch_tool.quick_research(question)
                
            elif action == "comprehensive_research":
                # 支持多种参数名称：question, query, task_description
                question = parameters.get("question") or parameters.get("query") or parameters.get("task_description", "")
                if not question:
                    return {
                        "success": False,
                        "data": None,
                        "error_message": "Question parameter is required (use 'question', 'query', or 'task_description')",
                        "error_type": "InvalidParameters"
                    }
                
                topic_focus = parameters.get("topic_focus")
                result = await self.deepsearch_tool.comprehensive_research(question, topic_focus)
                
            elif action == "get_cache_stats":
                # 获取缓存统计信息
                cache_stats = self.deepsearch_tool.cache.get_cache_stats()
                return {
                    "success": True,
                    "data": cache_stats,
                    "error_message": "",
                    "error_type": ""
                }
                
            elif action == "clear_cache":
                # 清空缓存
                await self.deepsearch_tool.cache.clear_cache()
                return {
                    "success": True,
                    "data": {"message": "Cache cleared successfully"},
                    "error_message": "",
                    "error_type": ""
                }
                
            elif action == "get_health_status":
                # 获取系统健康状态
                health_status = self.deepsearch_tool.get_health_status()
                return {
                    "success": True,
                    "data": health_status,
                    "error_message": "",
                    "error_type": ""
                }
                
            elif action == "get_optimization_stats":
                # 获取优化统计信息
                optimization_stats = self.deepsearch_tool.get_optimization_stats()
                return {
                    "success": True,
                    "data": optimization_stats,
                    "error_message": "",
                    "error_type": ""
                }
                
            else:
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"Unsupported action: {action}. Available actions: research, quick_research, comprehensive_research, get_cache_stats, clear_cache, get_health_status, get_optimization_stats",
                    "error_type": "UnsupportedAction"
                }

            return {
                "success": result.get("success", False),
                "data": result.get("output", {}),
                "error_message": result.get("error_message", ""),
                "error_type": result.get("error_type", "")
            }
                
        except Exception as e:
            import traceback
            
            # 🔧 优化：提供结构化的错误信息
            error_details = {
                "exception_type": type(e).__name__,
                "exception_message": str(e) if str(e) else "No error message provided",
                "action": action,
                "parameters": {k: "***" if "key" in k.lower() or "token" in k.lower() else str(v)[:100] 
                             for k, v in parameters.items()},  # 隐藏敏感信息但保留参数结构
                "traceback": traceback.format_exc()[-500:],  # 只保留最后500字符的堆栈信息
                "structured": True  # 标记为结构化错误响应
            }
            
            # 根据异常类型提供更具体的错误信息
            if isinstance(e, (ConnectionError, TimeoutError)):
                error_message = f"网络连接问题: {str(e) or '连接超时或服务不可达'}"
                error_type = "NetworkError"
            elif isinstance(e, ValueError):
                error_message = f"参数值错误: {str(e) or '提供的参数值不符合预期格式'}"
                error_type = "ParameterError"
            elif isinstance(e, KeyError):
                error_message = f"缺少必需的配置或参数: {str(e) or '配置项缺失'}"
                error_type = "ConfigurationError"
            elif "api" in str(e).lower() or "key" in str(e).lower():
                error_message = f"API调用失败: {str(e) or 'API密钥无效或服务不可用'}"
                error_type = "APIError"
            else:
                error_message = f"DeepSearch工具内部错误: {str(e) or 'Unknown internal error'}"
                error_type = "InternalError"
            
            logger.error(f"DeepSearch tool execution failed for {action}: {error_message}", exc_info=True)
            
            return {
                "success": False,
                "data": None,
                "error_message": error_message,
                "error_type": error_type,
                "error_details": error_details
            }

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
    
    # 初始化ConfigManager
    from core.config_manager import ConfigManager
    config_manager = ConfigManager()
    
    server = DeepSearchMCPServer(config_manager)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())