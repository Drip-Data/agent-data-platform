# 工具参数统一化方案

## 问题背景

### 当前问题描述

在Agent Data Platform中，不同的MCP工具有不同的参数要求，导致以下问题：

1. **参数不统一**：
   - `browser_search_google`: 只需要 `query` 参数
   - `browser_use_execute_task`: 需要 `task`, `max_steps`, `use_vision` 参数
   - `microsandbox_execute`: 需要 `code`, `session_id`, `timeout` 参数

2. **映射复杂性**：
   - 现有的参数映射试图将所有 `query` 都映射到不同工具的主参数
   - 但这种一对一映射无法处理多参数工具

3. **模型理解困难**：
   - 模型需要知道每个工具的具体参数要求
   - 当前只能盲目传入一个参数，导致调用失败

### 典型错误示例

```
"工具调用验证失败: 缺少必需参数: ['task']; 无效参数: ['query']，有效参数: ['use_vision', 'task', 'max_steps']"
```

这个错误说明：
- 模型传入了 `query` 参数
- 但工具期望的是 `task` 参数
- 工具还支持 `use_vision` 和 `max_steps` 参数，但模型不知道

## 解决方案

### 核心理念

采用统一的JSON格式进行工具参数传递，让模型能够：
1. 明确知道每个工具支持哪些参数
2. 灵活传入多个参数
3. 使用标准化的调用格式

### 统一调用格式

#### 前端格式
```xml
<tool_name>
<action_name>
{
  "参数1": "值1",
  "参数2": "值2",
  "参数3": "值3"
}
</action_name>
</tool_name>
```

#### 具体示例
```xml
<browser_use>
<browser_use_execute_task>
{
  "task": "搜索李文倩目前工作地点",
  "max_steps": 10,
  "use_vision": true
}
</browser_use_execute_task>
</browser_use>
```

### 方案优势

1. **统一性**：所有工具都使用相同的调用格式
2. **灵活性**：可以传入任意数量的参数
3. **可扩展性**：新增参数不需要修改调用逻辑
4. **清晰性**：模型可以明确知道每个工具支持哪些参数
5. **可维护性**：参数定义集中管理，易于维护

### 技术实现

#### 1. 参数解析器
```python
def parse_tool_parameters(tool_name, action, raw_params):
    """解析工具参数"""
    # 解析JSON参数
    if isinstance(raw_params, str):
        params = json.loads(raw_params)
    else:
        params = raw_params
    
    # 根据工具定义验证和映射参数
    tool_def = get_tool_definition(tool_name, action)
    validated_params = validate_and_map_params(params, tool_def)
    
    return validated_params
```

#### 2. 参数验证
```python
def validate_and_map_params(params, tool_def):
    """验证并映射参数"""
    validated = {}
    
    # 检查必需参数
    for param_name, param_def in tool_def.get('parameters', {}).items():
        if param_def.get('required', False) and param_name not in params:
            raise ValueError(f"缺少必需参数: {param_name}")
    
    # 映射参数
    for param_name, value in params.items():
        if param_name in tool_def.get('parameters', {}):
            validated[param_name] = value
        else:
            # 检查是否有别名映射
            mapped_name = get_parameter_alias(param_name, tool_def)
            if mapped_name:
                validated[mapped_name] = value
            else:
                raise ValueError(f"无效参数: {param_name}")
    
    return validated
```

#### 3. 工具定义增强
```yaml
browser_use_execute_task:
  description: "AI驱动的智能浏览器任务执行"
  parameters:
    task:
      type: string
      required: true
      description: "要执行的任务描述"
    max_steps:
      type: integer
      required: false
      default: 50
      description: "最大执行步骤数"
    use_vision:
      type: boolean
      required: false
      default: true
      description: "是否使用视觉理解"
```

## 实施步骤

1. **收集所有工具的参数结构**：详细记录每个MCP服务器的所有工具参数
2. **修改LLM提示**：让模型知道要传入完整的参数JSON
3. **增强参数解析器**：支持JSON格式的参数解析
4. **更新工具定义**：在配置中明确每个工具的参数结构
5. **添加参数验证**：确保传入的参数符合工具要求
6. **测试验证**：确保所有工具都能正常工作

## 预期效果

1. **减少工具调用错误**：明确的参数定义减少参数不匹配问题
2. **提高模型理解**：模型能够准确使用各种工具的高级功能
3. **简化维护**：集中的参数定义便于管理和更新
4. **增强扩展性**：新增工具和参数更加简单

## 所有MCP服务器工具参数结构

### 1. MicroSandbox Server (microsandbox)
**服务端口**: 8090  
**服务ID**: microsandbox  

#### 工具列表:

**1.1 microsandbox_execute**
- **描述**: 执行Python代码
- **必需参数**: 
  - `code` (string): 要执行的Python代码
- **可选参数**:
  - `session_id` (string): 会话标识符
  - `timeout` (integer): 超时时间（秒）
- **示例**:
  ```json
  {
    "code": "print('Hello World'); result = 2 + 3; print(result)",
    "timeout": 30
  }
  ```

**1.2 microsandbox_install_package**
- **描述**: 安装Python包
- **必需参数**: 
  - `package_name` (string): 包名称
- **可选参数**:
  - `version` (string): 包版本
  - `session_id` (string): 会话标识符
- **示例**:
  ```json
  {
    "package_name": "numpy",
    "version": "1.21.0"
  }
  ```

**1.3 microsandbox_list_sessions**
- **描述**: 列出活跃会话
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**1.4 microsandbox_close_session**
- **描述**: 关闭会话
- **必需参数**: 
  - `session_id` (string): 要关闭的会话标识符
- **可选参数**: 无
- **示例**:
  ```json
  {
    "session_id": "my-session"
  }
  ```

**1.5 microsandbox_cleanup_expired**
- **描述**: 清理过期会话
- **必需参数**: 无
- **可选参数**:
  - `max_age` (integer): 最大年龄秒数
- **示例**:
  ```json
  {
    "max_age": 3600
  }
  ```

**1.6 microsandbox_get_performance_stats**
- **描述**: 获取性能统计
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**1.7 microsandbox_get_health_status**
- **描述**: 获取健康状态
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

### 2. Browser Use Server (browser_use)
**服务端口**: 8082  
**服务ID**: browser_use  

#### 工具列表:

**2.1 browser_use_execute_task**
- **描述**: 使用AI执行复杂的浏览器任务，支持自然语言描述
- **必需参数**: 
  - `task` (string): 要执行的任务描述，使用自然语言
- **可选参数**:
  - `max_steps` (integer): 最大执行步骤数，默认50
  - `use_vision` (boolean): 是否使用视觉理解，默认true
- **示例**:
  ```json
  {
    "task": "搜索Python教程并打开第一个结果"
  }
  ```

**2.2 browser_navigate**
- **描述**: 导航到指定网址
- **必需参数**: 
  - `url` (string): 要访问的URL地址
- **可选参数**: 无
- **示例**:
  ```json
  {
    "url": "https://www.google.com"
  }
  ```

**2.3 browser_search_google**
- **描述**: 在Google中搜索指定查询
- **必需参数**: 
  - `query` (string): 搜索查询词
- **可选参数**: 无
- **示例**:
  ```json
  {
    "query": "Python machine learning tutorial"
  }
  ```

**2.4 browser_go_back**
- **描述**: 返回上一页
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**2.5 browser_click_element**
- **描述**: 通过索引点击页面元素
- **必需参数**: 
  - `index` (integer): 要点击的元素索引
- **可选参数**: 无
- **示例**:
  ```json
  {
    "index": 1
  }
  ```

**2.6 browser_input_text**
- **描述**: 在指定元素中输入文本
- **必需参数**: 
  - `index` (integer): 要输入文本的元素索引
  - `text` (string): 要输入的文本
- **可选参数**: 无
- **示例**:
  ```json
  {
    "index": 2,
    "text": "hello world"
  }
  ```

**2.7 browser_send_keys**
- **描述**: 发送特殊键或快捷键
- **必需参数**: 
  - `keys` (string): 要发送的键，如Enter、Escape、Control+c等
- **可选参数**: 无
- **示例**:
  ```json
  {
    "keys": "Enter"
  }
  ```

**2.8 browser_scroll_down**
- **描述**: 向下滚动页面
- **必需参数**: 无
- **可选参数**:
  - `amount` (integer): 滚动像素数，不指定则滚动一页
- **示例**:
  ```json
  {
    "amount": 500
  }
  ```

**2.9 browser_scroll_up**
- **描述**: 向上滚动页面
- **必需参数**: 无
- **可选参数**:
  - `amount` (integer): 滚动像素数，不指定则滚动一页
- **示例**:
  ```json
  {
    "amount": 300
  }
  ```

**2.10 browser_scroll_to_text**
- **描述**: 滚动到包含指定文本的元素
- **必需参数**: 
  - `text` (string): 要滚动到的文本内容
- **可选参数**: 无
- **示例**:
  ```json
  {
    "text": "Sign up"
  }
  ```

**2.11 browser_switch_tab**
- **描述**: 切换到指定标签
- **必需参数**: 
  - `page_id` (integer): 要切换到的标签ID
- **可选参数**: 无
- **示例**:
  ```json
  {
    "page_id": 0
  }
  ```

**2.12 browser_open_tab**
- **描述**: 在新标签中打开URL
- **必需参数**: 
  - `url` (string): 要在新标签中打开的URL
- **可选参数**: 无
- **示例**:
  ```json
  {
    "url": "https://www.example.com"
  }
  ```

**2.13 browser_close_tab**
- **描述**: 关闭指定标签
- **必需参数**: 
  - `page_id` (integer): 要关闭的标签ID
- **可选参数**: 无
- **示例**:
  ```json
  {
    "page_id": 1
  }
  ```

**2.14 browser_extract_content**
- **描述**: 从页面提取特定内容
- **必需参数**: 
  - `goal` (string): 提取目标描述
- **可选参数**:
  - `include_links` (boolean): 是否包含链接，默认false
- **示例**:
  ```json
  {
    "goal": "提取所有公司名称"
  }
  ```

**2.15 browser_get_ax_tree**
- **描述**: 获取页面的可访问性树结构
- **必需参数**: 
  - `number_of_elements` (integer): 返回的元素数量
- **可选参数**: 无
- **示例**:
  ```json
  {
    "number_of_elements": 50
  }
  ```

**2.16 browser_get_dropdown_options**
- **描述**: 获取下拉菜单的所有选项
- **必需参数**: 
  - `index` (integer): 下拉菜单元素的索引
- **可选参数**: 无
- **示例**:
  ```json
  {
    "index": 3
  }
  ```

**2.17 browser_select_dropdown_option**
- **描述**: 选择下拉菜单中的选项
- **必需参数**: 
  - `index` (integer): 下拉菜单元素的索引
  - `text` (string): 要选择的选项文本
- **可选参数**: 无
- **示例**:
  ```json
  {
    "index": 3,
    "text": "Option 1"
  }
  ```

**2.18 browser_drag_drop**
- **描述**: 执行拖拽操作
- **必需参数**: 无
- **可选参数**:
  - `element_source` (string): 源元素选择器
  - `element_target` (string): 目标元素选择器
  - `coord_source_x` (integer): 源坐标X
  - `coord_source_y` (integer): 源坐标Y
  - `coord_target_x` (integer): 目标坐标X
  - `coord_target_y` (integer): 目标坐标Y
  - `steps` (integer): 拖拽步骤数，默认10
- **示例**:
  ```json
  {
    "element_source": ".item1",
    "element_target": ".dropzone"
  }
  ```

**2.19 browser_save_pdf**
- **描述**: 将当前页面保存为PDF
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**2.20 browser_screenshot**
- **描述**: 截取当前页面截图
- **必需参数**: 无
- **可选参数**:
  - `filename` (string): 截图文件名，可选
- **示例**:
  ```json
  {
    "filename": "current_page.png"
  }
  ```

**2.21 browser_wait**
- **描述**: 等待指定秒数
- **必需参数**: 无
- **可选参数**:
  - `seconds` (number): 等待的秒数，默认3
- **示例**:
  ```json
  {
    "seconds": 5
  }
  ```

**2.22 browser_done**
- **描述**: 标记任务完成
- **必需参数**: 
  - `text` (string): 完成描述
  - `success` (boolean): 是否成功完成
- **可选参数**: 无
- **示例**:
  ```json
  {
    "text": "任务已完成",
    "success": true
  }
  ```

**2.23 browser_get_page_info**
- **描述**: 获取当前页面信息
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**2.24 browser_get_current_url**
- **描述**: 获取当前页面URL
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**2.25 browser_close_session**
- **描述**: 关闭浏览器会话
- **必需参数**: 无
- **可选参数**: 无
- **示例**: `{}`

**2.26 browser_get_content**
- **描述**: 获取页面内容
- **必需参数**: 无
- **可选参数**:
  - `selector` (string): CSS选择器，空则获取全部内容
- **示例**:
  ```json
  {
    "selector": "body"
  }
  ```

### 3. DeepSearch Server (deepsearch)
**服务端口**: 8086  
**服务ID**: deepsearch  

#### 工具列表:

**3.1 research**
- **描述**: 专业级深度研究
- **必需参数**: 
  - `question` (string): 研究问题或查询
- **可选参数**:
  - `initial_queries` (array): 初始查询列表
  - `max_loops` (integer): 最大循环次数
  - `reasoning_model` (string): 推理模型
- **示例**:
  ```json
  {
    "question": "Python asyncio最佳实践",
    "max_loops": 3
  }
  ```

**3.2 quick_research**
- **描述**: 快速研究
- **必需参数**: 
  - `question` (string): 研究问题
- **可选参数**: 无
- **示例**:
  ```json
  {
    "question": "机器学习基础概念"
  }
  ```

**3.3 comprehensive_research**
- **描述**: 全面深入研究
- **必需参数**: 
  - `question` (string): 研究问题
- **可选参数**:
  - `topic_focus` (string): 主题焦点
- **示例**:
  ```json
  {
    "question": "区块链技术发展趋势",
    "topic_focus": "2024年最新进展"
  }
  ```

### 4. Search Tool Server (mcp-search-tool)
**服务端口**: 8080  
**服务ID**: mcp-search-tool  

#### 工具列表:

**4.1 search_file_content**
- **描述**: 搜索文件内容
- **必需参数**: 
  - `file_path` (string): 文件路径
  - `regex_pattern` (string): 正则表达式模式
- **可选参数**: 无
- **示例**:
  ```json
  {
    "file_path": "src/main.py",
    "regex_pattern": "def.*"
  }
  ```

**4.2 list_code_definitions**
- **描述**: 列出代码定义
- **必需参数**: 无
- **可选参数**:
  - `file_path` (string): 文件路径
  - `directory_path` (string): 目录路径
- **示例**:
  ```json
  {
    "directory_path": "src/"
  }
  ```

**4.3 analyze_tool_needs**
- **描述**: 分析任务的工具需求
- **必需参数**: 
  - `task_description` (string): 任务描述
- **可选参数**: 无
- **示例**:
  ```json
  {
    "task_description": "创建数据可视化图表"
  }
  ```

**4.4 search_and_install_tools**
- **描述**: 搜索并安装新工具
- **必需参数**: 
  - `task_description` (string): 任务描述
- **可选参数**:
  - `reason` (string): 安装原因
- **示例**:
  ```json
  {
    "task_description": "需要处理PDF文件",
    "reason": "当前工具不支持PDF操作"
  }
  ```

## 工具统计总结

### 服务器统计:
- **MicroSandbox Server**: 7个工具
- **Browser Use Server**: 26个工具
- **DeepSearch Server**: 3个工具
- **Search Tool Server**: 4个工具

### 总计: 40个工具

### 参数类型统计:
- **string**: 主要参数类型，用于文本、URL、路径等
- **integer**: 用于数值、索引、计数等
- **boolean**: 用于开关选项
- **array**: 用于列表数据
- **number**: 用于浮点数

---

*文档创建日期：2025-07-11*  
*最后更新：2025-07-11*  
*版本：1.0.0*