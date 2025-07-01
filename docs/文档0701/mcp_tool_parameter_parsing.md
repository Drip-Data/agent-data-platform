# MCP 工具参数解析与数据清洗方案 (V4 Aligned)

**注意: 本文档仅作为各 MCP Server 工具能力的详细分析参考。关于权威的、最终的交互格式、标签和数据规范，请务必以 `system_design_and_rl_data_synthesis.md` 为准。**

本文档旨在分析项目中各个 MCP Server 提供的工具能力，并为设计一套标准化的、面向模型训练的数据提取与注入方案提供基础。

---

## 核心原则

1.  **面向模型决策**: 注入给模型的数据，应该是能帮助它做出下一步正确决策的**最小信息集**。
2.  **标准化标签**: 采用统一的、可扩展的标签体系来表示工具调用和结果返回。**[已更新]** 标签体系遵循 V4 方案。
3.  **结构化提取**: 优先使用 JSON 键值提取和 XML 解析，而不是脆弱的正则表达式或字符串查找。
4.  **集中处理**: 将所有数据清洗和格式化逻辑集中到统一的“结果处理器”中（通常在 `Orchestrator` 或 `Dispatcher` 中实现）。

---

## V4 标签体系回顾

-   **工具调用 (模型生成)**:
    ```xml
    <!-- 单工具调用 -->
    <server_name><tool_name>parameter_string_or_json</tool_name></server_name>

    <!-- 多工具调用 -->
    <sequential>
        <server_name_1><tool_name_1>...</tool_name_1></server_name_1>
        <server_name_2><tool_name_2>...</tool_name_2></server_name_2>
    </sequential>
    ```
    **执行信号**: 上述调用块之后，必须跟随 `<execute_tools />`

-   **结果注入 (系统注入)**:
    ```xml
    <result index="N">processed_output</result>
    ```

---

## `microsandbox_server`

### 1. 工具能力分析
-   **`execute_python`**: 执行 Python 代码。
-   **`install_package`**: 安装 Python 包。
-   其他管理类工具...

### 2. 数据提取与注入策略 (V4 示例)

#### `execute_python`
-   **调用示例**:
    ```xml
    <microsandbox_server><execute_python>print("hello")</execute_python></microsandbox_server>
    <execute_tools />
    ```
-   **结果注入示例**:
    -   **成功**:
      ```xml
      <result index="0">hello</result>
      ```
    -   **失败**:
      ```xml
      <result index="0">NameError: name 'prnt' is not defined</result>
      ```

#### `install_package`
-   **调用示例**:
    ```xml
    <microsandbox_server><install_package>numpy</install_package></microsandbox_server>
    <execute_tools />
    ```
-   **结果注入示例**:
    -   **成功**:
      ```xml
      <result index="0">Package 'numpy' installed successfully.</result>
      ```
    -   **失败**:
      ```xml
      <result index="0">ERROR: Could not find a version that satisfies the requirement non_existent_package</result>
      ```
---

## `browser_use_server`

### 1. 工具能力分析
-   **`navigate`**: 导航到 URL。
-   **`extract_content`**: 提取页面内容。
-   其他交互类工具...

### 2. 数据提取与注入策略 (V4 示例)

#### `navigate`
-   **调用示例**:
    ```xml
    <browser_use_server><navigate>https://www.wikipedia.org</navigate></browser_use_server>
    <execute_tools />
    ```
-   **结果注入示例**:
    ```xml
    <result index="0">Navigated to https://www.wikipedia.org. Page title: Wikipedia. Key elements: [Search Box, Language Links, Main Content Area]</result>
    ```

---

## `deepsearch_server`

### 1. 工具能力分析
-   **`research`**: 对问题进行深度研究。
-   `quick_research`, `comprehensive_research`...

### 2. 数据提取与注入策略 (V4 示例)

#### `research`
-   **调用示例**:
    ```xml
    <deepsearch_server><research>Benefits of server-side rendering</research></deepsearch_server>
    <execute_tools />
    ```
-   **结果注入示例**:
    ```xml
    <result index="0">
    **Benefits of Server-Side Rendering (SSR):**

    1.  **Improved SEO**: Search engine crawlers can easily index the fully rendered HTML.
    2.  **Faster First Contentful Paint (FCP)**: Users see content quicker as the browser receives a ready-to-render page.
    </result>
    ```

---

## `search_tool_server`

### 1. 工具能力分析
-   **`search_file_content`**: 在文件中搜索内容。
-   **`list_code_definitions`**: 列出代码定义。
-   其他元工具...

### 2. 数据提取与注入策略 (V4 示例)

#### `search_file_content`
-   **调用示例**:
    ```xml
    <search_tool_server><search_file_content>{"file_path": "main.py", "pattern": "import"}</search_file_content></search_tool_server>
    <execute_tools />
    ```
-   **结果注入���例**:
    -   **成功**:
      ```xml
      <result index="0">Matches in 'main.py': [Line 1: import os], [Line 2: import sys]</result>
      ```
    -   **文件未找到**:
      ```xml
      <result index="0">Error: File not found at path 'main.py'.</result>
      ```
