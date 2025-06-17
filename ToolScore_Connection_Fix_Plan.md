# ToolScore 连接问题修复计划

## 概述
本计划旨在解决当前代码库中 `ToolScoreClient` 的连接问题，并确保 `PYTHONPATH=. pytest tests/test_toolscore_connection.py` 测试能够通过。经过对旧版本代码和当前代码库的分析，主要问题点已确定。

## 问题诊断
1.  **`RealTimeToolClient` 连接端口不正确**：在 `tests/test_toolscore_connection.py` 中，`RealTimeToolClient` 尝试连接到 `http://localhost:8090`。然而，`config/ports_config.yaml` 中明确指出 `toolscore_mcp` (WebSocket 服务) 监听 `8090` 端口，而 `toolscore_http` (HTTP 监控 API) 监听 `8091` 端口。`RealTimeToolClient` 作为“实时”客户端，更应该通过 WebSocket 连接到 `ToolScoreMCP` 服务。
2.  **`ToolScoreMCPServer` 工具库初始化时序**：已确认 `core/toolscore/mcp_server.py` 中的 `UnifiedToolLibrary` 初始化发生在服务器绑定端口之后，并在 `server_started_event` 设置之前，这表明其时序是正确的。

## 修复计划步骤

### 1. 修改 `tests/test_toolscore_connection.py`
**目标**：修正 `RealTimeToolClient` 的连接 URL，使其正确连接到 `ToolScoreMCP` 的 WebSocket 服务。

**具体修改**：
*   打开文件 `tests/test_toolscore_connection.py`。
*   找到 `test_real_time_tool_client_connection` 测试用例。
*   将以下行：
    ```python
    toolscore_endpoint = f"http://localhost:{toolscore_mcp_port}" # RealTimeToolClient 期望 HTTP 端点
    ```
    修改为：
    ```python
    toolscore_endpoint = f"ws://localhost:{toolscore_mcp_port}/websocket" # RealTimeToolClient 期望 WebSocket 端点
    ```

### 2. 运行测试并验证
**目标**：验证上述代码修改是否成功解决了 `ToolScoreClient` 的连接问题，并使所有相关测试通过。

**具体操作**：
*   在终端中执行以下命令：
    ```bash
    PYTHONPATH=. pytest tests/test_toolscore_connection.py
    ```
*   观察测试结果，确保所有测试（特别是与 `ToolScoreClient` 和 `RealTimeToolClient` 连接相关的测试）均通过。

## 服务依赖和连接图示

```mermaid
graph TD
    subgraph Main Application
        A[main.py] --> B(ServiceManager)
    end

    subgraph Services
        B --> C[redis_service]
        B --> D[toolscore_service]
        B --> E[mcp_server_launcher]
        B --> F[task_api_service]
        B --> G[runtime_service]
        B --> H[synthesis_service]
    end

    subgraph ToolScore Components
        D --> I[ToolScoreMCPServer]
        D --> J[ToolScoreMonitoringAPI]
        D --> K[UnifiedToolLibrary]
        D --> L[CoreManager]
    end

    subgraph Clients
        M[ToolScoreClient]
        N[RealTimeToolClient]
        O[tests/test_toolscore_connection.py]
    end

    subgraph Configuration
        P[config/ports_config.yaml]
    end

    C -- Redis Connection --> D
    C -- Redis Connection --> F
    C -- Redis Connection --> G
    C -- Redis Connection --> H

    D -- Starts --> I
    D -- Starts --> J

    I -- WebSocket (8090/websocket) --> M
    I -- WebSocket (8090/websocket) --> N (Proposed Change)

    J -- HTTP (8091) --> O (Health Check)

    K -- Manages --> L

    P -- Configures Ports --> D
    P -- Configures Ports --> M
    P -- Configures Ports --> N

    O -- Tests --> M
    O -- Tests --> N
    O -- Tests --> I
    O -- Tests --> D