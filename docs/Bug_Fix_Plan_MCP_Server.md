# MCP Server Bug 修复计划

## 1. 问题分析回顾

最初的错误是 `asyncio - ERROR - Task was destroyed but it is pending!`，发生在 `core/toolscore/mcp/mcp_server.py:517` 的 `await asyncio.Future()`。

第一次尝试修复时，将 `await asyncio.Future()` 替换为 `self.server_task = asyncio.create_task(asyncio.Future())`，这导致了新的错误 `TypeError: a coroutine was expected, got <Future pending>`。

`TypeError` 的原因是 `asyncio.create_task()` 期望一个协程，而不是一个 `Future` 对象。

## 2. 解决方案

*   引入一个新的协程方法 `_run_server_forever`，它包含一个无限循环 `while True: await asyncio.sleep(3600)`。
*   将 `self.server_task = asyncio.create_task(asyncio.Future())` 修改为 `self.server_task = asyncio.create_task(self._run_server_forever())`。
*   在 `stop` 方法中，确保 `self.server_task` 被正确取消，以优雅地停止服务器。

## 3. “无限循环”的必要性解释

这个无限循环的目的是为了让 MCP Server 的主任务持续运行，防止 Python 进程过早退出。

`asyncio.sleep(3600)` 允许事件循环处理其他任务（如 WebSocket 消息），同时保持主任务的活跃。

通过捕获 `asyncio.CancelledError`，可以在服务器停止时优雅地终止这个无限循环任务。

## 4. 实施步骤

*   **步骤 1：** 修改 `core/toolscore/mcp/mcp_server.py` 文件，添加 `_run_server_forever` 协程，并更新 `start` 方法中的 `self.server_task` 创建方式。
*   **步骤 2：** 重新运行 `python main.py`，观察日志输出，确认 `TypeError` 和 `Task was destroyed but it is pending!` 错误是否已解决。

## 5. Mermaid 图示

```mermaid
graph TD
    A[启动 main.py] --> B{MCP Server 启动};
    B --> C[MCPServer.start() 调用];
    C --> D[创建 aiohttp.web.Application 和 AppRunner];
    D --> E[启动 TCPSite];
    E --> F{注册 toolscore_registration_task (如果需要)};
    F --> G[创建并等待 self.server_task];
    G --> H[调用 _run_server_forever()];
    H -- 循环 --> I[asyncio.sleep(3600)];
    I -- 保持运行 --> H;
    subgraph 停止流程
        J[调用 MCPServer.stop()];
        J --> K[取消 toolscore_registration_task];
        K --> L[取消 self.server_task];
        L --> M[清理 aiohttp 资源];
    end
    G -- 任务取消 --> L;