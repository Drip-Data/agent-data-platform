# Datapresso Agent 平台核心模块解析：Synthesis, Runtimes, Tool

本文档详细解析了 `Datapresso Agent` 平台中 `synthesis`、`runtimes` 和 `tool` 三大核心模块的功能、它们之间的交互方式，并深入探讨了 `runtime` 中代理模型如何调用工具库中的工具，以及工具的内部运作和不同类型工具的管理。

## 1. `tool` 模块 (`core/toolscore`)

`core/toolscore` 是一个**纯粹的工具管理平台**，其核心职责是为执行环境中的自主 Agent 提供工具的注册、发现、描述和调用服务。它专注于管理两大类工具：**Function Tools**（遗留的、直接嵌入在 runtime 中的工具，正逐步迁移）和 **MCP Server**（独立运行的 MCP 协议服务器，是未来工具架构的主体）。系统不包含任何业务逻辑或硬编码的工具匹配规则，而是将智能决策的职责完全交给 Agent。

### 1.1 核心设计理念

*   **职责分离**：工具库专注工具管理，Agent 专注智能决策。
*   **自主决策**：Agent 在 Runtime 中通过 prompt 直接分析和选择工具。
*   **纯服务化**：工具库仅提供工具管理和查询 API，不做智能推荐。
*   **动态注册**：支持运行时动态注册新工具。

### 1.2 核心组件

*   **[`UnifiedToolLibrary`](core/toolscore/unified_tool_library.py)**: 作为 API 网关，为 Agent 提供统一的查询和调用接口。它协调工具注册中心和调度器，提供标准化 API，但不进行任何智能推荐或工具匹配。
*   **[`ToolRegistry`](core/toolscore/tool_registry.py)**: 工具注册中心，负责管理所有工具的注册和元数据，包括 Function Tool 和 MCP Server 的注册和管理，以及工具元数据存储和查询。
*   **[`DescriptionEngine`](core/toolscore/description_engine.py)**: 描述生成引擎，为 Agent 提供可理解的工具详细描述信息，包括工具使用说明、参数规范和使用示例。
*   **[`UnifiedDispatcher`](core/toolscore/unified_dispatcher.py)**: 统一调度器，负责执行 Agent 选定的工具调用，并适配 Function Tool 和 MCP Server 的执行，以及执行结果的标准化。

### 1.3 工具类型管理

`tool` 模块管理两大类工具：

*   **Function Tools**:
    *   **定义**: 遗留的、直接嵌入在 `ReasoningRuntime` 进程中的 Python 函数工具。
    *   **特点**: 直接嵌入在 runtime 进程中，通过 Python 模块导入和调用，支持同步和异步执行，资源共享和快速响应。**注意：这部分工具正在逐步被迁移到独立的 MCP Servers，以提升系统模块化和隔离性。**
    *   **管理**: 通过 `FunctionToolSpec` 定义，包含 `module_path` 和 `class_name`，由 `ToolRegistry` 注册和管理。
*   **MCP Servers**:
    *   **定义**: 独立运行的 MCP (Model Context Protocol) 协议服务器。
    *   **特点**: 独立进程运行，通过 MCP 协议通信，支持复杂的外部集成，具有隔离性和可扩展性。
    *   **管理**: 通过 `MCPServerSpec` 定义，包含 `server_config` 和 `endpoint`，由 `ToolRegistry` 注册和管理。

## 2. `runtimes` 模块

`runtimes` 模块是 Agent 实际执行任务的**多种环境集合**。它包含了自主 Agent 的核心逻辑，负责任务的分析、工具的选择、执行计划的制定以及工具的调用。

*   **`ReasoningRuntime`**: 这是 Agent 的核心决策和执行环境，负责通过 LLM 进行智能决策，并协调各种工具的调用。它通常是基于 Python 的环境。**当前版本中，`ReasoningRuntime` 不再直接承载 Function Tools，而是通过 `MCPToolClient` 连接到远程 `toolscore` MCP Server 来调用所有工具。**
*   **其他专门化 `runtime`**: 平台支持多种专门化的 `runtime`，例如用于 Web 交互的 `MemoryControlledWebRuntime` 和用于沙箱代码执行的 `LightweightSandboxRuntime`。这些 `runtime` 提供了特定领域的能力，并已或将逐步被封装为独立的 `MCP Servers`。`ReasoningRuntime` 通过远程 `toolscore` MCP Server 间接调用和管理这些能力。

### 2.1 核心职责

*   **Agent 决策**: Agent 在 `runtime` 中通过 LLM (Large Language Model) 进行智能决策，包括需求分析、工具选择、执行策略制定和结果分析。
*   **工具集成**: `runtime` 通过 `UnifiedToolLibrary` 与 `tool` 模块进行交互，获取可用工具列表、工具描述，并执行工具调用。
*   **上下文感知**: `enhanced_runtime.py` 引入了 `ExecutionContext`，用于维护 Agent 的记忆，包括任务描述、已执行步骤、当前观察、失败尝试和学习到的模式。这使得 Agent 能够从失败中学习，避免重复错误，并进行自适应调整。

### 2.2 Agent 模型如何调用 Tool 库工具（通过 Prompt）

Agent 模型在接收到任务 query 后，**会通过构建上下文感知的 Prompt 来调用 tool 库里的工具**。这个过程是高度智能化，而不是硬编码的匹配。

详细流程如下：

1.  **初始化**: `ReasoningRuntime` (或 `ContextAwareReasoningRuntime`) 在初始化时会创建 `MCPToolClient` 实例，并使用该客户端实例化 `UnifiedToolLibrary`。`UnifiedToolLibrary` 将通过此客户端连接到远程 `toolscore` MCP Server。
2.  **获取工具描述**: `runtime` 调用 `tool_library.get_all_tools_description_for_agent()` 来获取所有可用工具的 Agent 友好描述。这些描述由远程 `toolscore` MCP Server 提供。
3.  **Agent 决策 Prompt**: `runtime` 构建一个包含用户任务、可用工具描述、执行状态、失败历史和学习模式的**上下文感知 prompt**，发送给 LLM。
    *   **Prompt 示例结构**:
        ```
        你是一个智能工具选择专家。请基于上下文信息分析用户任务并选择最合适的工具：

        原始任务: {context.task_description}
        最近的失败尝试: ...
        当前观察: ...
        已知问题模式: ...
        可用工具: {format_tools_for_prompt(context.available_tools)}

        请分析:
        1. 基于失败历史，哪些方法已经证明不可行？
        2. 当前观察结果表明任务进展如何？
        3. 下一步应该选择什么工具和策略？
        4. 如何避免重复之前的错误？

        输出格式:
        ACTION_TYPE: [execute_tool|replan|switch_tool|complete]
        SELECTED_TOOL: [工具ID]
        ACTION: [具体动作]
        PARAMETERS: [参数]
        REASONING: [基于上下文的选择理由]
        ```
4.  **Agent 决策**: LLM 根据 Prompt 分析任务需求和上下文，输出一个决策，包括要执行的 `tool_id`、`action` 和 `parameters`。
5.  **执行工具调用**: `runtime` 解析 Agent 的决策，然后调用 `tool_library.execute_tool()` 来实际执行选定的工具。如果使用 `ContextAwareReasoningRuntime`，则会调用 `tool_library.execute_tool_with_context()`，允许工具库根据上下文调整参数。
6.  **结果分析与上下文更新**: 工具执行结果返回给 `runtime`，Agent 分析结果并更新 `ExecutionContext`，为下一次决策提供上下文信息。

### 2.3 Function Tools 与 `runtime` 环境的启动和调用

**Function Tools** 是 Python 函数，它们在旧架构中被设计为**直接嵌入在调用它们的 `runtime` 进程中执行**。这意味着 Function Tools 的执行环境就是其所在的 `runtime` 实例。**在新架构中，Function Tools 正在逐步被迁移并封装为独立的 MCP Servers。**

*   **`ReasoningRuntime` 的核心作用**: `ReasoningRuntime` (或 `ContextAwareReasoningRuntime`) 是 Agent 的核心决策和执行环境。在新架构中，它在初始化时会创建 `MCPToolClient` 实例，并使用该客户端实例化 `UnifiedToolLibrary`。`UnifiedToolLibrary` 将通过此客户端连接到远程 `toolscore` MCP Server。当 Agent 决策需要工具能力时，`UnifiedDispatcher` 会通过 `MCPToolClient` 向远程 `toolscore` MCP Server 发送请求，由 `toolscore` 负责将请求路由到相应的 MCP Server（包括由原 Function Tools 转换而来的 MCP Servers）。
*   **其他专门化 `runtime` 的集成**: 像 `MemoryControlledWebRuntime` 和 `LightweightSandboxRuntime` 这样的专门化 `runtime`，它们提供了特定领域的能力（如 Web 浏览、沙箱代码执行）。在当前架构优化中，它们的能力已被封装为独立的 MCP Servers（例如 `browser_navigator_server` 和 `python_executor_server`）。`ReasoningRuntime` 不再直接与它们交互，而是通过远程 `toolscore` MCP Server 间接调用这些独立的 MCP Servers。
*   **Agent 的决策与 `runtime` 协调**: Agent 的决策核心始终在 `ReasoningRuntime` 中。它不会直接“切换”到另一个 `runtime`，而是通过智能地选择和调用工具来间接利用不同 `MCP Servers` 提供的能力。不同的 `MCP Server` 实例可以独立运行，Agent 根据任务需求，通过远程工具调用来协调它们的工作。

因此，在新的架构中，工具的执行不再依赖于 `ReasoningRuntime` 进程本身，而是通过 `MCPToolClient` 和远程 `toolscore` MCP Server 进行解耦和路由。`ReasoningRuntime` 作为 Agent 的“大脑”，通过统一的工具库机制，能够灵活地利用远程提供的各种工具能力。

### 2.4 Tool 内部运作与工具管理

`tool` 模块内部的运转主要围绕 `UnifiedToolLibrary` 及其核心组件展开：

1.  **注册**: Function Tools 和 MCP Servers 的规范 (`FunctionToolSpec`, `MCPServerSpec`) 被提交给 `ToolRegistry` 进行存储和管理。
2.  **查询**: Agent 通过 `UnifiedToolLibrary` 查询可用的工具列表或特定工具的元数据。
3.  **描述生成**: `UnifiedToolLibrary` 调用 `DescriptionEngine` 生成 Agent 可理解的工具描述。
4.  **执行**: 当 Agent 调用工具时，`UnifiedToolLibrary` 将请求转发给 `UnifiedDispatcher`。
    *   **对于 Function Tool (遗留)**: `UnifiedDispatcher` 仍可直接在当前进程中加载并调用对应的 Python 函数，但此路径正逐步废弃。
    *   **对于 MCP Server**: `UnifiedDispatcher` 通过 `MCPServerAdapter` 和注入的 `MCPToolClient` 实例与外部的 MCP Server 建立通信，发送工具调用请求。
5.  **上下文感知执行**: `UnifiedToolLibrary` 提供了 `execute_tool_with_context()` API，在执行前根据 `ExecutionContext` 动态调整参数，执行后记录失败信息供 Agent 学习。

**Function Tools 和 MCP Server 的管理方式：**

它们通过不同的数据模型和调度逻辑进行管理：

*   **数据模型**: 使用 `FunctionToolSpec` 和 `MCPServerSpec` 两个不同的数据类来定义各自的工具规范，包含各自特有的配置信息。
*   **注册**: `UnifiedToolLibrary` 提供独立的 API (`register_function_tool()` 和 `register_mcp_server()`) 来注册不同类型的工具。
*   **调度/执行**: `UnifiedDispatcher` 是统一的执行入口，它会根据工具的类型 (`ToolSpec.tool_type`) 来判断并执行不同的调度逻辑：对于 Function Tool（遗留），直接调用 Python 函数；对于 MCP Server，通过 `MCPServerAdapter` 和 `MCPToolClient` 与外部服务器通信。

## 3. `synthesis` 模块 (`core/synthesiscore`)

`synthesis` 模块（主要由 `SimpleSynthesizer` 类实现）是一个**任务合成器**，其核心目标是通过分析 Agent 的执行轨迹，提取任务的本质特征，并生成高质量的**种子任务 (seed tasks)**，用于训练或评估 Agent。

### 3.1 主要功能

1.  **轨迹分析 (Trajectory Analysis)**: 深度理解 Agent 的行为模式，监控 `output/trajectories/trajectories_collection.json` 文件变化。
2.  **本质提取 (Essence Extraction)**: 使用 LLM 分析 Agent 的完整执行轨迹（包括步骤、动作、参数、结果、思考过程、错误信息等），提取任务的类型、领域、优化描述、复杂度、关键特征和使用的工具等。
3.  **种子生成 (Seed Generation)**: 基于提取到的任务本质，创造新的、高质量的训练任务，推断预期工具和最大步数。
4.  **自动监控 (Automatic Monitoring)**: 实时跟踪轨迹文件的变化，通过 `watchdog` 库监控并使用 Redis 队列触发异步处理。
5.  **数据存储**: 使用 JSON 文件进行数据存储，包括 `task_essences.json` (存储任务本质) 和 `seed_tasks.jsonl` (存储生成的种子任务)。

### 3.2 核心流程

*   `SimpleSynthesizer` 启动，初始化 `UnifiedToolLibrary` 和 `LLMClient`。
*   启动文件监控器 (`TrajectoryHandler`) 监听轨迹集合文件。
*   文件变化时，`TrajectoryHandler` 向 Redis 队列发送处理命令。
*   `SimpleSynthesizer` 接收命令，读取轨迹数据。
*   对每个轨迹：
    *   检查是否已处理，判断是否值得处理。
    *   调用 `_extract_essence` 方法，将轨迹信息作为 prompt 发送给 LLM，提取任务本质 (`TaskEssence`)。
    *   保存 `TaskEssence` 到 `task_essences.json`。
    *   调用 `_convert_essence_to_seed` 方法，将 `TaskEssence` 转换为 `TaskSpec` 格式的种子任务。
    *   将生成的种子任务追加到 `seed_tasks.jsonl` 文件中。
    *   标记该轨迹为已处理。
*   `synthesis` 模块还会定期或根据命令导出种子任务的统计报告。

## 4. 模块间交互总结

以下 Mermaid 图展示了 `synthesis`、`runtimes` 和 `tool` 三大模块之间的交互关系：

```mermaid
graph TD
    subgraph User/External System
        A[用户查询/任务] --> B(任务输入)
    end

    subgraph Runtimes Module
        B --> C{ReasoningRuntime (Agent Core)};
        C -- 1. 初始化 MCPToolClient --> C_MCP_Client[MCPToolClient];
        C_MCP_Client -- 2. 连接到远程 toolscore MCP Server --> E[UnifiedToolLibrary (远程实例)];
        C -- 3. 获取所有工具描述 (通过远程 toolscore) --> E;
        E -- 4. 返回工具描述 --> C;
        C -- 5. Agent决策 (选择工具, 制定计划) --> D[LLM (Agent Model)];
        D -- 6. Agent决策结果 --> C;
        C -- 7. 执行工具调用 (tool_id, action, params, 通过远程 toolscore) --> E;
        E -- 8. 返回执行结果 --> C;
        C -- 9. 更新执行上下文 (记忆, 失败模式) --> F[ExecutionContext];
        C -- 10. 生成执行轨迹 --> G[Trajectory Data];
    end

    subgraph Tool Module (toolscore MCP Server)
        E -- 11. 接收工具调用请求 --> J[UnifiedDispatcher];
        J -- 11a. 调度 MCP Server 工具 (通过 MCP Protocol) --> L[MCP Servers (External services)];
        L -- 11a.i. 返回结果 --> J;
        J -- 11b. 调度 Function Tool (遗留, in-process) --> K[Function Tools (Python functions)];
        K -- 11b.i. 返回结果 --> J;
        E -- 12. 查询工具元数据 --> H[ToolRegistry];
        E -- 13. 生成工具描述 --> I[DescriptionEngine];
        H -- 12a. 存储/查询 ToolSpec --> M[Tool Metadata (FunctionToolSpec, MCPServerSpec)];
    end

    subgraph External MCP Servers
        L -- Python 代码执行 --> P_EXEC[Python Executor Server];
        L -- 浏览器操作 --> B_NAV[Browser Navigator Server];
        P_EXEC -- 注册工具/提供服务 --> E;
        B_NAV -- 注册工具/提供服务 --> E;
    end

    subgraph Synthesis Module
        G -- 14. 监控轨迹文件变化 --> N[TrajectoryHandler (File Watcher)];
        N -- 15. 发送处理命令 (Redis Stream) --> O[SimpleSynthesizer];
        O -- 16. 读取轨迹数据 --> G;
        O -- 17. LLM提取任务本质 (Prompt) --> D;
        D -- 18. 返回任务本质 --> O;
        O -- 19. 存储任务本质 --> P[Task Essences (JSON)];
        O -- 20. 生成种子任务 --> Q[Seed Tasks (JSONL)];
        O -- 21. 推断预期工具 (查询ToolRegistry) --> H;
    end

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#bbf,stroke:#333,stroke-width:2px
    style C_MCP_Client fill:#add8e6,stroke:#333,stroke-width:2px
    style D fill:#ccf,stroke:#333,stroke-width:2px
    style E fill:#bfb,stroke:#333,stroke-width:2px
    style F fill:#fbb,stroke:#333,stroke-width:2px
    style G fill:#ffb,stroke:#333,stroke-width:2px
    style H fill:#bfb,stroke:#333,stroke-width:2px
    style I fill:#bfb,stroke:#333,stroke-width:2px
    style J fill:#bfb,stroke:#333,stroke-width:2px
    style K fill:#bfb,stroke:#333,stroke-width:2px
    style L fill:#bfb,stroke:#333,stroke-width:2px
    style M fill:#bfb,stroke:#333,stroke-width:2px
    style N fill:#fbb,stroke:#333,stroke-width:2px
    style O fill:#bbf,stroke:#333,stroke-width:2px
    style P fill:#ffb,stroke:#333,stroke-width:2px
    style Q fill:#ffb,stroke:#333,stroke-width:2px
    style P_EXEC fill:#cce,stroke:#333,stroke-width:2px
    style B_NAV fill:#cce,stroke:#333,stroke-width:2px

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#bbf,stroke:#333,stroke-width:2px
    style D fill:#ccf,stroke:#333,stroke-width:2px
    style E fill:#bfb,stroke:#333,stroke-width:2px
    style F fill:#fbb,stroke:#333,stroke-width:2px
    style G fill:#ffb,stroke:#333,stroke-width:2px
    style H fill:#bfb,stroke:#333,stroke-width:2px
    style I fill:#bfb,stroke:#333,stroke-width:2px
    style J fill:#bfb,stroke:#333,stroke-width:2px
    style K fill:#bfb,stroke:#333,stroke-width:2px
    style L fill:#bfb,stroke:#333,stroke-width:2px
    style M fill:#bfb,stroke:#333,stroke-width:2px
    style N fill:#fbb,stroke:#333,stroke-width:2px
    style O fill:#bbf,stroke:#333,stroke-width:2px
    style P fill:#ffb,stroke:#333,stroke-width:2px
    style Q fill:#ffb,stroke:#333,stroke-width:2px
```

**总结来说：**

*   **`tool` 模块**是工具的“图书馆”和“调度中心”，负责工具的注册、描述和统一调用，它不关心 Agent 如何决策，只提供工具服务。
*   **`runtimes` 模块**是 Agent 的“大脑”和“执行器”，它利用 LLM 进行智能决策（包括工具选择），并通过 `tool` 模块来实际执行任务。它还维护 Agent 的“记忆” (`ExecutionContext`)，实现上下文感知和学习。
*   **`synthesis` 模块**是 Agent 系统的“学习和进化引擎”，它通过分析 `runtimes` 产生的 Agent 执行轨迹，从中提取有价值的任务本质，并生成新的、高质量的种子任务，从而反哺 Agent 的训练和优化，形成一个闭环的学习机制。

这三个模块紧密协作，共同构建了一个智能、自适应的 Agent 平台。

## 5. 平台工具架构优化与演进

为了进一步提升 `Datapresso Agent` 平台的模块化、可扩展性、隔离性以及部署灵活性，我们对现有的工具架构进行了优化。旧架构中，部分核心工具（如 Python 执行和浏览器操作）作为 `Function Tools` 直接嵌入在 `ReasoningRuntime` 进程中。这种方式虽然提供了快速响应和资源共享的优势，但在以下方面存在局限：

*   **隔离性不足**：工具的崩溃或资源泄露可能影响整个 `ReasoningRuntime` 进程。
*   **扩展性受限**：新增或更新工具需要重新部署整个 `ReasoningRuntime`。
*   **技术栈绑定**：`Function Tools` 必须是 Python 函数，限制了使用其他语言实现工具的能力。
*   **资源管理复杂**：难以对单个工具进行独立的资源配额和监控。

为了解决这些问题，我们将逐步将核心 `Function Tools` 转换为独立的 `MCP Servers`。这将使得每个工具作为一个独立的微服务运行，通过 `MCP (Model Context Protocol)` 与 `toolscore` 模块进行通信。

### 5.1 优化目标

本次优化的核心目标是将紧耦合的 `Function Tools` 解耦为独立的 `MCP Servers`，从而实现：

1.  **增强模块化**：每个工具服务独立部署、独立运行，降低模块间的耦合度。
2.  **提升可扩展性**：可以独立扩展和升级单个工具服务，不影响其他组件。
3.  **改善隔离性**：工具服务之间的故障不会相互影响，提高系统稳定性。
4.  **支持多语言**：`MCP Servers` 可以使用任何语言实现，只要遵循 MCP 协议，极大地扩展了工具开发的技术栈选择。
5.  **简化资源管理**：可以为每个工具服务配置独立的资源，便于监控和管理。

### 5.2 优化阶段计划

本次优化分为以下三个主要阶段，其中阶段 1 和阶段 2 已完成：

#### 阶段 1：将现有 Function Tools 转换为独立的 MCP Servers (已完成)

**目的**：将当前直接嵌入 `ReasoningRuntime` 的 Python 执行工具和浏览器操作工具，改造为独立的、可独立部署和运行的 `MCP Servers`。这是实现工具解耦的第一步，为后续的架构调整奠定了基础。

*   **创建 `mcp_servers` 目录**：已创建，用于集中存放所有独立的 MCP Server 实现。
*   **迁移 `enhanced_python_tool`**：
    *   已创建 `mcp_servers/python_executor_server/main.py`：将 `runtimes/reasoning/tools/enhanced_python_tool.py` 的核心逻辑迁移到此文件，并将其封装为一个 MCP Server，使其能够接收并处理来自 `toolscore` 的 Python 代码执行请求。
    *   已创建 `mcp_servers/python_executor_server/Dockerfile`：定义 `python_executor_server` 的 Docker 镜像构建规则，使其能够独立打包和部署。
    *   已修改 `docker-compose.yml`：添加 `python_executor_server` 服务定义，将其集成到 Docker Compose 编排中，实现独立启动和管理。
*   **迁移 `enhanced_browser_tool`**：
    *   已创建 `mcp_servers/browser_navigator_server/main.py`：将 `runtimes/reasoning/tools/enhanced_browser_tool.py` 的核心逻辑迁移到此文件，并将其封装为一个 MCP Server，使其能够接收并处理来自 `toolscore` 的浏览器操作请求。
    *   已创建 `mcp_servers/browser_navigator_server/Dockerfile`：定义 `browser_navigator_server` 的 Docker 镜像构建规则，使其能够独立打包和部署。
    *   已修改 `docker-compose.yml`：添加 `browser_navigator_server` 服务定义，将其集成到 Docker Compose 编排中，实现独立启动和管理。

#### 阶段 2：修改 ReasoningRuntime 以使用远程 toolscore 和 MCP Servers (已完成)

**目的**：调整 `ReasoningRuntime` 的工具调用机制，使其不再直接导入和调用本地的 `Function Tools`，而是通过远程的 `toolscore` MCP Server 来发现和调用工具。这使得 `ReasoningRuntime` 变得更加轻量和通用，不再耦合具体的工具实现。

*   **已修改 `runtimes/reasoning/enhanced_runtime.py`**：
    *   **已移除直接导入和注册**：删除对 `enhanced_python_tool` 和 `enhanced_browser_tool` 的直接导入语句和在 `UnifiedToolLibrary` 中的注册逻辑。`ReasoningRuntime` 不再需要知道这些工具的具体实现细节。
    *   **已修改 `UnifiedToolLibrary` 的实例化方式**：调整 `ReasoningRuntime` 中 `UnifiedToolLibrary` 的创建过程，使其不再是本地实例，而是配置为连接到远程运行的 `toolscore` MCP Server。这意味着 `ReasoningRuntime` 将通过 `MCPToolClient` 通过网络请求与 `toolscore` 进行通信。
    *   **已调整工具调用逻辑**：确保 `ReasoningRuntime` 内部的工具调用逻辑（例如 `tool_library.execute_tool()`）能够正确地通过远程 `toolscore` 进行，而不是尝试在本地进程中执行。

#### 阶段 3：更新 toolscore MCP Server 的功能 (待完成)

**目的**：增强 `core/toolscore/mcp_server.py` 的功能，使其能够作为中央工具注册和路由中心。它将负责接收来自新创建的 `MCP Servers`（如 `python_executor_server` 和 `browser_navigator_server`）的注册请求，并将 `ReasoningRuntime` 发出的工具调用请求路由到正确的、独立的 `MCP Servers`。

*   **修改 `core/toolscore/mcp_server.py`**：
    *   **支持 MCP Server 注册**：确保 `toolscore` 的 MCP Server 能够接收并处理来自其他独立 `MCP Servers`（如 `python_executor_server` 和 `browser_navigator_server`）的工具注册请求。这意味着 `toolscore` 将维护一个动态的、包含所有可用远程工具的注册表。
    *   **支持工具调用路由**：确保 `toolscore` 能够接收来自 `ReasoningRuntime` 的工具调用请求，并根据请求中的 `tool_id` 将其正确地路由到对应的独立 `MCP Server`。`toolscore` 将充当一个代理，将 `ReasoningRuntime` 的请求转发给实际执行工具的 `MCP Server`，并将执行结果返回给 `ReasoningRuntime`。

通过以上三个阶段的优化，我们将实现一个更加健壮、灵活和可扩展的 Agent 平台工具架构，为未来的功能扩展和性能优化奠定坚实的基础。