# MCP Server 架构改进计划

## 背景问题回顾

在当前的 Agent Data Platform 架构中，每个 MCP 服务器（如 Python Executor MCP Server 和 Browser Navigator MCP Server）以及其他核心服务（如 ToolScore Monitoring API、Task API Server、ToolScore MCP Server）都需要监听一个唯一的网络端口来提供其服务。这导致了以下问题：

1.  **端口冲突风险高：** 手动分配固定端口容易与系统或其他应用程序的端口发生冲突，导致服务无法启动。
2.  **配置复杂性：** 每次添加新的 MCP 服务器都需要手动修改 `config/settings.py` 文件，增加了配置和维护的复杂性。
3.  **资源浪费：** 即使某个 MCP 服务器不活跃，其预留的端口也可能被占用。
4.  **动态性差：** 不利于系统根据需求动态启动或停止 MCP 服务器。

## 改进方案：动态端口分配与统一 MCP 服务器管理

为了解决上述问题，我们建议引入一个更智能的端口管理机制，并优化 MCP 服务器的启动流程。

**核心思想：**
我们将从手动分配固定端口转变为**动态端口分配**，并利用一个**统一的 MCP 服务器启动器**来集中管理所有 MCP 服务器的生命周期，包括端口的获取和注册。

### 详细计划步骤：

1.  **MCP 服务器配置中心化 (`config/mcp_servers.json`)：**
    *   我们将把所有 MCP 服务器的配置（例如服务器名称、运行时路径等）集中存储在 `config/mcp_servers.json` 文件中。
    *   这个配置文件将不再包含固定的端口号，因为端口将由系统动态分配。
    *   **状态：已完成**。

2.  **扩展 `services/mcp_server_launcher.py`：**
    *   `mcp_server_launcher.py` 将成为所有外部 MCP 服务器的中央管理器。
    *   **读取配置：** 它将负责读取 `config/mcp_servers.json` 文件，获取需要启动的 MCP 服务器列表。
    *   **动态端口分配：** 对于每个需要启动的 MCP 服务器，`mcp_server_launcher` 将使用 `utils/port_manager.py` 或 Python 的 `socket` 模块来查找一个当前可用的空闲端口。
    *   **启动进程：** `mcp_server_launcher` 将以子进程的形式启动每个 MCP 服务器，并将动态分配的端口作为命令行参数或环境变量传递给它。
    *   **注册到 ToolScore：** **已完成**。注意：实际注册动作由 MCP Server 自身完成，而非 Launcher。Launcher 负责启动进程并传递端口。
    *   **状态：已完成**。

3.  **修改 MCP 服务器的 `main.py` 文件：**
    *   每个 MCP 服务器的 `main.py`（例如 `mcp_servers/python_executor_server/main.py` 和 `mcp_servers/browser_navigator_server/main.py`）将进行修改，使其能够从命令行参数或环境变量中获取其监听端口，而不是从 `config/settings.py` 中硬编码或导入。
    *   **状态：已完成**。

4.  **简化 `main.py`：**
    *   主入口文件 `main.py` 已更新为通过 `MCPServerLauncher.launch_all_configured_servers()` 与 `MCPServerLauncher.stop_all_servers()` 来统一处理所有 MCP 服务器的生命周期管理，避免了手动维护各服务器的启动/停止逻辑。
    *   **状态：已完成**。

### 待完善事项（2025-06-15）：

经过最新代码审查，当前仍有以下细节待进一步优化：

1.  **配置常量统一性：**
    *   `main.py` 中原先引用了 `settings.TOOLSCORE_WEBSOCKET_ENDPOINT`，但在 `config/settings.py` 中实际定义的常量为 `TOOLSCORE_WS_URL`，两者不一致。
    *   **状态：已完成**。已在代码中将其修正为 `TOOLSCORE_WS_URL`，并统一了 `config/settings.py` 中 `TOOLSCORE_WS_URL` 的端口定义。

2.  **ToolScore WebSocket 与 HTTP 端点说明：**
    *   `EnhancedReasoningRuntime` 与若干服务通过环境变量 `TOOLSCORE_WS_URL` 动态获取 WebSocket 端点；`services/runtime_service.py` 会在启动时写入默认值。
    *   **状态：已完成**。已在代码中统一 `TOOLSCORE_WS_URL` 的引用。
    *   **说明：**
        *   `TOOLSCORE_HTTP_URL` 用于监控 API（HTTP）。
        *   `TOOLSCORE_WS_URL` 用于实时通知（WebSocket），其端口与 `TOOLSCORE_MCP_PORT` 相同。
        *   `TOOLSCORE_MCP_WS_URL` 用于 MCP Server 间通信，是 MCP Server 自身监听的 WebSocket 地址。

3.  **Launcher 与 ToolScore 注册职责说明：**
    *   目前 MCP Server 的注册动作由各自进程在启动后，通过 `MCPServer._register_with_toolscore()` 主动完成，而非由 `MCPServerLauncher` 执行。
    *   **状态：已完成**。文档已更新，但仍建议在未来考虑：Launcher 在确认子进程成功启动后，可监听其注册结果以提供更准确的启动状态反馈。

### 改进后的 MCP 服务器启动和注册流程图：

```mermaid
graph TD
    subgraph 启动阶段
        A[main.py] --> B(初始化 CoreManager, PortManager等)
        B --> C{调用 services.mcp_server_launcher.start_all_mcp_servers()}
    end

    subgraph MCP Server Launcher (services/mcp_server_launcher.py)
        C --> D[读取 config/mcp_servers.json]
        D --> E{遍历每个 MCP Server 配置}
        E --> F[动态获取可用端口 (PortManager.get_available_port())]
        F --> G[启动 MCP Server 进程 (例如: python -m mcp_servers.python_executor_server.main --port <dynamic_port>)]
        G --> H[MCP Server 进程启动]
    end

    subgraph 各个 MCP Server (例如: mcp_servers/python_executor_server/main.py)
        H --> I{MCP Server 接收动态端口}
        I --> J[MCP Server 启动其内部服务 (例如: FastAPI)]
        J --> K[MCP Server 向 ToolScore 注册自身 (通过 ToolScore MCP Client)]
    end

    subgraph ToolScore (core/toolscore/mcp/mcp_server.py)
        K --> L[ToolScore 接收 MCP Server 注册请求]
        L --> M[ToolScore 将 MCP Server及其动态端口注册到 UnifiedToolLibrary]
    end

    subgraph 运行时交互
        N[Reasoning Runtime] --> O{通过 ToolScore 调用 MCP Server 工具}
        O --> P[ToolScore 根据注册信息路由请求到正确的动态端口]
        P --> Q[MCP Server 执行工具并返回结果]
    end

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#bbf,stroke:#333,stroke-width:2px
    style G fill:#bbf,stroke:#333,stroke-width:2px
    style H fill:#bbf,stroke:#333,stroke-width:2px
    style K fill:#bbf,stroke:#333,stroke-width:2px
    style M fill:#bbf,stroke:#333,stroke-width:2px
    style O fill:#bbf,stroke:#333,stroke-width:2px