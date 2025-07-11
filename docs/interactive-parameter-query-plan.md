# 交互式参数查询方案 (Interactive Parameter Query Plan)

**版本**: 1.0
**日期**: 2025-07-11
**状态**: 已批准

## 1. 背景与动机

在完成了参数的JSON统一化，并将硬编码逻辑迁移到 `JSONParameterParser` 之后，我们遇到了一个新的设计挑战：如何将工具的参数信息有效地提供给LLM。

直接在初始Prompt中暴露所有工具、所有动作的完整参数定义，存在以下缺点：
- **Prompt过长**：导致token成本增加，并可能超出模型的上下文窗口限制。
- **模型混淆**：过量的信息可能会干扰LLM的核心任务选择，使其在选择工具和填充参数之间难以权衡。

## 2. 核心问题：为SFT模型生成高质量的训练数据

本次讨论的核心洞察是：我们当前系统的主要目标之一是**生成理想的、高质量的交互式轨迹，用于未来SFT（Supervised Fine-Tuning）模型的训练**。

因此，我们设计的交互模式不应只考虑当前系统的即时性能，而应着眼于我们希望最终的SFT模型所具备的行为模式。我们希望SFT模型能够：
1.  在不确定工具用法时，主动向系统查询。
2.  在获取用法后，再精确地填充参数。
3.  使用一个非常简洁的System Prompt来完成任务。

## 3. 提议的解决方案：`<tool_param>` 交互式查询

为了实现上述目标，我们决定不采用在Prompt中一次性提供所有信息的方式，而是引入一种新的、两步走的交互模式，通过一个新的XML标签 `<tool_param>` 来实现。

### 3.1. 交互流程

**第一步：LLM声明意图并查询参数**

当LLM决定要使用某个工具但需要其参数信息时，它会生成一个 `<tool_param>` 请求，其中包含清晰的 `tool_id` 和 `action` 标签。

```xml
<think>
我需要执行一段Python代码来计算1+1。我不确定 `microsandbox_execute` 需要哪些参数，让我先查询一下。
</think>
<tool_param>
  <tool_id>microsandbox</tool_id>
  <action>microsandbox_execute</action>
</tool_param>
```
**注意**：这个标签不会触发 `<execute_tools />`，因为它不是一个真正的工具执行。

**第二步：后端返回参数模板**

`EnhancedReasoningRuntime` 捕获到 `<tool_param>` 标签后，会：
1.  解析出 `tool_id` 和 `action` 的值。
2.  从 `UnifiedToolManager` 获取该动作的参数定义。
3.  将参数定义格式化为JSON，并放入 `<result>` 标签中返回。

```xml
<result>
{
  "status": "success",
  "tool_id": "microsandbox",
  "action": "microsandbox_execute",
  "parameters": {
    "code": {
      "type": "string",
      "required": true,
      "description": "要执行的Python代码"
    },
    "session_id": {
      "type": "string",
      "required": false,
      "description": "会话标识符"
    },
    "timeout": {
      "type": "integer",
      "required": false,
      "description": "超时时间（秒）"
    }
  }
}
</result>
```

**第三步：LLM填充参数并执行**

LLM在收到参数模板后，进行第二次思考，并根据模板填充参数，然后发起真正的工具调用。

```xml
<think>
好的，现在我知道了 `microsandbox_execute` 需要一个名为 `code` 的必需参数。我将把我的代码放入这个参数中。
</think>
<microsandbox>
  <microsandbox_execute>
    {
      "code": "print(1 + 1)"
    }
  </microsandbox_execute>
</microsandbox>
<execute_tools />
```

## 4. 实施计划

为了实现这一流程，需要对以下模块进行修改：

1.  **`runtimes/reasoning/enhanced_runtime.py`**:
    -   修改主执行循环，增加对 `<param_query>` 标签的识别和处理逻辑。
    -   当捕获到该标签时，调用 `UnifiedToolManager` 获取参数信息并返回，而不是进入工具执行流程。

2.  **`core/llm/prompt_builders/reasoning_prompt_builder.py`**:
    -   更新System Prompt，明确告知并演示如何使用新的 `<param_query>` 两步流程。
    -   初始的工具列表可以简化，不再包含完整的参数定义。

## 5. 方案优势

-   **生成理想的SFT数据**：生成的轨迹将完美地展示“查询-填充-执行”的行为模式，这是训练出更智能、更具交互性的SFT模型的关键。
-   **简化最终模型的Prompt**：经过SFT训练的模型将内化这种查询行为，其System Prompt可以变得非常简洁，只需告知其拥有 `param_query` 这个能力即可。
-   **降低当前模型的认知负荷**：将复杂的任务分解为“选择工具”和“填充参数”两个独立的步骤，有助于提高当前“教师模型”生成结果的准确性。
