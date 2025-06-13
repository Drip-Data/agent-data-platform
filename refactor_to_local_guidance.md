

1.  **Analysis of the Original Docker Orchestration**:
    *   Briefly describe each service defined in the `docker-compose.yml` (`redis`, `vllm`, `dispatcher`, `sandbox-runtime`, `web-runtime`, `reasoning-runtime`).
    *   Highlight key configurations: dependencies, environment variables (especially for service URLs), port mappings.
2.  **Core Principles for De-Dockerization**:
    *   Each Docker service that is part of *your application* (not third-party like Redis) will become a locally run Python process.
    *   Third-party services like Redis will need to be installed and run locally.
    *   Networking will shift from Docker's internal network to `localhost` with distinct ports for each service.
    *   Environment variables will need to be managed locally.
3.  **Strategies for Migrating Each Service/Component (from `new_version` perspective)**:
    *   **Redis**: Requires local installation and a running instance.
    *   **LLM Serving (vLLM vs. Cloud APIs)**:
        *   The `docker-compose.yml` includes an optional `vllm` service. If you intend to use a local LLM like vLLM without Docker, it requires a separate, potentially complex local setup (GPU, CUDA, Python environment for vLLM).
        *   Alternatively, and often simpler for de-dockerization, is to rely on cloud-based LLM APIs (Gemini, OpenAI, DeepSeek) as configured in `new_version/agent-data-platform/core/llm_client.py`. The `docker-compose.yml` already shows environment variables for these.
    *   **ToolScore (`new_version/agent-data-platform/core/toolscore/monitoring_api.py`)**:
        *   How to run this as a local Python process.
        *   It needs access to the local Redis.
        *   It will listen on a specific port (e.g., `8080` as per default in `new_version`).
    *   **MCP Servers (`new_version/agent-data-platform/mcp_servers/`)**:
        *   The `PythonExecutorMCPServer` and `BrowserNavigatorMCPServer` are already designed as Python applications.
        *   They will run as separate local Python processes.
        *   They need to be configured with the `TOOLSCORE_ENDPOINT` pointing to the local ToolScore API (e.g., `ws://localhost:8080/websocket` or the appropriate registration endpoint).
        *   Each will listen on its own port (e.g., Python Executor on `8081`, Browser Navigator on `8082`).
    *   **`DynamicMCPManager` (`new_version/agent-data-platform/core/toolscore/dynamic_mcp_manager.py`)**:
        *   **This is the most critical part to adapt.** Its core function of pulling and running Docker images for new tools is inherently tied to Docker.
        *   **Recommended Strategy**: For a Docker-less setup, this dynamic installation capability will be lost or need significant re-imagining.
            *   **Option 1 (Simplest for now)**: Assume all necessary MCP tools (like the Python executor and browser navigator) are known and will be run as persistent local Python processes (as described above). The `DynamicMCPManager`'s role in *installing* new Dockerized tools would be effectively disabled.
            *   The `MCPSearchTool`'s `search_and_install_tools` action would then either:
                *   Only perform the "search" part (LLM suggests what *type* of tool is needed).
                *   Be modified to trigger a manual process or a script that starts a *pre-existing, locally available* MCP server script.
    *   **`EnhancedReasoningRuntime` (`new_version/agent-data-platform/runtimes/reasoning/enhanced_runtime.py`)**:
        *   Run as a local Python process.
        *   Configure its `ToolScoreClient` and `RealTimeToolClient` to point to the local ToolScore API and WebSocket event endpoints (e.g., `http://localhost:8080`, `ws://localhost:8080/api/v1/events/tools`).
        *   Configure its `LLMClient` with appropriate API keys and endpoints (either local vLLM if set up, or cloud APIs).
    *   **`Dispatcher` (from original `docker-compose.yml` and `main.py`)**:
        *   The `main.py` you provided runs `core.dispatcher`. If this logic is still present and required in your `new_version` (likely, as `core` is a top-level directory), it will also run as a local Python process.
        *   It needs its `REDIS_URL` to point to `redis://localhost:6379`.
        *   The `TASK_FILE` volume mount (`./tasks.jsonl:/app/tasks.jsonl:ro`) means it expects a `tasks.jsonl` file in its working directory.
4.  **Suggested Local Startup Order**:
    1.  Start local Redis server.
    2.  (Optional, if used) Start local vLLM server.
    3.  Start `ToolScoreMonitoringAPI` process.
    4.  Start `PythonExecutorMCPServer` process.
    5.  Start `BrowserNavigatorMCPServer` process.
    6.  (If used) Start `Dispatcher` process.
    7.  Start `EnhancedReasoningRuntime` process (or trigger tasks through it).
5.  **Environment Variable Management**:
    *   How to set them for each Python process (e.g., in the shell before running, or using a `.env` file with `python-dotenv`).
    *   List critical variables derived from `docker-compose.yml` and `new_version` code.
6.  **Code and Configuration Adjustments**:
    *   Review all service URL configurations (e.g., in `ConfigManager` or directly in client instantiations) to use `localhost` and the chosen ports.
    *   Modify `DynamicMCPManager` and `MCPSearchTool` to reflect the non-Docker approach for tool "installation."
    *   Ensure `requirements.txt` for `new_version` includes all necessary dependencies that were previously handled by different Docker images (e.g., `playwright` for `BrowserNavigatorMCPServer`).
7.  **Output and Logging**:
    *   The `output` volume mount (`./output:/app/output`) suggests logs and trajectories are written to a local `output` directory. This behavior can likely be maintained.

I will now generate the Markdown document with these details.

# 指南：将 Agent Data Platform 重构为本地无 Docker 环境运行

本文档旨在指导您将 `new_version/agent-data-platform/` 代码库从依赖 Docker 编排的方式重构为可以直接在本地环境运行。我们将分析原始的 Docker 配置，并针对 `new_version` 的组件提出本地化运行策略。

## 1. 原始 Docker 编排分析 (`docker-compose.yml`)

原始 `docker-compose.yml` 定义了以下主要服务：

*   **`redis`**: Redis 服务，用于消息队列和缓存。
*   **`vllm` (可选)**: 本地 LLM 推理服务，使用 `vllm/vllm-openai` 镜像。需要 GPU 资源。
*   **`dispatcher`**: 任务分发器。构建自项目根目录的 `Dockerfile` (您提供的 `Dockerfile.dispatcher` 示例)，入口为 `python -m core.dispatcher` (或 `python main.py` 如果 `main.py` 调用 `core.dispatcher`)。依赖 Redis。
*   **`sandbox-runtime`**: 轻量级代码执行运行时。构建自 `./runtimes/sandbox/Dockerfile`。依赖 Redis，并可配置连接到 `vllm` 或外部 LLM API (Gemini, DeepSeek, OpenAI)。
*   **`web-runtime`**: Web 导航运行时。构建自 `./runtimes/web_navigator/Dockerfile`。依赖 Redis，可配置 LLM。
*   **`reasoning-runtime`**: 推理运行时服务。构建自 `./docker/reasoning.Dockerfile`。依赖 Redis，可配置 LLM。
*   **`prometheus` & `grafana`**: 监控和仪表盘服务。

**关键配置点**:

*   **服务依赖**: 大部分应用服务依赖 `redis`。
*   **环境变量**:
    *   `REDIS_URL`: 通常设置为 `redis://redis:6379`，指向 Docker 网络中的 `redis` 服务。
    *   `VLLM_URL`: 通常设置为 `http://vllm:8000`。
    *   `GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.: 用于外部 LLM 服务。
    *   `TASK_FILE`: `dispatcher` 服务使用。
*   **端口映射**: Redis (`6379`), vLLM (`8000`), Runtimes (e.g., `web-runtime` metrics `8002`, `reasoning-runtime` `8003`), Prometheus (`9090`), Grafana (`3000`)。
*   **网络**: Docker Compose 会创建一个默认的桥接网络，服务间通过服务名进行通信。

## 2. 本地化运行核心原则

1.  **服务进程化**: 原 Docker `services` 中属于本应用的部分（如 `dispatcher`, 各 Runtimes/MCPs, ToolScore API）将转为独立的本地 Python 进程运行。
2.  **本地依赖**: 第三方服务（如 Redis）需要在本地安装并运行。
3.  **网络配置**: 所有服务间通信将通过 `localhost` 和为每个服务指定的唯一端口进行。
4.  **环境变量**: 之前在 `docker-compose.yml` 中定义的环境变量需要在本地环境中为每个进程设置。
5.  **`DynamicMCPManager` 调整**: 这是核心改动点，因为其动态拉取和运行 Docker 镜像的功能在无 Docker 环境下无法实现。

## 3. `new_version` 组件本地化策略

以下策略针对您 `new_version/agent-data-platform/` 代码库中的组件：

### A. 依赖服务

*   **Redis**:
    *   **操作**: 在本地安装并启动一个 Redis 实例。确保其监听默认端口 `6379` 或您选择的端口。
    *   **配置**: 所有需要连接 Redis 的 `new_version` 组件（如 `CoreManager`, `ToolScoreMonitoringAPI`, `EnhancedReasoningRuntime` 等）中的 Redis URL 配置需更新为 `redis://localhost:6379` (或您的本地 Redis 端口)。
*   **LLM 服务**:
    *   **选项1 (推荐，简单)**: 主要依赖云端 LLM API (Gemini, OpenAI, DeepSeek)。
        *   **操作**: 确保已在环境变量中正确设置了所选云端 LLM 的 API 密钥 (如 `GEMINI_API_KEY`)。
        *   **配置**: `new_version/agent-data-platform/core/llm_client.py` 应能自动检测或通过配置使用这些 API。
    *   **选项2 (复杂)**: 如果仍希望使用本地 vLLM。
        *   **操作**: 您需要在本地（无 Docker）环境中手动安装和配置 vLLM，这可能涉及 GPU驱动、CUDA、Python环境的复杂设置。
        *   **配置**: 如果成功运行本地 vLLM (例如在 `http://localhost:8000`)，则相应配置 `LLMClient`。

### B. `new_version` 核心应用组件

*   **ToolScore (`new_version/agent-data-platform/core/toolscore/monitoring_api.py`)**:
    *   **运行方式**: 作为独立的 Python 进程启动。例如: `python -m core.toolscore.monitoring_api` (假设其内部有 `if __name__ == "__main__":` 启动逻辑，或您创建一个启动脚本)。
    *   **端口**: 默认监听 `8080` (基于 `ToolScoreMonitoringAPI` 的 `DEFAULT_PORT`)。确保此端口未被占用。
    *   **依赖**: 需要连接到本地 Redis。
    *   **配置**:
        *   `CORE_REDIS_URL`: 应设置为本地 Redis 地址。
        *   `TOOLSCORE_WEBSOCKET_EVENT_URL`: 客户端将连接到此 API 提供的 WebSocket 事件端点，例如 `ws://localhost:8080/api/v1/events/tools`。
*   **MCP 服务器 (`new_version/agent-data-platform/mcp_servers/`)**:
    *   例如 `PythonExecutorMCPServer` 和 `BrowserNavigatorMCPServer`。
    *   **运行方式**: 每个 MCP 服务器作为独立的 Python 进程启动。
        *   `python -m mcp_servers.python_executor_server.main`
        *   `python -m mcp_servers.browser_navigator_server.main`
    *   **端口**: 每个 MCP 服务器需要监听一个唯一的端口。
        *   `PythonExecutorMCPServer` 默认 `ws://0.0.0.0:8081/mcp`。
        *   `BrowserNavigatorMCPServer` 默认 `ws://0.0.0.0:8082/mcp`。
    *   **配置**:
        *   `TOOLSCORE_ENDPOINT`: **非常重要**。每个 MCP 服务器启动时需要此环境变量，指向本地 `ToolScoreMonitoringAPI` 的 *注册* WebSocket 端点。根据 `MCPServer` 的实现，这通常是 `ToolScore` 主 WebSocket 端点，例如 `ws://localhost:8080/websocket` (您需要确认 `ToolScoreMonitoringAPI` 或其依赖的 `UnifiedToolLibrary` 是否在此路径上提供 MCP 注册服务，或者是否有专门的注册端点)。
*   **`DynamicMCPManager` 和 `MCPSearchTool`**:
    *   **核心调整**: 由于无法使用 Docker，`DynamicMCPManager` 的动态拉取和运行新 Docker 镜像的功能将失效。
    *   **策略**:
        1.  **禁用动态安装**: 假设所有需要的 MCP 工具 (如 Python 执行器、浏览器导航器以及您可能拥有的其他自定义 MCP) 都是已知的，并且会作为本地 Python 进程手动启动（如上所述）。
        2.  **修改 `DynamicMCPManager`**:
            *   其 `pull_and_run_mcp_image` 等与 Docker 交互的方法需要被移除或修改为抛出“不支持”的异常，或者在非 Docker 模式下返回失败。
            *   `CoreManager` 中的 `is_docker_stubbed()` 可以用来判断是否处于非 Docker 环境。
        3.  **修改 `MCPSearchTool`**:
            *   `search_and_install_tools` 方法中的 "install" 部分需要调整。它可以：
                *   完全移除安装逻辑，只保留 "search" (LLM 分析任务需要什么类型的工具)。
                *   或者，如果 LLM 建议了一个本地已存在但未运行的 MCP 工具脚本，它可以尝试通过 `subprocess` 启动该本地脚本（这增加了复杂性）。
                *   最简单的初始方法是，LLM 仅建议工具类型，然后用户需要手动启动相应的本地 MCP 服务器进程。
            *   `analyze_tool_needs` 仍然可以使用 LLM 分析任务对工具的需求。
    *   **结论**: 系统将从“动态按需安装新工具”变为“使用一组预定义并手动启动的本地工具”。
*   **`EnhancedReasoningRuntime` (`new_version/agent-data-platform/runtimes/reasoning/enhanced_runtime.py`)**:
    *   **运行方式**: 作为独立的 Python 进程启动。
    *   **配置**:
        *   `TOOLSCORE_HTTP_ENDPOINT`: `ToolScoreClient` 需要，应指向本地 `ToolScoreMonitoringAPI` 的 HTTP 地址，例如 `http://localhost:8080`。
        *   `TOOLSCORE_WEBSOCKET_EVENT_URL`: `RealTimeToolClient` 需要，应指向 `ws://localhost:8080/api/v1/events/tools`。
        *   LLM API Keys (`GEMINI_API_KEY` 等) 和相关 URL。
        *   Redis URL (如果直接使用或通过 `CoreManager`)。
    *   **端口**: 如果它自身也提供服务（例如 Prometheus 指标端点，如原始 `reasoning-runtime` 的 `8003`），确保端口不冲突。`EnhancedMetrics` 在 `new_version` 中默认监听 `8003`。
*   **`Dispatcher` (如果 `new_version/agent-data-platform/core/dispatcher.py` 仍在使用)**:
    *   **运行方式**: `python main.py` (假设 `main.py` 位于项目根目录并调用 `core.dispatcher.main`) 或 `python -m core.dispatcher`。
    *   **配置**:
        *   `REDIS_URL`: `redis://localhost:6379`。
        *   `TASK_FILE`: 指向本地 `tasks.jsonl` 文件的路径。
        *   `LOG_LEVEL`.
    *   **工作目录**: 确保从正确的项目根目录运行，以便能找到 `tasks.jsonl` 和 `output` 目录。

### C. 监控组件 (可选，但 `docker-compose.yml` 中包含)

*   **Prometheus & Grafana**: 如果您仍希望使用它们，需要在本地分别安装和配置 Prometheus 和 Grafana。Prometheus 需要配置去抓取各个本地运行服务的 metrics 端点 (例如 `EnhancedReasoningRuntime` 的 `localhost:8003/metrics`)。

## 4. 建议的本地启动顺序

1.  **启动外部依赖**:
    *   启动本地 Redis 服务器。
    *   (可选) 启动本地 vLLM 服务。
2.  **启动核心服务**:
    *   启动 `ToolScoreMonitoringAPI` 进程。等待其成功启动并监听端口。
3.  **启动 MCP 服务器**:
    *   启动 `PythonExecutorMCPServer` 进程。观察其日志，确保它尝试连接并成功注册到 `ToolScore`。
    *   启动 `BrowserNavigatorMCPServer` 进程。同样观察注册情况。
    *   启动任何其他自定义的本地 MCP 服务器进程。
4.  **启动应用逻辑/运行时**:
    *   (如果使用) 启动 `Dispatcher` 进程。
    *   启动 `EnhancedReasoningRuntime` 进程或通过脚本调用其执行任务的逻辑。

## 5. 环境变量管理

对于每个需要作为独立进程运行的 Python 脚本，您需要在启动它之前设置所需的环境变量。方法：

*   **在 Shell 中直接设置**:
    ```bash
    export REDIS_URL="redis://localhost:6379"
    export TOOLSCORE_ENDPOINT="ws://localhost:8080/websocket" # For MCPs
    export GEMINI_API_KEY="your_key"
    python -m core.toolscore.monitoring_api
    ```
*   **使用 `.env` 文件**: 在项目根目录创建一个 `.env` 文件，并使用如 `python-dotenv` 的库在脚本启动时加载它们。
    ```env
    # .env file
    REDIS_URL="redis://localhost:6379"
    TOOLSCORE_HTTP_ENDPOINT="http://localhost:8080"
    TOOLSCORE_WEBSOCKET_EVENT_URL="ws://localhost:8080/api/v1/events/tools"
    # ... other variables for MCPs, LLMs etc.
    ```
    然后在每个主脚本的开头添加:
    ```python
    from dotenv import load_dotenv
    load_dotenv()
    ```

**关键环境变量汇总 (基于 `new_version` 和原始 `docker-compose.yml`)**:

*   `REDIS_URL` (或 `CORE_REDIS_URL`): `redis://localhost:6379`
*   `TOOLSCORE_HTTP_ENDPOINT`: `http://localhost:8080` (供 `EnhancedReasoningRuntime` 的 `ToolScoreClient` 使用)
*   `TOOLSCORE_WEBSOCKET_EVENT_URL`: `ws://localhost:8080/api/v1/events/tools` (供 `EnhancedReasoningRuntime` 的 `RealTimeToolClient` 使用)
*   `TOOLSCORE_ENDPOINT`: `ws://localhost:8080/websocket` (供各 MCP 服务器注册到 ToolScore 使用 - **请验证此端点是否为 `ToolScoreMonitoringAPI` 中 MCP 注册的正确路径**)
*   `GEMINI_API_KEY`, `GEMINI_API_URL` (以及其他 LLM 提供商的类似变量)
*   `LOG_LEVEL`
*   `DISABLE_CACHE` (用于 `LLMClient` 和可能的其他组件)
*   `SAVE_INDIVIDUAL_TRAJECTORIES`
*   (如果使用 `Dispatcher`) `TASK_FILE` (路径应为本地路径)

## 6. 代码和配置调整建议

*   **URL 和端点配置**:
    *   仔细检查 `new_version` 代码中所有硬编码的或通过配置加载的服务 URL (Redis, ToolScore, LLM)。确保它们可以被配置为指向 `localhost` 和正确的端口。
    *   `ConfigManager` (如果 `new_version` 中使用) 是一个集中的地方来管理这些配置。
*   **`DynamicMCPManager` 和 `MCPSearchTool`**:
    *   如上所述，需要明确处理其 Docker 依赖。在 `DynamicMCPManager` 中添加逻辑，使其在检测到非 Docker 环境时（例如，通过检查 `CoreManager.is_docker_stubbed()` 或一个新的配置标志）不尝试执行 Docker 操作。
    *   `MCPSearchTool` 的 `search_and_install_tools` 需要相应调整。
*   **`requirements.txt`**: 确保 `new_version` 的主 `requirements.txt` 文件包含了所有组件运行所需的依赖。例如，如果 `BrowserNavigatorMCPServer` 需要 `playwright`，而 `PythonExecutorMCPServer` 不需要，那么在本地运行时，您的 Python 环境需要同时安装这些依赖。
*   **工作目录和文件路径**:
    *   对于像 `TASK_FILE` 或 `output` 目录这样的文件路径，确保它们在本地运行时是有效的。使用相对路径时，要注意脚本从哪个目录启动。`os.path.abspath` 和 `os.path.join` 会很有用。
*   **端口冲突**: 确保为本地运行的每个服务分配了唯一的端口，并更新所有相关配置。

## 7. 输出和日志

*   原始 `docker-compose.yml` 将 `./output` 目录挂载到容器的 `/app/output`。在本地运行时，Python 脚本可以直接写入到相对路径的 `output` 目录，这部分行为应该比较容易保持一致。
*   日志记录配置 (`LOG_LEVEL`) 应通过环境变量控制。

## 8. 验证步骤

1.  **启动 Redis** 并确认其运行正常。
2.  **启动 `ToolScoreMonitoringAPI`**。访问其 `/health` 和 `/tools` 端点 (例如 `http://localhost:8080/health`) 确认其工作。初始时 `/tools` 可能为空。
3.  **启动一个 MCP 服务器** (如 `PythonExecutorMCPServer`)。检查其日志，看是否成功连接到 `ToolScore` 并注册。然后再次访问 `ToolScore` 的 `/tools` 端点，确认该工具已列出。
4.  **启动 `EnhancedReasoningRuntime`**。
5.  **执行一个简单的测试任务**，该任务使用已注册的本地 MCP 工具。观察 `EnhancedReasoningRuntime`、`ToolScoreMonitoringAPI` 和相应 MCP 服务器的日志，跟踪请求流程。
6.  检查 `output` 目录中是否生成了预期的轨迹和日志文件。

这个重构过程需要细致的配置和对组件间交互的理解。从小处着手，逐步启动和测试每个组件。
