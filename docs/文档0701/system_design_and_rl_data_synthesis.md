# Agent 系统核心设计与强化学习数据生成方案 (V4 - Final)

本文档旨在精确描述一个极致简洁、流式交互的 Agent 系统。它记录了设计的演进过程，并详细阐述了最终确定的交互格式、执行流程、各工具的详细输入输出规范，以及具体的实施计划，以确保系统的高效、动态适应性，并为未来模型训练提供最直接、干净的轨迹数据。

---

## 1. 设计演进与核心原则

我们的设计经过了数次迭代（V1到V4），最终确立了以下核心原则：

-   **极致简洁**: 交互格式必须最大程度地减少冗余，降低模型生成内容的复杂度。
-   **信号明确**: 使用自闭合的 `<execute_tools />` 作为清晰、无歧义的执行触发器。
-   **动态适应**: 系统能无缝处理“单步动态观察”和“多步一次性规划”两种模式。
-   **数据纯净**: 最终产出的轨迹数据是一个忠实记录交互全过程的、干净的对话流，可以直接用于模型训练。

---

## 2. 最终版核心 XML 交互语言

系统与模型的交互遵循一套极简的 XML 方言。

### 2.1. 思考: `<think>`
-   **用途**: 承载模型的推理过程、计划、分析和自我修正。
-   **格式**: `<think>...</think>`
-   **规则**: 不触发任何工具执行，纯粹是思维链的体现。

### 2.2. 工具调用与执行控制
-   **单个工具调用 (无需包裹)**:
    -   **用途**: 处理动态、不确定性任务的基础模式，实现“走一步，看一步”。
    -   **格式**: `<server_name><tool_name>raw_query_string_or_json</tool_name></server_name>`

-   **多个工具调用 (必须包裹)**:
    -   **用途**: 当模型能够一次性规划多个确定的动作时使用。
    -   **并行格式**: `<parallel>...</parallel>`
    -   **串行格式**: `<sequential>...</sequential>`

### 2.3. 执行触发器: `<execute_tools />`
-   **用途**: 模型“回合结束，请求执行”的明确信号。
-   **格式**: `<execute_tools />` (自闭合)
-   **规则**: 在生成了一个**独立的工具调用**或一个**完整的 `<parallel>`/`<sequential>` 块**之后，模型必须紧跟着输出此标签来触发系统执行。

### 2.4. 结果反馈: `<result>`
-   **用途**: 系统向模型反馈工具执行的结果。
-   **格式**: `<result index="N">processed_output</result>`
-   **关键设计**:
    -   `index` 属性: 从 0 开始，严格对应指令块中工具的顺序。对于独立的工具调用，`index` 恒为 0。
    -   `processed_output` 内容: **处理后的干净结果** (成功输出或简洁的错误信息)，不含任何子标签，以便模型直接解析。

### 2.5. 最终答案: `<answer>`
-   **用途**: 当 Agent 完成任务时，使用此标签给出最终答案。
-   **格式**: `<answer>...</answer>`

---

## 3. 工具输入/输出详细规范 (Tool I/O Specification)

本章节将精确定义每个核心工具的输入（模型如何调用）和输出（系统如何返回结果），确保数据格式的统一和可预测性。

### 3.1. `microsandbox_server`

#### **`execute_python`**
-   **用途**: 在隔离的沙箱环境中执行 Python 代码。
-   **输入格式 (模型生成)**:
    -   模型应将需要执行的 Python 代码直接作为 `execute_python` 标签的内容。
    ```xml
    <microsandbox_server><execute_python>
    import os
    print(os.listdir('.'))
    </execute_python></microsandbox_server>
    ```
-   **输出格式 (系统注入)**:
    -   **成功**: 返回代码的 `stdout`。
    ```xml
    <result index="0">['main.py', 'docs/']</result>
    ```
    -   **失败**: 返回 `stderr` 或关键的错误信息。
    ```xml
    <result index="0">FileNotFoundError: [Errno 2] No such file or directory: 'non_existent_file.py'</result>
    ```
    -   **超时**: 返回明确的超时错误。
    ```xml
    <result index="0">Execution timed out after N seconds.</result>
    ```

#### **`install_package`**
-   **用途**: 在沙箱中安装 Python 包。
-   **输入格式 (模型生成)**:
    ```xml
    <microsandbox_server><install_package>pandas</install_package></microsandbox_server>
    ```
-   **输出格式 (系统注入)**:
    -   **成功**: 返回简洁的成功确认信息，**忽略**详细的 pip 安装日志。
    ```xml
    <result index="0">Package 'pandas' installed successfully.</result>
    ```
    -   **失败**: 返回关键的错误信息。
    ```xml
    <result index="0">ERROR: Could not find a version that satisfies the requirement non_existent_package</result>
    ```

### 3.2. `browser_use_server`

#### **`navigate`**
-   **用途**: 导航到指定的 URL。
-   **输入格式 (模型生成)**:
    ```xml
    <browser_use_server><navigate>https://www.google.com</navigate></browser_use_server>
    ```
-   **输出格式 (系统注入)**:
    -   **核心思想**: 返回操作后的**页面状态**，为模型提供决策上下文。
    -   **成功**: 返回一个包含页面核心信息的、经过处理的字符串。
    ```xml
    <result index="0">Navigated to https://www.google.com. Page title: Google. Key elements: [Search Box, Search Button, I'm Feeling Lucky Button]</result>
    ```
    -   **失败**:
    ```xml
    <result index="0">Failed to navigate to https://invalid-url.error: net::ERR_NAME_NOT_RESOLVED</result>
    ```

#### **`extract_content`**
-   **用途**: 根据目标描述，从当前页面提取核心内容。
-   **输入格式 (模型生成)**:
    ```xml
    <browser_use_server><extract_content>the main headlines from the news section</extract_content></browser_use_server>
    ```
-   **输出格式 (系统注入)**:
    -   **成功**: 返回提取到的、经过清洗和总结的内容。
    ```xml
    <result index="0">Extracted content: 1. World Leaders Meet for Climate Summit. 2. New Breakthrough in AI Research. 3. Stock Market Hits Record High.</result>
    ```
    -   **失败**:
    ```xml
    <result index="0">Failed to extract content: No matching elements found for 'the main headlines'.</result>
    ```

### 3.3. `deepsearch_server`

#### **`research`**
-   **用途**: 针对一个问题进行深入、自主的研究，并返回一份总结报告。
-   **输入格式 (模型生成)**:
    -   输入可以是简单的字符串，也可以是包含更复杂参数的 JSON 字符串。
    ```xml
    <deepsearch_server><research>What are the main applications of reinforcement learning in robotics?</research></deepsearch_server>
    ```
-   **输出格式 (系统注入)**:
    -   **核心思想**: 提供最终的、经过提炼的研究报告，**忽略**原始搜索过程和参考文献。
    -   **成功**: 返回 `final_report` 的 Markdown 内容。
    ```xml
    <result index="0">
    **Applications of Reinforcement Learning in Robotics:**

    Reinforcement Learning (RL) has several key applications in robotics:
    1.  **Manipulation**: Training robotic arms to grasp and move objects in complex, unstructured environments.
    2.  **Locomotion**: Enabling legged robots to walk, run, and adapt to uneven terrain.
    3.  **Navigation**: Teaching mobile robots to navigate autonomously from point A to point B, avoiding obstacles.
    </result>
    ```
    -   **失败**:
    ```xml
    <result index="0">Research failed: Could not retrieve sufficient information to generate a report.</result>
    ```

### 3.4. `search_tool_server`

#### **`search_file_content`**
-   **用途**: 在指定文件中使用正则表达式搜索内容。
-   **输入格式 (模型生成)**:
    -   参数使用 JSON 字符串格式，以清晰地分隔 `file_path` 和 `pattern`。
    ```xml
    <search_tool_server><search_file_content>{"file_path": "core/orchestrator.py", "pattern": "def\\s+execute_instruction"}</search_file_content></search_tool_server>
    ```
-   **输出格式 (系统注入)**:
    -   **成功 (有匹配)**: 返回格式化的匹配结果。
    ```xml
    <result index="0">Matches in 'core/orchestrator.py': [Line 25: def execute_instruction(self, instruction_block):]</result>
    ```
    -   **成功 (无匹配)**:
    ```xml
    <result index="0">No matches found in 'core/orchestrator.py' for pattern 'def\\s+execute_instruction'.</result>
    ```
    -   **失败 (文件未找到)**:
    ```xml
    <result index="0">Error: File not found at path 'core/orchestrator.py'.</result>
    ```

---

## 4. 自适应主控制循环与实施计划

系统的核心是其自适应性，它由一个由 `<execute_tools />` 驱动的主控制循环实现。

1.  **监听**: 系统持续监听模型生成的输出流。
2.  **触发**: 当系统完整接收到 `<execute_tools />` 标签时，执行逻辑被触发。
3.  **定位与提取**: 系统会立即查找并提取**紧邻**在 `<execute_tools />` **之前**的那个指令块（单工具、`<parallel>` 或 `<sequential>`）。
4.  **调度与执行**:
    -   **目标文件**: `core/dispatcher_enhanced.py` (主控循环), `core/orchestrator.py` (指令解析与执行)。
    -   **`dispatcher_enhanced.py`**: 实现上述第 2、3 步的逻辑，提取出干净的指令块，并调用 Orchestrator。
    -   **`core/orchestrator.py`**: 增强其解析能力，使其能处理三种不同形态的指令块（单工具、并行、串行），并根据第 3 节定义的规范，调用相应的工具并格式化返回结果。
5.  **结果注入**: 系统将格式化好的 `<result>` 标签注入回模型上下文，开始新的交互回合。

---

## 5. 最终轨迹数据格式示例

### 轨迹示例 (单步动态观察)

```xml
<think>I need to check the contents of the main file. I'll list the directory first.</think>
<microsandbox_server><execute_python>import os; print(os.listdir('.'))</execute_python></microsandbox_server>
<execute_tools />
<result index="0">['main.py', 'core/', 'docs/']</result>
<think>Okay, the file is `main.py`. Now I can read its content.</think>
<microsandbox_server><execute_python>with open('main.py', 'r') as f: print(f.read())</execute_python></microsandbox_server>
<execute_tools />
<result index="0"># Main application logic...</result>
<answer>The content of main.py has been retrieved.</answer>
```

### 轨迹示例 (多步一次性规划)

```xml
<think>I will find the user's age and then calculate their age in 10 years. This is a predictable sequence.</think>
<sequential>
    <deepsearch_server><research>How old is the current US president</research></deepsearch_server>
    <microsandbox_server><execute_python>age_string = "{results[0]}"; import re; age = int(re.search(r'\d+', age_string).group()); print(f"In 10 years, he will be {age + 10}")</execute_python></microsandbox_server>
</sequential>
<execute_tools />
<result index="0">As of July 2025, Joe Biden is 82 years old.</result>
<result index="1">In 10 years, he will be 92.</result>
<answer>The current US president is 82. In 10 years, he will be 92.</answer>
```