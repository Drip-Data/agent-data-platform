# Browser Tool (browser_action) 参考指南

本文档为 Agent 提供了关于如何有效使用 `browser` 工具（通过 `browser_action` 类型）的详细说明和最佳实践。Agent 在与 LLM 交互并生成工具调用时，应严格遵守此处的参数格式和使用建议。

## 核心概念

`browser` 工具允许 Agent 与一个虚拟的 Web 浏览器进行交互，执行如页面导航、内容提取、元素点击等操作。Agent 通过指定 `ACTION`（在 LLM Prompt 中定义，对应到工具的具体方法）和相应的 `PARAMETERS` 来控制浏览器的行为。

## 通用参数格式

Agent 在生成 `PARAMETERS` 时，必须遵循以下JSON对象格式：

```json
{
  "action": "specific_browser_action_name", // 例如 browser_navigate, browser_get_text
  "tool": "browser",
  "parameters": {
    // 特定操作的参数会在这里定义
  }
}
```

**重要**：`PARAMETERS` 字段本身必须是一个JSON对象。**绝对禁止使用 `{"raw": ...}` 作为 `PARAMETERS` 的主要结构。** 所有参数都应该有明确的键名。

## 支持的操作 (ACTIONs) 及其参数

以下是 `browser` 工具支持的主要操作及其所需的 `PARAMETERS` 结构。

### 1. `browser_navigate`

导航到指定的 URL。

*   **用途**：打开一个新的网页或跳转到不同的网址。
*   **`PARAMETERS` 结构**：
    ```json
    {
      "url": "<完整的、有效的HTTP或HTTPS URL>"
    }
    ```
*   **参数说明**：
    *   `url` (string, **必需**): 目标网页的完整URL。必须以 `http://` 或 `https://` 开头。
*   **示例**：
    ```json
    {
      "action": "browser_navigate",
      "tool": "browser",
      "parameters": {
        "url": "https://www.google.com/search?q=python"
      }
    }
    ```
*   **成功响应 (`tool_output`) 示例**：
    ```json
    {
      "success": true,
      "url": "https://www.google.com/search?q=python",
      "title": "python - Google Search",
      "content_length": 75000, // 页面内容的字节长度
      "message": "Successfully navigated to https://www.google.com/search?q=python"
    }
    ```
*   **失败响应 (`tool_output`) 示例 (无效URL)**：
    ```json
    {
      "success": false,
      "error_type": "InvalidArgument",
      "error": "URL parameter is missing or invalid. It must be a valid HTTP/HTTPS URL.",
      "message": "Failed to navigate due to invalid URL parameter: some_invalid_url"
    }
    ```
*   **失败响应 (`tool_output`) 示例 (导航错误)**：
    ```json
    {
      "success": false,
      "error_type": "NavigationError",
      "error": "net::ERR_NAME_NOT_RESOLVED at https://nonexistentwebsite12345.com",
      "message": "Failed to navigate to https://nonexistentwebsite12345.com"
    }
    ```

### 2. `browser_get_text`

提取当前页面的文本内容。

*   **用途**：获取整个页面或特定元素的文本信息。
*   **`PARAMETERS` 结构**：
    ```json
    {
      "selector": "<CSS选择器>" // 可选参数
    }
    ```
    或者，如果提取整个页面的 body 文本：
    ```json
    {}
    ```
*   **参数说明**：
    *   `selector` (string, *可选*): 用于定位特定页面元素的CSS选择器。如果提供，则提取该元素的内部文本。如果省略或为空对象 `{}`, 则尝试提取整个 `<body>` 标签的文本。
*   **示例 (提取特定元素)**：
    ```json
    {
      "action": "browser_get_text",
      "tool": "browser",
      "parameters": {
        "selector": "div.article-content p"
      }
    }
    ```
*   **示例 (提取整个页面)**：
    ```json
    {
      "action": "browser_get_text",
      "tool": "browser",
      "parameters": {}
    }
    ```
*   **成功响应 (`tool_output`) 示例**：
    ```json
    {
      "success": true,
      "text": "这是提取到的文本内容...",
      "length": 123 // 文本内容的字符长度
    }
    ```
*   **失败响应 (`tool_output`) 示例 (选择器未找到或页面未初始化)**：
    ```json
    {
      "success": false,
      "error": "Browser not initialized" // 或具体的选择器错误
    }
    ```

### 3. `browser_click`

点击页面上由CSS选择器指定的元素。

*   **用途**：模拟用户点击链接、按钮或其他可交互元素。
*   **`PARAMETERS` 结构**：
    ```json
    {
      "selector": "<CSS选择器>"
    }
    ```
*   **参数说明**：
    *   `selector` (string, **必需**): 用于定位要点击的页面元素的CSS选择器。
*   **示例**：
    ```json
    {
      "action": "browser_click",
      "tool": "browser",
      "parameters": {
        "selector": "button#submit-form"
      }
    }
    ```
*   **成功响应 (`tool_output`) 示例**：
    ```json
    {
      "success": true,
      "message": "Successfully clicked button#submit-form"
    }
    ```
*   **失败响应 (`tool_output`) 示例 (选择器未找到)**：
    ```json
    {
      "success": false,
      "error": "Timeout 30000ms exceeded.\n=========================== logs ===========================\nwaiting for selector \"button#nonexistent-submit-form\"\n============================================================",
      "message": "Failed to click button#nonexistent-submit-form"
    }
    ```

### 4. `browser_fill_form` (示例，基于 `browser_tool.py` 中的 `fill_form`)

在指定的表单输入字段中填入值。

*   **用途**：填写文本框、密码框等表单元素。
*   **`PARAMETERS` 结构**：
    ```json
    {
      "selector": "<CSS选择器>",
      "value": "<要填入的值>"
    }
    ```
*   **参数说明**：
    *   `selector` (string, **必需**): 表单输入字段的CSS选择器。
    *   `value` (string, **必需**): 要填入该字段的文本值。
*   **示例**：
    ```json
    {
      "action": "browser_fill_form", // 注意：此action名需要与LLM Prompt中定义的ACTION列表一致
      "tool": "browser",
      "parameters": {
        "selector": "input[name='username']",
        "value": "testuser"
      }
    }
    ```

### 5. `browser_extract_links` (示例，基于 `browser_tool.py` 中的 `extract_links`)

提取当前页面上所有可见的链接。

*   **用途**：获取页面上的导航链接、资源链接等。
*   **`PARAMETERS` 结构**：
    ```json
    {} // 通常不需要参数
    ```
*   **示例**：
    ```json
    {
      "action": "browser_extract_links", // 注意：此action名需要与LLM Prompt中定义的ACTION列表一致
      "tool": "browser",
      "parameters": {}
    }
    ```
*   **成功响应 (`tool_output`) 示例**：
    ```json
    {
      "success": true,
      "links": [
        {"text": "首页", "href": "https://example.com/", "title": "返回首页"},
        {"text": "关于我们", "href": "https://example.com/about", "title": ""}
      ],
      "count": 2
    }
    ```

## 常见错误与应对策略

Agent 在使用浏览器工具时，应能理解并尝试处理以下常见错误：

1.  **`InvalidArgument` (通常由工具层参数校验返回)**
    *   **原因**：提供的参数不符合要求（例如，`url` 缺失、格式错误；`selector` 缺失）。
    *   **应对**：Agent 应在 `THINKING` 过程中检查其生成的参数，如果发现问题，应修正参数或向用户请求缺失的信息。

2.  **`NavigationError` (例如 `net::ERR_NAME_NOT_RESOLVED`, `TimeoutError` from `page.goto`)**
    *   **原因**：URL无法访问（域名不存在、网络问题、服务器无响应、页面加载超时）。
    *   **应对**：
        *   检查URL是否拼写正确。
        *   尝试等待一段时间后重试（如果适用）。
        *   如果多次失败，考虑该URL不可达，向用户报告并询问是否有备用URL或信息源。
        *   对于超时，可以考虑是否是页面过于复杂或网络条件不佳。

3.  **Selector Not Found (通常在 `click`, `get_text`, `fill_form` 中发生)**
    *   **原因**：提供的CSS选择器未能匹配到页面上的任何元素。可能是选择器错误、页面结构变化或元素尚未加载。
    *   **应对**：
        *   检查选择器是否正确无误。
        *   尝试使用更通用或更具体的选择器。
        *   如果页面是动态加载的，可能需要在操作前增加等待时间或检查特定元素是否可见。
        *   如果无法定位，向用户报告并请求帮助或确认选择器。

4.  **反爬虫机制或访问限制**
    *   **现象**：页面返回验证码、访问被拒绝、IP被封锁、或内容与预期严重不符。
    *   **应对**：
        *   Agent 目前难以直接处理复杂的反爬虫机制。
        *   应识别这类情况（例如，通过页面标题、特定文本内容判断），并向用户报告问题，请求用户手动处理或提供其他方式获取信息。

## 最佳实践

*   **明确意图**：在 `THINKING` 过程中清晰说明希望通过浏览器操作达到什么目的。
*   **参数先行**：在生成 `ACTION` 和 `PARAMETERS` 之前，确保所有必需的信息（如URL、搜索词、选择器）已经从任务描述或之前的步骤中获取。
*   **小步快跑**：对于复杂任务，将其分解为多个简单的浏览器操作步骤。
*   **观察与调整**：仔细分析每次操作的 `tool_output`。如果操作失败或结果不符合预期，应在下一步的 `THINKING` 中分析原因并调整策略。
*   **URL 验证**：在尝试导航前，Agent 内部应尽可能对 URL 的基本格式进行判断（例如，是否以 http/https 开头）。（此点已通过工具层校验部分实现）
*   **选择器健壮性**：优先使用ID选择器（如果可用且唯一），其次是稳定的类名或属性选择器。避免使用过于依赖页面结构或动态生成内容的选择器。

通过遵循本指南，Agent 可以更可靠、更高效地使用浏览器工具完成任务。