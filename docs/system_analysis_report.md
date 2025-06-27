# 系统诊断与优化方案报告

## 1. 概述

通过对 `unified.log` 日志和 `trajectories_collection.json` 轨迹文件的深入分析，结合对代码库的全面审查，我们识别出当前系统在稳定性、健壮性和智能性方面存在的多个核心问题。本报告将逐一剖析这些问题的根本原因，并提供一套完整的、可执行的解决方案。

---

## 2. 诊断详情与解决方案

### 2.1. `microsandbox_server` 服务不稳定且存在连接问题

-   **问题表现**:
    -   **启动超时**: 日志显示 `microsandbox_server` 经常无法在30秒内准备就绪。
    -   **执行失败**: 轨迹 `15f8b537-45f4-4e31-9f31-14ec15290720` 显示，当尝试使用 `microsandbox_execute` 时，发生了致命错误：“无法连接到 MCP 服务器: ws://localhost:8090/websocket”。

-   **根本原因分析**:
    1.  **无端口配置**: `config/mcp_servers.json` 中，`microsandbox_server` 没有像其他服务一样预设端口，导致 `mcp_server_launcher.py` 无法对其进行有效的端口就绪检测。
    2.  **启动逻辑缺陷**: `mcp_servers/microsandbox_server/main.py` 缺少一个明确的“就绪”信号（如HTTP健康检查端点），导致启动器只能依赖于进程是否存在，这并不可靠。
    3.  **连接失败**: 客户端在尝试连接 `ws://localhost:8090` 时失败，表明 `microsandbox_server` 即使进程在运行，其WebSocket服务也未在预期端口上成功监听。

-   **解决方案**:
    1.  **分配静态端口**: 在 `config/mcp_servers.json` 中为 `microsandbox_server` 分配一个固定的端口（例如 `8090`），并设置 `"auto_start": true`。
    2.  **实现健康检查**: 在 `mcp_servers/microsandbox_server/main.py` 中，使用 `FastAPI` 实现一个简单的HTTP健康检查端点（如 `/health`）。
    3.  **完善就绪检测**: 修改 `services/mcp_server_launcher.py`，使其在启动 `microsandbox_server` 后，轮询其 `/health` 端点，以确认服务真正就绪。
    4.  **修复WebSocket服务**: 审查 `mcp_servers/microsandbox_server/main.py` 中的WebSocket服务器启动逻辑，确保它能正确绑定到 `8090` 端口并处理连接。

### 2.2. `deepsearch` 工具执行持续失败

-   **问题表现**:
    -   在所有相关的轨迹中，调用 `deepsearch.research` 动作最终都以一个模糊的 `Unknown error` 失败告终。

-   **根本原因分析**:
    -   **错误屏蔽**: 在 `mcp_servers/deepsearch_server/deepsearch_tool.py` 的 `research` 方法中，存在一个过于宽泛的 `try...except Exception` 块，它捕获了所有底层异常但没有记录或返回具体的错误信息。

-   **解决方案**:
    1.  **精细化异常处理**: 修改 `mcp_servers/deepsearch_server/deepsearch_tool.py`。移除通用的 `except Exception`，替换为针对具体预期异常的捕获。
    2.  **透传错误信息**: 在异常处理块中，记录详细的错误堆栈信息，并将具体的错误原因作为返回结果的一部分。

### 2.3. LLM响应解析失败与Guardrails验证错误

-   **问题表现**:
    -   **JSON解析失败**: 日志中频繁出现 `JSON解析失败: Extra data` 和 `JSON结构重建失败` 的错误。
    -   **Guardrails验证失败**: 日志中出现 `Guardrails验证失败: 输出验证失败: API must be provided.`。

-   **根本原因分析**:
    1.  **提示词脆弱**: `runtimes/reasoning/enhanced_runtime.py` 中构建的系统提示词对于JSON格式的约束不够强。
    2.  **解析器鲁棒性不足**: `core/llm/response_parsers/reasoning_response_parser.py` 中的修复逻辑无法处理复杂的格式问题。
    3.  **Guardrails配置错误**: 在 `core/llm/guardrails_middleware.py` 中初始化 `Guard` 对象时，未能正确提供其验证器所需的 `api` 或其他依赖。

-   **解决方案**:
    1.  **强化提示词**: 在 `runtimes/reasoning/enhanced_runtime.py` 的相关prompt中，使用更强硬的指令，并加入 "few-shot" 示例。
    2.  **优化解析器**: 改进 `core/llm/response_parsers/reasoning_response_parser.py`，在尝试 `json.loads` 之前，使用更强大的正则表达式 `re.search(r'\{.*\}', response, re.DOTALL)` 来提取被包裹的JSON主体。
    3.  **修复Guardrails配置**: 审查 `core/llm/guardrails_middleware.py`，确保在创建 `Guard.from_rail(...)` 或类似调用时，传递了所有必需的参数。

### 2.4. 任务状态评估逻辑混乱

-   **问题表现**:
    -   **假性成功**: 轨迹 `f5eba3ac-9a25-49b7-80ba-bfab6a176b94` 被标记为成功，但其最后一个关键步骤 `deepsearch.research` 实际上失败了。
    -   **无效循环**: 轨迹 `baca3929-a36e-452a-821b-55db594ebb37` 中，Agent反复成功执行 `browser_navigate`，但从未推进到任务的下一步。

-   **根本原因分析**:
    -   **成功判断标准单一**: `core/trajectory_enhancer.py` 或 `runtimes/reasoning/enhanced_runtime.py` 中的成功判断逻辑过于简单。
    -   **缺乏进展检测**: `core/step_planner.py` 和 `enhanced_runtime.py` 的循环逻辑中，缺少对“无效进展”的检测。

-   **解决方案**:
    1.  **引入目标驱动的完成度检查**: 在 `runtimes/reasoning/enhanced_runtime.py` 的任务结束阶段，引入一个基于LLM的“完成度检查器”。
    2.  **实现循环检测**: 在 `enhanced_runtime.py` 的主执行循环中，增加一个机制来检测重复的、无意义的工具调用。

### 2.5. SynthesisCore 合成核心处理失败

-   **问题表现**:
    -   日志显示 `SynthesisCore处理失败: Unknown error`，并且 `未提取到有效语料`。

-   **根本原因分析**:
    -   **数据结构不匹配**: `core/synthesiscore/corpus_ingestor.py` 在解析轨迹 `trajectories_collection.json` 的数据结构时，可能期望找到特定的字段或格式，但由于轨迹结构的变化或错误，导致其无法提取任何内容。

-   **解决方案**:
    1.  **增加日志和验证**: 在 `core/synthesiscore/corpus_ingestor.py` 中，为每个被处理的轨迹和步骤添加详细的日志。
    2.  **健壮性处理**: 在解析轨迹时，使用 `.get()` 方法并提供默认值来安全地访问字典键。
    3.  **暴露根本错误**: 捕获并记录导致 `Unknown error` 的具体异常。
