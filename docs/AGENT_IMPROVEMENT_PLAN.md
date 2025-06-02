# Agent 数据平台执行轨迹问题分析与综合解决方案

## I. 引言与问题确认

基于对 Agent 执行轨迹数据（特别是 `agent-data-platform/output/trajectories/trajectories_collection.json`）的分析，我们共同识别出当前系统在处理涉及浏览器的任务时存在的若干核心问题。这些问题主要集中在参数传递的准确性、与外部网站交互的鲁棒性、Agent 内部思考与实际行动的一致性，以及对所使用工具的理解和运用上。

核心问题领域包括：

1.  **浏览器操作中的URL/参数传递错误**：这是导致任务失败的最主要原因。Agent 在调用浏览器工具（如 `browser_action`）时，经常未能正确生成、传递或使用有效的URL及其他必要参数。一个典型现象是，即使 Agent 在其 `thinking` 过程中可能已意识到需要特定URL，但在生成 `execution_code` 时，`tool_input` 仍可能出现 `{"raw": ""}` 或缺少关键的 `url` 字段，导致导航或操作失败。
    *   **相关文件**：
        *   Agent 的决策和工具参数生成主要受 [`agent-data-platform/core/llm_client.py`](agent-data-platform/core/llm_client.py:1) 中的 Prompt 构建逻辑（尤其是 `_build_reasoning_prompt` ([`agent-data-platform/core/llm_client.py:308`](agent-data-platform/core/llm_client.py:308))）影响。
        *   工具参数的解析发生在 [`agent-data-platform/core/llm_client.py`](agent-data-platform/core/llm_client.py:1) 的 `_parse_reasoning_response` ([`agent-data-platform/core/llm_client.py:450`](agent-data-platform/core/llm_client.py:450)) 方法中。
        *   实际的浏览器工具调用由 [`agent-data-platform/runtimes/reasoning/runtime.py`](agent-data-platform/runtimes/reasoning/runtime.py:1) 协调，并由 [`agent-data-platform/runtimes/reasoning/tools/browser_tool.py`](agent-data-platform/runtimes/reasoning/tools/browser_tool.py:1) 执行。
2.  **外部网站访问限制与交互鲁棒性不足**：
    *   **反爬虫机制**：任务在尝试访问某些外部网站（如Google搜索、CoinMarketCap）时，可能会遇到反爬虫机制（如验证码页面、IP封锁），导致无法获取预期数据。
    *   **网络超时**：对外部网站的请求可能因网络延迟或服务器响应缓慢而超时。
    *   **重试与容错缺乏**：当前 Agent 在遇到这些访问问题时，缺乏有效的重试机制和容错策略。
3.  **Agent 内部逻辑与状态管理缺陷**：
    *   **思考与行动脱节**：Agent 的 `thinking` 过程有时能识别问题或正确的下一步，但这种认知未能准确转化为实际的工具调用参数。
    *   **上下文记忆不足**：在多步骤任务中，Agent 可能难以有效追踪和传递关键上下文信息（如当前页面的URL、从页面中提取的新链接或数据），导致后续步骤操作基于错误或过时的信息。
4.  **工具理解与使用不当**：
    *   Agent 可能未完全或准确理解其可用的浏览器工具（尤其是 `browser_action` 及其各种子操作）的参数要求、预期行为和输出格式。
    *   工具文档可能不够清晰或详尽，未能提供足够的正确使用范例和错误处理指导。

## II. 综合解决方案策略

为系统性解决上述问题，我们制定了以下多方面、分层次的改进策略：

### A. 支柱一：强化 Prompt 工程与 Agent 指导

1.  **精确的工具使用指令与示例**：
    *   在 Agent 的核心系统 Prompt 中，集成清晰、具体、强制性的浏览器工具使用规则和格式化示例。
    *   **主要修改目标文件**：[`agent-data-platform/core/llm_client.py`](agent-data-platform/core/llm_client.py:1) 中的 `_build_reasoning_prompt` ([`agent-data-platform/core/llm_client.py:308`](agent-data-platform/core/llm_client.py:308)) 方法。
    *   **示例指令 (集成用户建议)**：
        ```markdown
        当你需要使用浏览器工具时，请遵循以下规则：

        1.  **导航到新URL时**，必须使用以下格式：
            `{"action": "browser_navigate", "tool": "browser", "parameters": {"url": "https://example.com"}}`
            确保 `url` 字段包含完整的、以 `http://` 或 `https://` 开头的有效网址。

        2.  **提取当前页面文本时**，可使用（selector可选）：
            `{"action": "browser_get_text", "tool": "browser", "parameters": {"selector": "optional-css-selector"}}`

        3.  **绝对禁止使用空参数或不完整的参数调用**，例如 `{"raw": ""}` 或仅有 `{"action": "browser_navigate"}`。这会导致操作失败。

        4.  **参数检查**：在每次调用浏览器工具前，请在思考中确认所有必需参数（尤其是 `url`）均已获取并正确填充。如果缺少必要参数，必须先通过提问用户或其他方式获取，或明确指出无法继续。

        5.  **错误处理**：如果上一步浏览器操作失败，不要简单重复相同的操作。应分析错误信息（`error_type`, `error_message`），并在思考中提出具体的修正方案（如修改URL、更换选择器、尝试不同操作）或向用户报告问题。
        ```

2.  **动态 Prompt 增强 (长期目标)**：
    *   研究并实现基于 Agent 近期错误历史动态调整提示的机制。例如，如果 Agent 近期频繁出现URL相关错误，系统可以临时在 Prompt 中加入更强的提醒：“注意：您最近在处理URL时遇到了问题。请确保所有URL都是完整的，包含协议前缀，并在每次浏览器导航前验证URL的有效性。”

### B. 支柱二：改进工具、文档与错误处理机制

1.  **工具层面的参数校验与包装器 (用户核心建议)**：
    *   为核心的浏览器工具函数（如处理 `browser_navigate`, `browser_get_text` 等动作的后端逻辑）实现一层参数校验包装器。
    *   **主要修改目标文件**：[`agent-data-platform/runtimes/reasoning/tools/browser_tool.py`](agent-data-platform/runtimes/reasoning/tools/browser_tool.py:1) 中的相关方法，例如 `navigate` ([`agent-data-platform/runtimes/reasoning/tools/browser_tool.py:41`](agent-data-platform/runtimes/reasoning/tools/browser_tool.py:41))。
    *   **功能**：
        *   在实际执行浏览器操作前，自动检查传入的 `parameters`。
        *   对于导航操作，强制 `parameters.url` 必须存在、非空，且为合法的 HTTP/HTTPS URL。
```python
# 示例：在 browser_tool.py 中添加参数校验包装器
import re
from agent_data_platform.runtimes.reasoning.tools.browser_tool import ToolError

def navigate(self, parameters):
    url = parameters.get("url")
    # 强制检查：url 非空，且以 http:// 或 https:// 开头
    if not url or not re.match(r"^https?://", url):
        raise ToolError(
            "MissingOrInvalidURL",
            "操作 'browser_navigate' 需要一个有效的 'url' 参数。请提供如 https://example.com 格式的 URL。"
        )
    # 通过校验后调用底层导航接口
    return self._browser.navigate(url)
```
        *   如果关键参数缺失或格式错误，包装器应直接阻止工具执行，并可以考虑返回一个结构化的错误信息，提示 Agent 需要修正输入或询问用户（例如，返回类似 `ToolError("MissingOrInvalidURL", "操作 'browser_navigate' 需要一个有效的 'url' 参数。请提供如 https://example.com 格式的URL。")` 的信息）。
    *   **好处**：从源头拦截大量因参数错误导致的低级失败，减轻 Agent 自行诊断此类问题的负担。

2.  **详尽的工具参考指南**：
    *   为 `browser_action` 工具及其支持的各种 `action` 类型创建全面、易懂的 Markdown 文档。
    *   **内容应包括 (集成用户建议)**：
        *   每种 `action`（如 `navigate`, `get_text`, `fill_and_submit`, `extract_element_attribute` 等）的用途描述。
        *   必需参数和可选参数的详细列表，包括参数名、数据类型、预期格式和具体示例。
        *   强调 `url` 参数在导航类操作中的核心地位和格式要求（必须包含协议前缀）。
        *   常见错误代码/消息（如 "Cannot navigate to invalid URL", "Timeout exceeded", "Element not found"）的解释、可能原因及推荐的 Agent 应对策略（例如，检查URL、尝试备用选择器、调整超时、告知用户）。
        *   工具成功执行后，`tool_output` 的典型结构和含义。

3.  **Agent 级别的错误分析与自适应重试逻辑**：
    *   在 Agent 的 Prompt 和内部逻辑中，强化对工具执行结果（尤其是错误信息）的分析能力。
```python
# 示例：BrowserStateManager 增强实现
# 文件：agent-data-platform/core/browser_state_manager.py
class BrowserStateManager:
    def __init__(self):
        self.current_url = None
        self.page_title = None
        self.navigation_history = []  # 列表项：{"url", "success", "timestamp", "error"}
        self.last_extracted_text_summary = ""
        self.available_links_on_page = []  # 列表项：{"url", "text"}
        self.error_history_for_current_task = []  # 列表项：{"type", "message", "timestamp"}

    def update_navigation(self, url, success: bool, error: str = None):
        from time import time
        self.navigation_history.append({
            "url": url,
            "success": success,
            "timestamp": time(),
            "error": error
        })
        if success:
            self.current_url = url

    def update_page_info(self, title: str, links: list, full_text: str):
        self.page_title = title
        self.available_links_on_page = [{"url": u, "text": t} for u, t in links]
        # 摘要前 500 字
        self.last_extracted_text_summary = full_text[:500]

    def record_error(self, error_type: str, message: str):
        from time import time
        self.error_history_for_current_task.append({
            "type": error_type,
            "message": message,
            "timestamp": time()
        })
```
    *   根据错误类型，指导 Agent 采取不同的重试或修正策略（例如，对于网络超时或临时服务器错误，可以尝试1-2次带退避策略的重试；对于参数错误，则应修正参数或询问用户）。

### C. 支柱三：鲁棒的 Agent 上下文与状态管理

1.  **引入全局/会话级「浏览器状态管理器」 (用户核心建议)**：
    *   在 Agent 的执行环境中或其调用的运行时模块中，实现一个 `BrowserStateManager` (或类似 `SessionContext` 的概念)。
    *   **追踪的关键状态信息应包括**：
        *   `current_url`: 当前浏览器标签页成功加载的URL。
        *   `page_title`: 当前页面的标题。
        *   `navigation_history`: 一个包含 `{url: string, success: boolean, timestamp: number, error?: string}` 对象的列表，记录导航尝试。
        *   `last_extracted_text_summary`: 上次提取文本的摘要或关键片段。
        *   `available_links_on_page`: 当前页面中探测到的主要链接列表（URL和锚文本）。
        *   `error_history_for_current_task`: 当前任务中发生的浏览器相关错误的简要记录（类型、次数）。
    *   **更新机制**：每次浏览器工具调用成功或失败后，相应更新此状态管理器中的信息。

2.  **状态驱动的决策与上下文利用**：
    *   Agent 在规划下一步浏览器操作时，应被引导（通过 Prompt）或能够（通过内部逻辑）查询和利用这些状态信息。
    *   例如：如果需要再次访问之前已成功导航的页面，可以直接从 `current_url` 或 `navigation_history` 获取。如果需要点击链接，可以从 `available_links_on_page` 中选择。如果某个URL多次导航失败，可以参考 `navigation_history` 和 `error_history_for_current_task` 来决定是否放弃或尝试不同策略。

### D. 支柱四：高级外部网站交互策略

1.  **反限制与请求优化技术 (集成用户建议)**：
    *   在执行浏览器请求的底层实现中，集成更智能的请求策略：
        *   **合理的默认超时设置**：例如，30-60秒，并允许 Agent 在特定情况下（如有提示）请求更长的超时。
        *   **智能页面加载等待策略**：默认使用如 `domcontentloaded`，但在超时或特定情况下可降级到 `commit`。
        *   **标准 User-Agent**：默认使用一个常见的浏览器 User-Agent 字符串。考虑未来支持 User-Agent 轮换。
        *   **请求延迟**：在连续对同一域名进行请求时，引入小的随机延迟（例如1-3秒），以模仿人类行为，降低被检测风险。
        *   **Cookie 与会话管理**：如果任务需要在同一网站内进行多步操作且依赖登录状态或会话，需要确保浏览器会话能够保持。

2.  **优雅处理访问失败与内容提取挑战**：
    *   当持续遇到访问限制（如验证码、IP封锁）或目标网站结构复杂难以提取信息时，Agent 应能：
        *   识别这种情况（例如，通过分析页面内容或错误代码）。
        *   向用户清晰报告问题，并解释已尝试的策略。
        *   请求用户提供替代信息源、手动完成特定步骤或提供更具体的提取指令（如XPath）。

### E. 支柱五：Agent 自学习与反馈机制 (长期目标)

1.  **错误模式识别与解决方案知识库**：
    *   系统性地收集和分类 Agent 在浏览器操作中遇到的错误模式。
    *   为每种常见错误模式关联一组推荐的解决方案或排查步骤。
    *   Agent 在遇到错误时，可以查询此知识库以获得解决灵感。

2.  **成功案例与模式记忆**：
    *   记录和分析成功的浏览器交互序列（包括任务描述、思考过程、工具调用链、上下文状态变化）。
    *   从中提取可复用的成功模式，用于指导 Agent 未来处理类似任务。

3.  **监控、日志与持续优化 (用户核心建议)**：
    *   在工具调用层面，详细记录关键信息：输入参数、参数校验结果、请求耗时、HTTP状态码（如果适用）、重试次数、最终结果（成功/失败及错误信息）。
    *   建立监控仪表盘，定期分析最常见的失败模式、高频错误URL、工具使用瓶颈等，为持续优化 Prompt、工具逻辑和 Agent 策略提供数据支持。

## III. 分阶段实施路线图

1.  **紧急修复 (立即行动)**：
    *   **工具层**：为 `browser_action` 的导航相关操作实现基础的 `url` 参数强制校验（非空、基本格式）。如果校验失败，工具应返回明确的错误信息。
    *   **Prompt层**：在 Agent 的系统 Prompt 中，紧急加入关于 `browser_navigate` 时 `url` 参数必须提供且格式正确的强提醒，并给出正确示例。

2.  **短期改进 (1-2周)**：
    *   **Prompt层**：全面更新系统 Prompt，包含针对各种常见浏览器操作（导航、提取文本、点击等）的正确 `tool_input` 格式示例，明确禁止 `{"raw": ""}` 等错误用法。
    *   **文档**：撰写并发布第一版 `browser_action` 工具的详细参考指南（Markdown格式），涵盖参数、示例和常见错误处理。
    *   **Agent逻辑**：为 Agent 实现简单的、基于特定错误类型（如网络超时）的重试逻辑（例如，固定重试1次，延迟几秒）。

3.  **中期优化 (1-2个月)**：
    *   **状态管理**：设计并初步实现 `BrowserStateManager` (或 `SessionContext`)，至少包含 `current_url` 和简化的 `navigation_history`。Agent 逻辑开始利用这些状态。
    *   **工具层/运行时**：在浏览器请求的底层实现中，加入可配置的超时、User-Agent 设置和基本的请求间随机延迟。
    *   **Agent逻辑**：增强 Agent 对工具错误输出的分析能力，并根据错误类型选择更合适的后续行动（修正参数、换策略、或放弃并报告）。
    *   **日志**：开始系统性记录浏览器工具调用的详细日志。

4.  **长期策略 (持续迭代)**：
    *   **状态管理**：完善 `BrowserStateManager`，增加更多有用的状态信息和管理功能。
    *   **自学习**：逐步构建错误模式库和成功案例库，探索将其用于 Agent 决策辅助或 Prompt 动态调整的方法。
    *   **高级交互**：研究更复杂的网页内容提取技术（如基于LLM的智能内容定位）和交互策略（如处理动态加载内容、应对更复杂的反爬机制）。
    *   **性能优化**：根据日志和监控数据，持续优化并发、缓存（如用户建议的对常访问页面启用本地缓存）和重试策略。

## IV. 效果评估与成功指标

我们将采用以下组合指标来衡量各项改进措施的成效：

1.  **浏览器操作成功率**：定义为（成功的浏览器工具调用次数 / 总的浏览器工具调用次数）。目标是显著提升此比率。
2.  **特定错误类型发生频率**：重点关注因无效URL/参数、超时、访问被拒等导致的错误。目标是大幅降低这些错误的发生频率。
3.  **任务完成率**：对于依赖浏览器操作的任务，其端到端的成功完成率。
4.  **平均任务完成时间/步骤数**：对于可比较的任务，观察完成时间和所需步骤数是否减少。
5.  **重试效率**：在启用重试机制后，重试成功解决问题的比例。
6.  **用户反馈/手动干预率**：收集用户对 Agent 表现的反馈，并观察需要用户手动介入修正或提供信息的频率是否下降。

通过以上综合方案的实施和持续迭代，我们期望能显著提升 Agent 在处理浏览器相关任务时的自主性、鲁棒性和效率。

## 1. 全面操作埋点 ＆ 日志
- 在每个 Step 执行前后记录：
  - step_id（唯一标识）
  - action_type（如“navigate”、“click”、“llm_call” 等）
  - tool（调用的工具名称）
  - parameters（传入参数，JSON 结构）
  - start_ts、end_ts、duration
  - success（布尔）
  - error_type、error_message（若失败时填充）
- 日志使用 JSON 格式化，便于 ELK/Prometheus 等系统采集。例如：
  ```json
  {
    "task_id": "xxx-uuid",
    "step_id": "step-1",
    "action_type": "navigate",
    "tool": "browser",
    "parameters": { "url": "https://..." },
    "start_ts": 1625247600.123,
    "end_ts": 1625247601.456,
    "duration": 1.333,
    "success": true,
    "error_type": null,
    "error_message": null
  }
  ```

## 2. 任务级元数据管理
- 为每个 Task 分配唯一 `task_id`（UUID）。
- 记录 task start_time、end_time、status（success/partial/fail）。
- 聚合该 Task 的所有 steps、outputs、token_usage、resource_usage 到一份 summary。

## 3. 资源与令牌消耗监控
- 在每次 LLM 调用前后，采集 token 使用情况（使用 LLM API 返回的 `usage` 字段或本地计算）。
- 结合 `psutil`（或 Prometheus node_exporter）在 Step 前后采集当前进程的 CPU、内存等指标：
  ```python
  import psutil, time, uuid
  proc = psutil.Process()
  cpu_before = proc.cpu_percent(interval=None)
  mem_before = proc.memory_info().rss
  # 执行工具调用…
  cpu_after = proc.cpu_percent(interval=None)
  mem_after = proc.memory_info().rss
  ```
- 将上述资源指标纳入 Step 日志，方便事后分析。

## 4. 日志采集与聚合
- 配置日志输出到文件/STDOUT，并接入文件采集器（Filebeat）或直接推送到 ELK/Prometheus。
- 定期汇总 Task 级别的执行报告，供监控面板展示。