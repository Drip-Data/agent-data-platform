# Search Tool MCP Server - 内置Prompt指南

## 🔍 服务概述
文件内容搜索和代码定义搜索服务，提供精确的文件系统搜索能力和智能工具管理功能。

## 🔧 工具分类与使用指南

### 📁 核心搜索功能

#### 🔎 文件内容搜索 - search_file_content
- **用途**: 在指定文件中搜索匹配正则表达式的内容
- **参数**: 
  - `file_path` (required) - 要搜索的文件路径
  - `regex_pattern` (required) - 正则表达式搜索模式
- **示例**:
```xml
<mcp-search-tool><search_file_content>{"file_path": "src/main.py", "regex_pattern": "def.*"}</search_file_content></mcp-search-tool>
```
- **适用场景**: 
  - 查找函数定义
  - 搜索特定代码模式
  - 查找配置项和常量
  - 定位错误信息

#### 📚 代码定义列表 - list_code_definitions
- **用途**: 列出文件或目录中的所有代码定义（函数、类等）
- **参数**:
  - `file_path` (optional) - 指定文件路径
  - `directory_path` (optional) - 指定目录路径
- **示例**:
```xml
<mcp-search-tool><list_code_definitions>src/</list_code_definitions></mcp-search-tool>
```
- **适用场景**:
  - 代码结构分析
  - API接口梳理
  - 模块功能概览
  - 重构前的代码盘点

### 🛠️ 智能工具管理

#### 🎯 工具需求分析 - analyze_tool_needs
- **用途**: 分析特定任务需要什么工具和能力
- **参数**: `task_description` (required) - 任务描述
- **示例**:
```xml
<mcp-search-tool><analyze_tool_needs>create data visualization charts</analyze_tool_needs></mcp-search-tool>
```
- **适用场景**:
  - 新项目技术栈选择
  - 工具能力评估
  - 技术方案制定
  - 依赖项分析

#### 📦 工具搜索安装 - search_and_install_tools
- **用途**: 搜索并安装满足特定需求的新工具
- **参数**:
  - `task_description` (required) - 任务描述
  - `reason` (optional) - 安装原因说明
- **示例**:
```xml
<mcp-search-tool><search_and_install_tools>{"task_description": "need to process PDF files", "reason": "current tools don't support PDF operations"}</search_and_install_tools></mcp-search-tool>
```
- **适用场景**:
  - 扩展系统能力
  - 解决技术瓶颈
  - 自动化工具配置
  - 动态功能增强

## 💡 搜索模式与技巧

### 🎯 正则表达式常用模式

#### 函数定义搜索
```xml
<!-- Python函数 -->
<mcp-search-tool><search_file_content>{"file_path": "app.py", "regex_pattern": "def\\s+\\w+\\("}</search_file_content></mcp-search-tool>

<!-- JavaScript函数 -->
<mcp-search-tool><search_file_content>{"file_path": "script.js", "regex_pattern": "function\\s+\\w+\\(|\\w+\\s*:\\s*function"}</search_file_content></mcp-search-tool>

<!-- 类定义 -->
<mcp-search-tool><search_file_content>{"file_path": "models.py", "regex_pattern": "class\\s+\\w+"}</search_file_content></mcp-search-tool>
```

#### 配置和常量搜索
```xml
<!-- 环境变量 -->
<mcp-search-tool><search_file_content>{"file_path": ".env", "regex_pattern": "\\w+_?\\w*="}</search_file_content></mcp-search-tool>

<!-- 配置项 -->
<mcp-search-tool><search_file_content>{"file_path": "config.json", "regex_pattern": "\"\\w+\":"}</search_file_content></mcp-search-tool>

<!-- API端点 -->
<mcp-search-tool><search_file_content>{"file_path": "routes.py", "regex_pattern": "@app\\.route\\(|@router\\."}</search_file_content></mcp-search-tool>
```

#### 错误和日志搜索
```xml
<!-- 错误处理 -->
<mcp-search-tool><search_file_content>{"file_path": "app.py", "regex_pattern": "except\\s+\\w+|raise\\s+\\w+"}</search_file_content></mcp-search-tool>

<!-- 日志记录 -->
<mcp-search-tool><search_file_content>{"file_path": "service.py", "regex_pattern": "logger\\.|logging\\."}</search_file_content></mcp-search-tool>
```

### 📁 目录结构分析
```xml
<!-- 分析整个源码目录 -->
<mcp-search-tool><list_code_definitions>src/</list_code_definitions></mcp-search-tool>

<!-- 分析特定模块 -->
<mcp-search-tool><list_code_definitions>{"directory_path": "src/api"}</list_code_definitions></mcp-search-tool>

<!-- 分析单个文件 -->
<mcp-search-tool><list_code_definitions>{"file_path": "src/main.py"}</list_code_definitions></mcp-search-tool>
```

## 🚀 高级使用场景

### 🔍 代码审计工作流
1. **结构概览**: 使用`list_code_definitions`了解代码结构
2. **安全检查**: 搜索潜在的安全问题模式
3. **性能分析**: 查找性能瓶颈相关代码
4. **依赖分析**: 梳理模块间的依赖关系

```xml
<!-- 1. 获取项目结构 -->
<mcp-search-tool><list_code_definitions>src/</list_code_definitions></mcp-search-tool>

<!-- 2. 查找安全相关代码 -->
<mcp-search-tool><search_file_content>{"file_path": "src/auth.py", "regex_pattern": "password|token|secret"}</search_file_content></mcp-search-tool>

<!-- 3. 分析数据库查询 -->
<mcp-search-tool><search_file_content>{"file_path": "src/models.py", "regex_pattern": "SELECT|INSERT|UPDATE|DELETE"}</search_file_content></mcp-search-tool>
```

### 🛠️ 技术栈扩展工作流
1. **需求分析**: 分析当前任务的工具需求
2. **能力评估**: 评估现有工具是否满足需求
3. **工具搜索**: 搜索合适的新工具
4. **集成验证**: 验证新工具的集成效果

```xml
<!-- 1. 分析需求 -->
<mcp-search-tool><analyze_tool_needs>implement real-time chat functionality</analyze_tool_needs></mcp-search-tool>

<!-- 2. 搜索工具 -->
<mcp-search-tool><search_and_install_tools>{"task_description": "WebSocket support for real-time communication", "reason": "need real-time bidirectional communication"}</search_and_install_tools></mcp-search-tool>
```

## ⚠️ 最佳实践

### 🎯 搜索效率优化
1. **精确模式**: 使用具体的正则表达式避免过多无关结果
2. **分层搜索**: 先用`list_code_definitions`了解结构，再精确搜索
3. **路径优化**: 指定具体的文件路径而非搜索整个项目

### 📝 模式设计原则
1. **转义字符**: 注意正则表达式中的特殊字符转义
2. **边界匹配**: 使用词边界`\\b`避免部分匹配
3. **大小写**: 考虑大小写敏感性问题

### 🔄 错误处理策略
- **路径检查**: 确保文件路径正确存在
- **权限验证**: 确认对目标文件有读取权限
- **模式测试**: 在简单示例上测试正则表达式的正确性
- **结果验证**: 检查搜索结果的准确性和完整性

## 📊 结果分析指南

### 🔍 搜索结果解读
- **匹配上下文**: 关注匹配内容的上下文信息
- **位置信息**: 注意匹配项在文件中的位置
- **相关性排序**: 根据相关性对结果进行排序

### 📈 后续行动建议
- **深度分析**: 基于搜索结果进行更深入的代码分析
- **文档更新**: 将发现的重要信息更新到项目文档
- **重构建议**: 基于代码结构分析提出重构建议