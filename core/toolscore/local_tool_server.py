import asyncio
import logging
import os
import signal
import sys
import threading
import time
import traceback
import uvicorn # type: ignore
import websockets # type: ignore
import json
from abc import ABC, abstractmethod
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks # type: ignore
from fastapi.responses import JSONResponse # type: ignore
from functools import wraps
from typing import Dict, Any, Optional, List, Union, Callable, Awaitable
import inspect

from core.interfaces import LocalToolSpec, LocalToolInterface
from core.config_service import ConfigService


logger = logging.getLogger(__name__)

class LocalServerInterface(ABC):
    """本地服务器接口"""

    @abstractmethod
    async def start(self):
        """启动服务器"""
        pass

    @abstractmethod
    async def stop(self):
        """停止服务器"""
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """服务器是否正在运行"""
        pass

    @property
    @abstractmethod
    def url(self) -> str:
        """服务器URL"""
        pass

class FastAPIToolServer(LocalServerInterface):
    """基于FastAPI的本地工具服务器"""

    def __init__(self,
                 host: str = "localhost",
                 port: int = 0, # 0 means auto-select
                 title: str = "Local Tool Server",
                 description: str = "FastAPI服务器提供本地工具服务"):
        self.host = host
        self.port = port or self._find_free_port()
        self.app = FastAPI(title=title, description=description)
        self.server_thread: Optional[threading.Thread] = None
        self.uvicorn_server: Optional[uvicorn.Server] = None
        self._running = False
        self._tool_specs: Dict[str, LocalToolSpec] = {}  # {工具ID: 工具规范}
        self._tools: Dict[str, LocalToolInterface] = {} # {工具ID: 工具实例}

        self._setup_routes()

    def _find_free_port(self) -> int:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def _setup_routes(self):
        @self.app.get("/")
        async def root():
            return {
                "name": self.app.title,
                "description": self.app.description,
                "tools": list(self._tool_specs.keys())
            }

        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

        @self.app.get("/tools")
        async def list_tools_route(): # Renamed to avoid conflict
            return {"tools": [spec.to_dict() for spec in self._tool_specs.values()]}

        @self.app.get("/tools/{tool_id}")
        async def get_tool_route(tool_id: str): # Renamed
            if tool_id not in self._tool_specs:
                raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
            return {"tool": self._tool_specs[tool_id].to_dict()}

    def register_tool(self, tool: LocalToolInterface):
        tool_spec = tool.tool_spec
        tool_id = tool_spec.tool_id

        self._tool_specs[tool_id] = tool_spec
        self._tools[tool_id] = tool # Store the tool instance

        # Dynamically add endpoint for the tool
        # Ensure this is done before the server starts or handle router updates if server is live
        @self.app.post(f"/tools/{tool_id}/{{action}}", name=f"execute_{tool_id}")
        async def execute_tool_endpoint(action: str, request: Request): # Removed background_tasks for simplicity here
            try:
                parameters = await request.json()
                target_tool = self._tools.get(tool_id)
                if not target_tool:
                    raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found during execution.")

                # Execute tool's method
                if asyncio.iscoroutinefunction(target_tool.execute):
                    result = await target_tool.execute(action, parameters)
                else:
                    # Run synchronous tool.execute in a thread pool
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, target_tool.execute, action, parameters)
                return result
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON payload")
            except Exception as e:
                logger.error(f"处理工具请求失败 {tool_id}.{action}: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

        logger.info(f"工具路由注册成功: /tools/{tool_id}/{{action}}")


    async def start(self):
        if self._running:
            logger.warning("服务器已经在运行")
            return

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning", # Quieter logs from uvicorn
            loop="asyncio"
        )
        self.uvicorn_server = uvicorn.Server(config)

        # Uvicorn's run method is blocking, so it needs its own thread
        self.server_thread = threading.Thread(target=self.uvicorn_server.run, daemon=True)
        self.server_thread.start()

        # Wait for server to start - Uvicorn doesn't have a simple 'started' flag accessible here
        # A common way is to try connecting, or just a short sleep
        await asyncio.sleep(1) # Give it a moment to start
        self._running = True
        logger.info(f"FastAPI工具服务器尝试启动于: {self.url}")


    async def stop(self):
        if not self._running or not self.uvicorn_server:
            return

        self.uvicorn_server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=5) # Wait for thread to finish

        self._running = False
        logger.info("FastAPI工具服务器已停止")

    @property
    def is_running(self) -> bool:
        # A more robust check might involve trying to connect to the health endpoint
        return self._running

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

class WebSocketToolServer(LocalServerInterface):
    """基于WebSocket的本地工具服务器"""

    def __init__(self,
                 host: str = "localhost",
                 port: int = 0, # 0 means auto-select
                 name: str = "WebSocket Tool Server"):
        self.host = host
        self.port = port or self._find_free_port()
        self.name = name
        self._tools: Dict[str, LocalToolInterface] = {}
        self._tool_specs: Dict[str, LocalToolSpec] = {}
        self._running = False
        self._server_task: Optional[asyncio.Task] = None
        self._server_instance: Optional[websockets.WebSocketServerProtocol] = None # type: ignore
        self._connections = set()


    def _find_free_port(self) -> int:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def register_tool(self, tool: LocalToolInterface):
        tool_spec = tool.tool_spec
        tool_id = tool_spec.tool_id
        self._tools[tool_id] = tool
        self._tool_specs[tool_id] = tool_spec
        logger.info(f"WebSocket工具注册成功: {tool_id}")

    async def handle_connection(self, websocket: websockets.WebSocketServerProtocol, path: str): # type: ignore
        self._connections.add(websocket)
        logger.info(f"新的WebSocket连接: {websocket.remote_address}")
        try:
            async for message_str in websocket:
                message = str(message_str) # Ensure it's a string
                try:
                    data = json.loads(message)
                    request_id = data.get("request_id", str(time.time_ns()))
                    tool_id = data.get("tool_id")
                    action = data.get("action")
                    parameters = data.get("parameters", {})

                    if tool_id == "_system" and action == "list_tools":
                        response = {
                            "request_id": request_id, "success": True,
                            "tools": [spec.to_dict() for spec in self._tool_specs.values()]
                        }
                        await websocket.send(json.dumps(response))
                        continue

                    if not tool_id or not action:
                        await websocket.send(json.dumps({"request_id": request_id, "success": False, "error": "无效请求"}))
                        continue

                    target_tool = self._tools.get(tool_id)
                    if not target_tool:
                        await websocket.send(json.dumps({"request_id": request_id, "success": False, "error": f"工具不存在: {tool_id}"}))
                        continue

                    try:
                        result = await target_tool.execute(action, parameters)
                        if not isinstance(result, dict): result = {"result": result}
                        result["request_id"] = request_id
                        if "success" not in result: result["success"] = True
                        await websocket.send(json.dumps(result))
                    except Exception as e_exec:
                        logger.error(f"工具执行失败 {tool_id}.{action}: {e_exec}", exc_info=True)
                        await websocket.send(json.dumps({"request_id": request_id, "success": False, "error": f"执行错误: {str(e_exec)}"}))

                except json.JSONDecodeError:
                    logger.warning(f"无效的JSON消息: {message}")
                    await websocket.send(json.dumps({"success": False, "error": "无效JSON"}))
                except Exception as e_handler:
                    logger.error(f"处理消息失败: {e_handler}", exc_info=True)
                    await websocket.send(json.dumps({"success": False, "error": f"服务器错误: {str(e_handler)}"}))
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket连接关闭: {websocket.remote_address}")
        finally:
            self._connections.remove(websocket)

    async def start(self):
        if self._running:
            logger.warning("WebSocket服务器已经在运行")
            return

        try:
            self._server_instance = await websockets.serve( # type: ignore
                self.handle_connection, self.host, self.port
            )
            self._running = True
            logger.info(f"WebSocket工具服务器启动于: {self.url}")
            # Keep server running in background if start() is awaited directly
            # If start() is called via create_task, this is not strictly needed here
            # await asyncio.Future() # This would block here if not careful
        except Exception as e:
            logger.error(f"启动WebSocket服务器失败: {e}", exc_info=True)
            self._running = False


    async def stop(self):
        if not self._running or not self._server_instance:
            return

        self._server_instance.close()
        await self._server_instance.wait_closed()
        self._running = False
        # Also close all client connections
        for conn in list(self._connections):
            await conn.close()
        self._connections.clear()
        logger.info("WebSocket工具服务器已停止")


    @property
    def is_running(self) -> bool:
        return self._running and self._server_instance is not None and self._server_instance.is_serving()


    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"


class LocalToolServerManager:
    """本地工具服务器管理器"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocalToolServerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.config_service = ConfigService()
        self.config = self.config_service.get_config().tools
        self.servers: Dict[str, LocalServerInterface] = {}
        self._initialized = True
        self._register_signal_handlers()
        logger.info("工具服务器管理器初始化完成")

    def _register_signal_handlers(self):
        loop = asyncio.get_event_loop()
        for sig_name in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig_name,
                lambda s=sig_name: asyncio.create_task(self.shutdown_on_signal(s))
            )

    async def shutdown_on_signal(self, sig):
        logger.info(f"收到信号 {sig.name}，正在关闭服务器...")
        await self.stop_all_servers()
        # Optionally, add other cleanup tasks here
        # To allow other tasks to complete, you might await a bit
        await asyncio.sleep(0.1)
        # Stop the loop, or let the main function handle exit
        # loop = asyncio.get_event_loop()
        # loop.stop()


    def create_http_server(self,
                                  name: str,
                                  host: str = "localhost",
                                  port: int = 0) -> FastAPIToolServer:
        actual_port = port or self.config.tool_server_port # Fallback to config if port is 0
        server = FastAPIToolServer(host=host, port=actual_port, title=name)
        server_id = f"http_{name}_{host}_{server.port}" # Use server.port as it might be auto-assigned
        self.servers[server_id] = server
        logger.info(f"创建HTTP工具服务器: {server_id} on {server.url}")
        return server

    def create_websocket_server(self,
                                       name: str,
                                       host: str = "localhost",
                                       port: int = 0) -> WebSocketToolServer:
        # Ensure different default port for WS if HTTP uses default
        default_ws_port = (self.config.tool_server_port + 1000) if self.config.tool_server_port else 9080
        actual_port = port or default_ws_port
        server = WebSocketToolServer(host=host, port=actual_port, name=name)
        server_id = f"ws_{name}_{host}_{server.port}"
        self.servers[server_id] = server
        logger.info(f"创建WebSocket工具服务器: {server_id} on {server.url}")
        return server


    async def start_server(self, server_id: str) -> bool:
        if server_id not in self.servers:
            logger.error(f"服务器不存在: {server_id}")
            return False
        server = self.servers[server_id]
        if server.is_running:
            logger.warning(f"服务器已经在运行: {server_id}")
            return True
        try:
            await server.start()
            return True
        except Exception as e:
            logger.error(f"启动服务器失败 {server_id}: {e}", exc_info=True)
            return False

    async def stop_server(self, server_id: str) -> bool:
        if server_id not in self.servers:
            logger.error(f"服务器不存在: {server_id}")
            return False
        server = self.servers[server_id]
        if not server.is_running:
            return True
        try:
            await server.stop()
            return True
        except Exception as e:
            logger.error(f"停止服务器失败 {server_id}: {e}", exc_info=True)
            return False

    async def start_all_servers(self):
        # Use asyncio.gather to start all servers concurrently
        results = await asyncio.gather(
            *(self.start_server(server_id) for server_id in self.servers.keys()),
            return_exceptions=True # So one failure doesn't stop others
        )
        for server_id, result in zip(self.servers.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"启动服务器 {server_id} 失败: {result}")
            elif not result:
                 logger.warning(f"服务器 {server_id} 未能成功启动 (no exception).")


    async def stop_all_servers(self):
        results = await asyncio.gather(
            *(self.stop_server(server_id) for server_id in self.servers.keys()),
            return_exceptions=True
        )
        for server_id, result in zip(self.servers.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"停止服务器 {server_id} 失败: {result}")


    def get_server(self, server_id: str) -> Optional[LocalServerInterface]:
        return self.servers.get(server_id)

    def get_server_by_url(self, url: str) -> Optional[LocalServerInterface]:
        for server in self.servers.values():
            if server.url == url:
                return server
        return None

    def list_servers(self) -> List[Dict[str, Any]]:
        return [{
            "id": sid, "url": s.url, "running": s.is_running,
            "type": "HTTP" if isinstance(s, FastAPIToolServer) else "WebSocket"
        } for sid, s in self.servers.items()]