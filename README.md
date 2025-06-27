# Agent Data Platform

🚀 **智能代理数据平台** - 基于MCP协议的企业级AI任务执行与学习框架，现已集成**MicroSandbox安全执行环境**、**持久化记忆管理**和**多步推理能力**

---
## 📖 快速启动命令
#启动服务
cd agent-data-platform
python3 main.py

#注入任务
cd agent-data-platform
python3 scripts/batch_test_tasks.py --tasks-file data/test_tasks.jsonl

## 📖 项目概述

**Agent Data Platform** 是一个先进的智能代理系统，专为**自动化AI任务执行**、**轨迹学习**和**大规模数据处理**而设计。该平台采用**模块化微服务架构**，结合**大语言模型推理能力**和**可扩展工具生态**，为复杂任务的智能化处理和持续学习提供完整解决方案。

### 🎯 核心价值

- **🤖 智能决策**: 基于Gemini LLM的自主任务分析和代码生成
- **🧠 持久化记忆**: 跨任务和跨会话的智能记忆管理，支持上下文学习
- **🔄 多步推理**: 动态步骤规划，支持复杂长流程任务执行（不再限制2步）
- **🔧 工具生态**: 基于MCP协议的可扩展工具服务器架构  
- **📚 轨迹学习**: 从执行轨迹中学习并生成新的训练任务
- **⚡ 高性能**: Redis驱动的异步任务队列和并发处理
- **🔒 安全执行**: **MicroSandbox**沙箱化代码执行环境，确保系统安全
- **📊 全链路追踪**: 完整的任务执行轨迹记录和分析
- **🌐 标准化接口**: RESTful API和WebSocket支持
- **🔄 自进化数据飞轮**: 实时轨迹监控 → 智能任务合成 → 质量验证 → 任务池扩充

### 🏗️ 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Data Platform                          │
├─────────────────────────────────────────────────────────────────┤
│  Task API │ Synthesis │ Enhanced Reasoning Runtime              │
│  Service  │  System   │ (统一执行引擎)                           │
├─────────────────────────────────────────────────────────────────┤
│              ToolScore System (统一工具管理)                    │
├─────────────────────────────────────────────────────────────────┤
│  MicroSandbox │  Browser      │  Search       │  Custom MCP     │
│  Server       │  Navigator    │  Tool         │  Servers        │
│  (安全执行)   │  Server       │  Server       │                 │
├─────────────────────────────────────────────────────────────────┤
│         Redis队列 & 配置管理 & 监控系统                        │
└─────────────────────────────────────────────────────────────────┘
```

### 🔄 自进化数据飞轮原理

**Agent Data Platform** 的核心创新在于实现了一个**自我学习与进化的数据飞轮**，通过四个关键阶段形成闭环，实现AI代理能力的持续提升：

#### 📋 完整系统运行流程

##### **第一阶段：系统启动与初始化**
```bash
python main.py  # 🚀 一键启动所有服务
```

**启动时自动完成：**
- ✅ **服务集群启动**: Redis、ToolScore、MCP服务器、任务API、合成服务
- ✅ **轨迹监控启动**: `TrajectoryMonitor` 开始实时监控 `output/trajectories/` 目录
- ✅ **文件变化检测**: 特别监控 `trajectories_collection.json` 的实时变化

##### **第二阶段：任务输入与智能执行**

**多种任务输入方式：**
```bash
# 方式1: 文件批量输入
data/tasks.jsonl  # 包含任务列表

# 方式2: API实时输入  
curl -X POST http://localhost:8000/api/v1/tasks \
     -H "Content-Type: application/json" \
     -d '{"task_type": "research", "input": "深度调研AI Agent发展趋势"}'
```

**智能执行流程：**
1. **📥 任务加载**: `TaskLoader` 读取和验证任务
2. **🎯 智能分发**: `TaskDistributor` 根据任务类型智能路由
3. **🧠 推理执行**: `EnhancedReasoningRuntime` 调用LLM进行多步推理
4. **🔧 工具协调**: 通过 `ToolScore` 动态调用最适合的MCP工具
5. **📊 轨迹记录**: 每个执行步骤实时记录到轨迹文件

##### **第三阶段：实时学习触发 (数据飞轮核心)**

**🔥 零延迟自动触发机制：**
```python
# core/synthesiscore/trajectory_monitor.py 
class TrajectoryFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('trajectories_collection.json'):
            # 轨迹文件变化立即被捕获！
            asyncio.create_task(
                self.trajectory_monitor.process_trajectory_changes(event.src_path)
            )
```

**智能合成处理流程：**
1. **⚡ 轨迹变化检测** → 文件修改后2-5分钟内自动触发
2. **🔍 成功轨迹解析** → 提取高质量的执行路径
3. **🌱 原子任务提取** → 从轨迹中智能生成种子任务
4. **📈 任务智能扩展** → 深度扩展(复杂度) + 宽度扩展(多样性)
5. **✅ 多维度质量验证** → 7个维度精准评估新生成任务
6. **💾 高质量任务存储** → 验证通过的任务自动保存到任务池

##### **第四阶段：数据飞轮闭环加速**

**📁 核心数据流转：**
- **输入任务**: `data/tasks.jsonl` (原始任务集)
- **执行轨迹**: `output/trajectories/trajectories_collection.json` (实时更新)
- **学习产出**: `output/seed_tasks.jsonl` (自动生成的高质量新任务)
- **知识提炼**: `output/task_essences.json` (任务模式和策略)

## ⚡ 快速开始

### 📋 环境要求

- **Python**: 3.9+ (推荐 3.11+)
- **Redis**: 6.0+ (用于任务队列和缓存)
- **内存**: 最少 4GB (推荐 8GB+)
- **操作系统**: Linux/macOS/Windows (Linux 生产环境推荐)
- **Docker**: 可选，用于MicroSandbox容器化执行

### 🚀 一键启动

#### 第一步：克隆仓库和基础安装
```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd agent-data-platform

# 2. 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 3. 安装基础依赖
pip install -r requirements.txt
```

#### 第二步：安装MicroSandbox (必需)
```bash
# 安装MicroSandbox - 安全代码执行环境
pip install microsandbox

# 验证安装
python -c "from microsandbox import PythonSandbox; print('✅ MicroSandbox安装成功')"
```

#### 第三步：启动Redis服务
```bash
# macOS (使用Homebrew)
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Windows
# 下载并安装Redis for Windows，或使用WSL

# 验证Redis运行
redis-cli ping  # 应该返回 PONG
```

#### 第四步：配置环境变量
```bash
# 创建环境变量文件
cat > .env << EOF
# 必需的API密钥
GEMINI_API_KEY=your_gemini_api_key_here

# 可选配置
OPENAI_API_KEY=your_openai_api_key  # 备用LLM
REDIS_URL=redis://localhost:6379    # Redis连接
LOG_LEVEL=INFO                      # 日志级别
EOF

# 加载环境变量
source .env  # Linux/macOS
# 或手动设置: export GEMINI_API_KEY=your_key
```

#### 第五步：启动平台
```bash
# 启动所有服务 (会自动清理端口并启动)
python main.py

# 查看启动日志，确保所有服务正常
# 应该看到类似输出：
# ✅ 端口清理完成
# === Agent Data Platform 启动中 ===
# ✅ ToolScore服务已就绪
# ✅ MicroSandbox MCP服务器启动成功
# ✅ 所有服务已启动
```

### 🧪 验证安装和提交测试任务

#### 检查系统健康状态
```bash
# 等待服务完全启动 (通常 15-30 秒)
sleep 20

# 检查核心服务
curl http://localhost:8000/health
# 期望输出: {"status":"healthy","redis":"connected"}

# 检查ToolScore服务
curl http://localhost:8088/health
# 期望输出: 健康状态信息
```

#### 提交测试任务

**示例1：基础计算任务**
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "请使用microsandbox执行: print(\"Hello, MicroSandbox!\")",
       "priority": "high"
     }'

# 期望输出: {"task_id": "xxx-xxx-xxx", "status": "queued", ...}
```

**示例2：多步推理研究任务**
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research",
       "input": "深度调研AI Agent开发领域的最新趋势，特别关注多模态Agent、LangGraph框架的发展现状",
       "priority": "high",
       "max_steps": 15,
       "context": {
         "session_id": "user_research_session",
         "timeout": 600
       }
     }'
```

**示例3：代码生成和执行任务**
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code", 
       "input": "创建一个Python函数实现快速排序算法，并在microsandbox中测试，要求包含性能基准测试",
       "priority": "medium",
       "max_steps": 8
     }'
```

**示例4：记忆管理演示**
```bash
# 第一个任务 - 建立会话记忆
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "reasoning",
       "input": "我是一个数据科学家，正在研究机器学习算法优化",
       "context": {"session_id": "data_scientist_session"},
       "priority": "medium"
     }'

# 第二个任务 - 利用会话记忆
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "基于我刚才提到的研究方向，帮我生成一个梯度下降优化器的代码",
       "context": {"session_id": "data_scientist_session"},
       "priority": "medium"
     }'
```

#### 查看任务结果
```bash
# 使用上述返回的task_id查看结果
TASK_ID="your-task-id-here"
curl "http://localhost:8000/api/v1/tasks/${TASK_ID}"

# 查看任务状态变化
watch -n 2 "curl -s http://localhost:8000/api/v1/tasks/${TASK_ID} | jq '.status'"
```

### 🔄 验证数据飞轮学习效果

**数据飞轮是系统的核心能力，以下步骤可以直观验证学习效果：**

#### 第一步：观察初始状态
```bash
# 检查种子任务文件（可能为空或很少）
wc -l output/seed_tasks.jsonl 2>/dev/null || echo "种子任务文件不存在"

# 检查轨迹文件初始状态
ls -la output/trajectories/
```

#### 第二步：提交学习任务并观察飞轮启动
```bash
# 提交一个研究类任务，让系统学习
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research",
       "input": "深度调研人工智能在教育领域的应用现状和发展趋势，重点关注个性化学习和智能评估",
       "priority": "high",
       "max_steps": 12,
       "context": {"session_id": "education_ai_research"}
     }'

echo "✅ 学习任务已提交，请等待5-10分钟观察数据飞轮效果..."
```

#### 第三步：实时监控飞轮运转
```bash
# 在新终端中监控轨迹文件变化（实时显示飞轮运转）
tail -f output/trajectories/trajectories_collection.json

# 在另一个终端监控种子任务生成（观察学习成果）
watch -n 10 "echo '=== 种子任务数量变化 ===' && wc -l output/seed_tasks.jsonl 2>/dev/null"

# 监控系统日志（查看合成过程）
tail -f logs/main_test.log | grep -E "(合成|Synthesis|轨迹|种子任务)"
```

#### 第四步：验证飞轮学习成果
```bash
# 等待任务执行完成（通常5-10分钟）
sleep 300

# 检查轨迹是否已生成
echo "=== 轨迹文件状态 ==="
ls -la output/trajectories/trajectories_collection.json
echo -e "\n=== 轨迹文件内容概览 ==="
tail -5 output/trajectories/trajectories_collection.json | jq '.' 2>/dev/null || echo "JSON格式待完善"

# 检查种子任务是否自动生成
echo -e "\n=== 自动生成的种子任务 ==="
if [ -f output/seed_tasks.jsonl ]; then
    echo "种子任务数量: $(wc -l < output/seed_tasks.jsonl)"
    echo "最新生成的任务示例:"
    tail -3 output/seed_tasks.jsonl | jq -r '.description' 2>/dev/null || tail -3 output/seed_tasks.jsonl
else
    echo "⏳ 种子任务正在生成中，请稍等..."
fi

# 检查任务本质提取
echo -e "\n=== 学习到的任务本质 ==="
if [ -f output/task_essences.json ]; then
    echo "任务本质文件大小: $(wc -c < output/task_essences.json) bytes"
    echo "本质示例:"
    head -5 output/task_essences.json | jq '.' 2>/dev/null || head -5 output/task_essences.json
else
    echo "⏳ 任务本质正在提取中..."
fi
```

#### 第五步：验证飞轮加速效果
```bash
# 提交与刚才类似的任务，验证系统是否从轨迹中学习
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "research", 
       "input": "调研人工智能在医疗领域的应用，特别是智能诊断和精准医疗",
       "priority": "high",
       "max_steps": 10,
       "context": {"session_id": "medical_ai_research"}
     }'

echo "🎯 第二个任务已提交，系统现在应该具备更强的研究能力！"
echo "💡 理想情况下，系统会:"
echo "   - 更快完成类似任务（从学习中获得经验）"
echo "   - 生成更多高质量的种子任务变体"
echo "   - 展示更好的推理路径和工具选择"
```

#### 第六步：数据飞轮效果总结
```bash
#!/bin/bash
# 数据飞轮效果验证脚本
echo "🔄 === Agent Data Platform 数据飞轮效果报告 ==="
echo "生成时间: $(date)"
echo ""

echo "📊 === 数据增长统计 ==="
echo "轨迹文件: $(ls -lh output/trajectories/trajectories_collection.json 2>/dev/null | awk '{print $5}' || echo '未生成')"
echo "种子任务: $(wc -l output/seed_tasks.jsonl 2>/dev/null | awk '{print $1}' || echo '0') 个"
echo "任务本质: $(ls -lh output/task_essences.json 2>/dev/null | awk '{print $5}' || echo '未生成')"

echo -e "\n🎯 === 验证数据飞轮成功标志 ==="
echo "✅ 轨迹文件自动更新: $([ -f output/trajectories/trajectories_collection.json ] && echo '是' || echo '否')"
echo "✅ 种子任务自动生成: $([ -f output/seed_tasks.jsonl ] && [ $(wc -l < output/seed_tasks.jsonl 2>/dev/null || echo 0) -gt 0 ] && echo '是' || echo '否')"
echo "✅ 任务本质自动提取: $([ -f output/task_essences.json ] && echo '是' || echo '否')"

echo -e "\n🚀 === 飞轮性能提升验证 ==="
if [ -f output/seed_tasks.jsonl ] && [ $(wc -l < output/seed_tasks.jsonl) -gt 0 ]; then
    echo "🎉 数据飞轮运转成功！"
    echo "📈 任务库自动扩展: 从原始任务 → $(wc -l < output/seed_tasks.jsonl) 个新任务"
    echo "⚡ 学习速度: 实时（2-5分钟）"
    echo "🎯 下次类似任务将获得:"
    echo "   - 更快的执行速度"
    echo "   - 更好的推理质量"
    echo "   - 更丰富的任务变体"
else
    echo "⏳ 数据飞轮正在启动中，请等待更长时间或检查系统日志"
fi
```

---

## 🏗️ 系统架构详解

### 🔧 核心组件

#### 1. **Task API Service** (任务接口服务)
- **端口**: 8000
- **功能**: RESTful API，任务提交、状态查询、结果获取
- **特性**: 支持并发请求、实时状态更新、错误处理
- **API端点**:
  - `POST /api/v1/tasks` - 提交新任务
  - `GET /api/v1/tasks/{task_id}` - 查看任务状态
  - `GET /health` - 健康检查

#### 2. **Enhanced Reasoning Runtime** (增强推理运行时)
- **作用**: 统一任务执行引擎，处理所有类型任务
- **能力**: LLM推理、工具调用、多步工作流编排
- **特性**: 
  - 智能工具选择、错误恢复、轨迹记录
  - **动态步骤数**：支持最多100步的复杂任务执行
  - **记忆集成**：自动存储和调用会话历史
  - **上下文注入**：LLM决策时获得历史经验指导
- **集成**: 与MicroSandbox、MemoryManager、StepPlanner无缝集成

#### 3. **ToolScore System** (工具评分系统)
- **端口**: 8089 (WebSocket), 8088 (HTTP监控)
- **功能**: 统一工具管理、动态工具注册、能力匹配
- **特性**: 实时工具发现、负载均衡、健康检查

#### 4. **MicroSandbox Integration** (MicroSandbox集成) 🆕
- **端口**: 8090
- **功能**: 安全的Python代码执行环境
- **特性**: 
  - 容器化沙箱执行
  - 会话管理和状态保持
  - 包安装和依赖管理
  - 超时和资源限制
- **安全性**: 完全隔离的执行环境，防止恶意代码

#### 5. **MemoryManager** (记忆管理器) 🧠
- **功能**: 会话记忆存储、上下文管理、跨会话洞察
- **特性**: 
  - **Redis持久化**：生产级记忆存储，支持内存降级
  - **智能摘要**：为LLM提供精炼的历史上下文
  - **跨会话学习**：从历史交互中提取成功模式
- **存储**: 支持会话步骤、任务轨迹、用户偏好

#### 6. **StepPlanner** (步骤规划器) 🔄
- **功能**: 智能任务分解、动态规划调整、策略选择
- **策略**: 
  - **顺序执行**：简单任务的线性处理
  - **自适应规划**：根据执行结果动态调整
  - **迭代优化**：复杂任务的反复改进
- **集成**: 与MemoryManager结合，基于历史经验规划

#### 7. **Synthesis System** (合成学习系统)
- **功能**: 轨迹分析、模式提取、种子任务生成
- **特性**: 自动学习、任务合成、质量评估
- **输出**: 新的训练任务和改进建议

### 🛠️ MCP 工具服务器

#### MicroSandbox Server (端口: 8090) 🆕
```python
# 支持的工具
- microsandbox_execute: 安全的Python代码执行
- microsandbox_install_package: 在沙箱中安装Python包
- microsandbox_list_sessions: 列出活跃的执行会话
- microsandbox_close_session: 关闭指定会话
- microsandbox_cleanup_expired: 清理过期会话
```

**使用示例**:
```python
# 简单代码执行
{
  "action": "microsandbox_execute",
  "parameters": {
    "code": "print('Hello from secure sandbox!')"
  }
}

# 会话化执行 (保持状态)
{
  "action": "microsandbox_execute", 
  "parameters": {
    "code": "x = 42; print(f'Variable x = {x}')",
    "session_id": "my-session"
  }
}

# 安装包并使用
{
  "action": "microsandbox_install_package",
  "parameters": {
    "package_name": "numpy",
    "session_id": "data-analysis"
  }
}
```

#### Browser-Use Server (端口: 8082)
```python
# AI驱动的浏览器自动化服务器 (替换原Browser Navigator)
# 支持的主要工具:
- browser_use_execute_task: AI自然语言任务执行
- browser_navigate: 页面导航
- browser_click_element: 智能元素点击
- browser_input_text: 智能文本输入
- browser_extract_content: AI内容提取
- browser_screenshot: 页面截图
- browser_scroll_down/up: 页面滚动
- browser_search_google: Google搜索
- browser_save_pdf: PDF保存
# ... 总计25+个功能

# AI功能示例:
browser_use_execute_task("在Google上搜索Python教程并打开第一个结果")
```

#### Search Tool Server (端口: 8080)
```python
# 支持的工具
- analyze_tool_needs: 工具需求分析
- search_and_install_tools: 工具搜索和安装
```

### 📊 数据流架构

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ 任务提交     │ -> │ Task API     │ -> │ Redis 队列      │
│ (HTTP API)  │    │ Service      │    │ (tasks:reasoning)│
└─────────────┘    └──────────────┘    └─────────────────┘
                                                │
┌─────────────────────────────────────────────┘
│
▼
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Enhanced        │ -> │ ToolScore    │ -> │ MCP Servers     │
│ Reasoning       │    │ System       │    │ (MicroSandbox   │
│ Runtime         │    │              │    │  Browser/Search)│
└─────────────────┘    └──────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐    ┌──────────────┐    
│ 轨迹存储        │ -> │ Synthesis    │    
│ (JSON文件)      │    │ System       │    
└─────────────────┘    └──────────────┘    
```

---

## 🚀 部署与配置

### 📁 核心配置文件

#### `config/llm_config.yaml` - LLM配置
```yaml
default_provider: "gemini"
providers:
  gemini:
    model: "gemini-2.5-flash-preview-05-20"
    api_key_env: "GEMINI_API_KEY"
    max_tokens: 8192
    temperature: 0.7
  openai:
    model: "gpt-4o"
    api_key_env: "OPENAI_API_KEY"
    max_tokens: 4096
    temperature: 0.7
```

#### `config/ports_config.yaml` - 端口配置
```yaml
core_services:
  task_api:
    port: 8000
    description: "任务提交和查询API"
  redis:
    port: 6379
    description: "Redis任务队列和缓存"
    
mcp_servers:
  toolscore_mcp:
    port: 8089
    description: "ToolScore MCP协议服务器"
    auto_detect_port: false
  toolscore_http:
    port: 8088
    description: "ToolScore HTTP监控API"
  microsandbox_mcp:        # 🆕 MicroSandbox配置
    port: 8090
    description: "MicroSandbox MCP服务器 - 安全代码执行"
    auto_start: true
    type: "internal"
  browser_navigator:
    port: 8082
    description: "浏览器导航器MCP服务器"
    auto_start: true
  search_tool:
    port: 8080
    description: "搜索工具MCP服务器"
    auto_start: true
```

#### `config/routing_config.yaml` - 路由配置
```yaml
task_routing:
  mode: "unified"
  default_queue: "tasks:reasoning"
  runtime: "enhanced-reasoning-runtime"
  
# 任务类型路由
task_types:
  code: "tasks:reasoning"      # 代码任务统一处理
  web: "tasks:reasoning"       # Web任务统一处理  
  reasoning: "tasks:reasoning" # 推理任务统一处理
```

### 🔧 环境变量详解

```bash
# === 必需环境变量 ===
export GEMINI_API_KEY=your_gemini_api_key_here
# 获取方式: https://aistudio.google.com/app/apikey

# === 可选环境变量 ===
export OPENAI_API_KEY=your_openai_api_key        # 备用LLM
export REDIS_URL=redis://localhost:6379          # Redis连接
export LOG_LEVEL=INFO                            # 日志级别: DEBUG/INFO/WARNING/ERROR
export MICROSANDBOX_TIMEOUT=30                   # MicroSandbox执行超时(秒)
export MAX_CONCURRENT_TASKS=10                   # 最大并发任务数

# === 高级配置 ===
export PYTHONPATH=/path/to/agent-data-platform:$PYTHONPATH
export TOOL_DISCOVERY_INTERVAL=60                # 工具发现间隔(秒)
export TRAJECTORY_RETENTION_DAYS=30              # 轨迹保留天数
```

### 🐳 Docker 部署 (可选)

#### 创建Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    redis-server \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制代码和依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 安装MicroSandbox
RUN pip install microsandbox

COPY . .

# 暴露端口
EXPOSE 8000 8088 8089 8090 8082 8080

# 启动脚本
CMD ["python", "main.py"]
```

#### Docker Compose 部署
```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  agent-platform:
    build: .
    ports:
      - "8000:8000"
      - "8088:8088"  
      - "8089:8089"
      - "8090:8090"
      - "8082:8082"
      - "8080:8080"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
    volumes:
      - ./output:/app/output
      - ./logs:/app/logs

volumes:
  redis_data:
```

```bash
# 使用Docker Compose启动
export GEMINI_API_KEY=your_key
docker-compose up -d

# 查看日志
docker-compose logs -f agent-platform
```

---

## 🧪 测试指南

### 📋 系统验证测试

#### 快速健康检查
```bash
# 检查所有核心服务
curl http://localhost:8000/health      # Task API
curl http://localhost:8088/health      # ToolScore HTTP
curl http://localhost:6379/ping        # Redis (如果直接暴露)

# 检查MCP服务器连接 (通过ToolScore)
curl http://localhost:8088/api/v1/tools/available
```

#### 运行完整系统验证
```bash
# 如果存在验证脚本
python test_system_validation.py

# 期望输出:
# ✅ Redis连接正常
# ✅ ToolScore服务可用  
# ✅ MicroSandbox集成正常
# ✅ 任务API响应正常
# ✅ 所有MCP服务器在线
# 🎉 系统验证通过！
```

### 🔥 功能测试示例

#### 1. **MicroSandbox安全执行测试**
```bash
# 测试基础代码执行
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "请在microsandbox中执行以下代码并返回结果: import math; print(f\"π的值是: {math.pi}\")",
       "priority": "high"
     }'

# 测试包安装和使用
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code", 
       "input": "在microsandbox中安装numpy包，然后创建一个1-10的数组并计算平均值",
       "priority": "high"
     }'

# 测试会话保持
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "在microsandbox中定义变量x=100，然后在同一会话中计算x的平方根",
       "priority": "high"
     }'
```

#### 2. **复合任务测试**
```bash
# 数据分析任务
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "使用microsandbox创建一个包含100个随机数的列表，计算统计信息(均值、方差、标准差)，并生成直方图",
       "priority": "medium"
     }'

# Web数据获取 + 代码处理
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "web",
       "input": "访问https://httpbin.org/json获取示例数据，然后在microsandbox中解析JSON并提取关键信息",
       "priority": "medium"
     }'
```

#### 3. **错误处理和安全测试**
```bash
# 测试超时处理
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "在microsandbox中执行一个可能长时间运行的任务，测试超时处理",
       "priority": "low"
     }'

# 测试错误恢复
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code", 
       "input": "在microsandbox中故意执行有语法错误的代码，测试错误处理机制",
       "priority": "low"
     }'
```

### 📊 批量测试
```bash
# 创建批量测试文件
cat > batch_test_tasks.jsonl << EOF
{"task_type": "code", "input": "使用microsandbox计算1+1", "priority": "high"}
{"task_type": "reasoning", "input": "解释什么是递归算法", "priority": "medium"}
{"task_type": "code", "input": "在microsandbox中创建一个简单的计算器函数", "priority": "medium"}
{"task_type": "web", "input": "获取一个公开API的数据", "priority": "low"}
EOF

# 如果有批量测试脚本
python scripts/batch_test_tasks.py --tasks-file batch_test_tasks.jsonl --concurrent 3

# 手动批量提交
for i in {1..5}; do
  curl -X POST "http://localhost:8000/api/v1/tasks" \
       -H "Content-Type: application/json" \
       -d "{\"task_type\": \"code\", \"input\": \"测试任务 ${i}: 在microsandbox中计算 ${i} 的阶乘\", \"priority\": \"medium\"}"
  sleep 1
done
```

---

## 📚 API 参考

### 🔥 Task API 端点

#### POST /api/v1/tasks - 提交新任务
```json
// 请求体
{
  "task_type": "code|reasoning|web|research",  // 任务类型
  "input": "任务描述",                   // 任务内容
  "priority": "high|medium|low",        // 优先级(可选)
  "max_steps": 10,                      // 最大执行步骤数(可选，默认10)
  "context": {                          // 额外上下文(可选)
    "session_id": "my-session",         // 会话ID，用于记忆管理
    "timeout": 60,
    "tags": ["test", "demo"]
  }
}

// 响应
{
  "task_id": "uuid-string",
  "status": "queued|processing|completed|failed",
  "message": "Task submitted successfully",
  "timestamp": "2024-01-01T12:00:00Z",
  "result": null  // 任务完成后包含结果
}
```

#### GET /api/v1/tasks/{task_id} - 查看任务状态
```json
// 响应 - 进行中的任务
{
  "task_id": "uuid-string",
  "status": "processing", 
  "message": "Task is being processed",
  "timestamp": "2024-01-01T12:00:00Z",
  "result": null,
  "progress": {
    "current_step": 2,
    "total_steps": 5,
    "description": "Executing code in MicroSandbox"
  }
}

// 响应 - 完成的任务
{
  "task_id": "uuid-string",
  "status": "completed",
  "message": "Task completed successfully", 
  "timestamp": "2024-01-01T12:00:30Z",
  "result": {
    "success": true,
    "final_result": "任务完成。生成结果：AI Agent领域深度分析报告已完成...",
    "execution_time": 207.5,
    "steps_completed": 8,
    "max_steps_used": 15,
    "tools_used": ["mcp-deepsearch.comprehensive_research"],
    "memory_context": {
      "session_id": "user_research_session",
      "context_applied": true,
      "previous_tasks_referenced": 3
    },
    "reasoning_trace": {
      "planning_steps": 2,
      "execution_steps": 6,
      "adaptive_adjustments": 1
    }
  }
}
```

#### GET /health - 健康检查
```json
{
  "status": "healthy",
  "redis": "connected", 
  "services": {
    "task_api": "running",
    "toolscore": "healthy",
    "microsandbox": "available",
    "memory_manager": "ready",
    "step_planner": "initialized"
  },
  "memory_stats": {
    "cached_sessions": 12,
    "total_stored_steps": 156,
    "redis_available": true
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 🔧 ToolScore API 端点

#### GET /api/v1/tools/available - 获取可用工具
```json
{
  "tools": [
    {
      "tool_id": "microsandbox-mcp-server",
      "name": "MicroSandbox",
      "description": "安全的Python代码执行环境",
      "capabilities": [
        "microsandbox_execute",
        "microsandbox_install_package", 
        "microsandbox_list_sessions",
        "microsandbox_close_session"
      ],
      "status": "available"
    }
  ],
  "total_count": 3
}
```

---

## 🔧 开发指南

### 📂 项目结构详解

```
agent-data-platform/
├── main.py                     # 🚀 主入口，集成端口清理和服务启动
├── cleanup_ports.py            # 🧹 端口清理工具
├── requirements.txt            # 📦 Python依赖（不含microsandbox）
├── .env.example               # 🔧 环境变量模板
├── docker-compose.yml         # 🐳 Docker编排文件
│
├── config/                     # ⚙️ 配置文件目录
│   ├── llm_config.yaml         # 🤖 LLM提供商配置
│   ├── ports_config.yaml       # 🌐 端口分配配置
│   └── routing_config.yaml     # 🔀 任务路由配置
│
├── core/                       # 🏗️ 核心模块
│   ├── config_manager.py       # ⚙️ 配置管理器
│   ├── task_manager.py         # 📋 任务管理器  
│   ├── llm_client.py          # 🤖 LLM客户端
│   ├── interfaces.py          # 📋 数据结构定义
│   ├── redis_manager.py       # 📊 Redis连接管理
│   ├── memory_manager.py      # 🧠 记忆管理器 (新增)
│   ├── step_planner.py        # 🔄 多步推理规划器 (新增)
│   ├── optimized_agent_controller.py  # 🎯 增强代理控制器 (更新)
│   ├── tool_usage_tracker.py  # 📈 工具使用跟踪 (新增)
│   │
│   ├── synthesiscore/         # 🧠 合成学习系统
│   │   ├── synthesis.py       # 🔬 轨迹学习核心
│   │   └── synthesis_api.py   # 🌐 合成API
│   │
│   └── toolscore/             # 🔧 工具管理系统
│       ├── unified_tool_library.py    # 📚 统一工具库
│       ├── mcp_server.py              # 🔌 MCP服务器基类
│       ├── mcp_connector.py           # 🔗 MCP连接器
│       ├── external_mcp_manager.py    # 🌐 外部MCP管理 (新增)
│       └── mcp_search_tool.py         # 🔍 MCP搜索工具
│
├── services/                   # 🛠️ 服务层
│   ├── service_manager.py      # 👔 服务管理器
│   ├── task_api_service.py     # 🌐 任务API服务
│   ├── toolscore_service.py    # 🔧 ToolScore服务
│   ├── mcp_server_launcher.py  # 🚀 MCP服务器启动器
│   ├── runtime_service.py      # ⚡ 运行时服务管理
│   └── synthesis_service.py    # 🧠 合成服务管理
│
├── mcp_servers/               # 🔌 MCP工具服务器
│   ├── microsandbox_server/   # 🛡️ MicroSandbox服务器 (新增)
│   │   ├── main.py             # 主服务器实现
│   │   ├── enhanced_sandbox_executor.py  # 增强执行器
│   │   └── microsandbox_executor.py      # 基础执行器
│   ├── browser_navigator_server/  # 🌐 浏览器导航服务器
│   └── search_tool_server/        # 🔍 搜索工具服务器
│
├── runtimes/                  # ⚡ 运行时系统
│   └── reasoning/
│       ├── enhanced_runtime.py       # 🧠 增强推理运行时
│       ├── real_time_tool_client.py  # 🔄 实时工具客户端 (已修复)
│       └── toolscore_client.py       # 🔧 ToolScore客户端
│
├── tests/                     # 🧪 测试套件
│   ├── test_synthesis_focus.py       # 🔬 合成系统测试
│   ├── test_system_validation.py     # ✅ 系统验证测试
│   ├── test_memory_manager.py        # 🧠 记忆管理器测试 (新增)
│   ├── test_step_planner.py          # 🔄 步骤规划器测试 (新增)
│   ├── test_microsandbox_*.py        # 🛡️ MicroSandbox测试 (新增)
│   └── test_tool_tracking*.py        # 📈 工具跟踪测试 (新增)
│
├── output/                    # 📊 输出目录
│   ├── trajectories/          # 📈 轨迹文件
│   │   └── trajectories_collection.json
│   ├── seed_tasks.jsonl       # 🌱 生成的种子任务
│   └── batch_test_results.json # 📊 批量测试结果
│
├── data/                      # 💾 数据目录 (新增)
│   ├── learning_data.json     # 🎯 持久化学习数据
│   └── memory_cache/          # 🧠 记忆缓存目录
│
├── logs/                      # 📝 日志目录
│   └── main_test.log          # 主要日志文件
│
└── scripts/                   # 🔧 工具脚本
    ├── batch_test_tasks.py     # 📊 批量任务测试
    └── stress_test.py          # 💪 压力测试
```

### 🛠️ 开发工作流

#### 1. **添加新的MCP工具服务器**
```python
# 1. 创建新服务器目录
mkdir mcp_servers/my_new_server

# 2. 实现工具类 (继承MCPServer基类)
from core.toolscore.mcp_server import MCPServer

class MyNewMCPServer:
    def __init__(self, config_manager):
        self.server_name = "my_new_server" 
        self.server_id = "my-new-mcp-server"
        
    async def execute_tool_action(self, action: str, parameters: Dict[str, Any]):
        if action == "my_action":
            return {"result": "success", "data": parameters}
        return {"error": "Unknown action"}

# 3. 注册到配置文件
# 在 config/ports_config.yaml 中添加:
# my_new_server:
#   port: 8091
#   description: "我的新工具服务器"
#   auto_start: true
```

#### 2. **扩展MicroSandbox功能**
```python
# 在 mcp_servers/microsandbox_server/main.py 中添加新方法
async def microsandbox_custom_action(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """自定义MicroSandbox动作"""
    code = parameters.get("code", "")
    session_id = parameters.get("session_id")
    
    # 实现自定义逻辑
    result = await self._execute_with_session(code, session_id)
    return result

# 在工具注册中添加新功能
capabilities = [
    # ... 现有功能
    ToolCapability(
        name="microsandbox_custom_action",
        description="执行自定义MicroSandbox操作",
        parameters={
            "code": {"type": "string", "description": "要执行的代码"},
            "session_id": {"type": "string", "description": "会话ID", "required": False}
        }
    )
]
```

#### 3. **自定义任务类型**
```python
# 1. 在 core/interfaces.py 添加新任务类型
class TaskType(Enum):
    CODE = "code"
    WEB = "web" 
    REASONING = "reasoning"
    DATA_ANALYSIS = "data_analysis"  # 新增数据分析类型

# 2. 在运行时处理新类型
# 修改 runtimes/reasoning/enhanced_runtime.py
async def process_task(self, task_data: Dict[str, Any]):
    task_type = task_data.get("task_type", "reasoning")
    
    if task_type == "data_analysis":
        # 专门处理数据分析任务的逻辑
        return await self._process_data_analysis_task(task_data)
    # ... 其他类型处理
```

### 🔧 调试技巧

#### 启用详细日志
```bash
# 设置调试级别日志
export LOG_LEVEL=DEBUG
python main.py

# 或在运行时启用调试
python main.py --debug
```

#### 查看MCP服务器状态
```bash
# 检查所有MCP服务器健康状态
curl http://localhost:8088/api/v1/tools/available | jq '.'

# 检查特定MicroSandbox状态
curl http://localhost:8088/api/v1/tools/microsandbox-mcp-server | jq '.'

# 测试MicroSandbox直接连接
nc -z localhost 8090 && echo "MicroSandbox端口可达" || echo "MicroSandbox端口不可达"
```

#### 监控任务队列
```bash
# 连接Redis查看队列状态
redis-cli

# 查看任务队列长度
XLEN tasks:reasoning

# 查看队列中的任务
XRANGE tasks:reasoning - + COUNT 5

# 查看消费者组状态
XINFO GROUPS tasks:reasoning

# 查看未确认的任务
XPENDING tasks:reasoning workers
```

#### 实时监控轨迹生成
```bash
# 监控轨迹文件变化
tail -f output/trajectories/trajectories_collection.json

# 监控主要日志文件
tail -f logs/main_test.log | grep -E "(ERROR|MicroSandbox|任务|执行)"

# 监控系统资源
watch -n 2 "ps aux | grep -E '(main.py|microsandbox|redis)' | grep -v grep"
```

---

## 🚨 故障排除

### 常见问题与解决方案

#### 🔧 MicroSandbox相关问题

**问题**: MicroSandbox安装失败
```bash
# 解决方案1: 升级pip并重新安装
pip install --upgrade pip
pip install microsandbox

# 解决方案2: 使用特定版本
pip install microsandbox==0.1.7

# 解决方案3: 从源码安装
pip install git+https://github.com/codelion/microsandbox.git

# 验证安装
python -c "from microsandbox import PythonSandbox; print('✅ 安装成功')"
```

**问题**: MicroSandbox服务器启动失败
```bash
# 检查端口8090是否被占用
lsof -ti :8090

# 如果被占用，杀死占用进程
lsof -ti :8090 | xargs kill -9

# 或者修改配置文件使用不同端口
# 编辑 config/ports_config.yaml 中的 microsandbox_mcp.port
```

**问题**: 代码执行超时
```bash
# 增加超时配置
export MICROSANDBOX_TIMEOUT=60  # 60秒超时

# 或在任务中指定超时
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "task_type": "code",
       "input": "长时间运行的代码",
       "context": {"timeout": 120}
     }'
```

#### 🔧 服务启动失败

**问题**: Redis连接失败
```bash
# 检查Redis服务状态
redis-cli ping
# 期望输出: PONG

# 启动Redis服务
# macOS:
brew services start redis

# Ubuntu:
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 检查Redis配置
redis-cli CONFIG GET "*"
```

**问题**: API Key未配置
```bash
# 检查环境变量
echo $GEMINI_API_KEY
echo $OPENAI_API_KEY

# 设置API Key
export GEMINI_API_KEY=your_actual_key_here

# 验证API Key
curl -H "Authorization: Bearer $GEMINI_API_KEY" \
     https://generativelanguage.googleapis.com/v1/models
```

**问题**: 端口冲突
```bash
# 查看所有占用的端口
lsof -i :8000,8088,8089,8090,8082,8080

# 批量清理端口 (已集成到main.py)
python cleanup_ports.py

# 或手动清理特定端口
lsof -ti :8090 | xargs kill -9
```

#### 🔧 任务执行失败

**问题**: 任务一直处于queued状态
```bash
# 检查运行时服务状态
curl http://localhost:8000/health

# 检查Redis队列
redis-cli XLEN tasks:reasoning

# 检查消费者组
redis-cli XINFO GROUPS tasks:reasoning

# 重启运行时消费者 (通常重启整个系统)
# Ctrl+C 停止main.py，然后重新启动
python main.py
```

**问题**: MCP服务器无响应
```bash
# 检查ToolScore健康状态
curl http://localhost:8088/health

# 检查MCP服务器列表
curl http://localhost:8088/api/v1/tools/available

# 检查特定服务器连接
telnet localhost 8090  # MicroSandbox

# 重启特定MCP服务器 (需要重启整个系统)
```

**问题**: 轨迹文件未生成
```bash
# 检查输出目录权限
ls -la output/trajectories/

# 检查合成服务状态
curl http://localhost:8088/api/v1/synthesis/status 2>/dev/null || echo "合成服务API不可用"

# 手动触发轨迹处理
curl -X POST http://localhost:8088/api/v1/synthesis/trigger 2>/dev/null || echo "无法触发合成"
```

### 📊 系统监控和诊断

#### 全面健康检查脚本
```bash
#!/bin/bash
# health_check.sh - 系统健康检查脚本

echo "🔍 Agent Data Platform 健康检查"
echo "================================"

# 检查核心服务
echo "📊 核心服务状态:"
curl -s http://localhost:8000/health | jq '.' 2>/dev/null && echo "✅ Task API 正常" || echo "❌ Task API 异常"
curl -s http://localhost:8088/health >/dev/null 2>&1 && echo "✅ ToolScore 正常" || echo "❌ ToolScore 异常"
redis-cli ping >/dev/null 2>&1 && echo "✅ Redis 正常" || echo "❌ Redis 异常"

# 检查MCP服务器
echo -e "\n🔌 MCP服务器状态:"
nc -z localhost 8090 2>/dev/null && echo "✅ MicroSandbox (8090) 正常" || echo "❌ MicroSandbox (8090) 异常"
nc -z localhost 8082 2>/dev/null && echo "✅ Browser Navigator (8082) 正常" || echo "❌ Browser Navigator (8082) 异常"
nc -z localhost 8080 2>/dev/null && echo "✅ Search Tool (8080) 正常" || echo "❌ Search Tool (8080) 异常"

# 检查队列状态
echo -e "\n📋 任务队列状态:"
queue_len=$(redis-cli XLEN tasks:reasoning 2>/dev/null)
echo "队列长度: ${queue_len:-'无法获取'}"

# 检查可用工具
echo -e "\n🔧 可用工具:"
curl -s http://localhost:8088/api/v1/tools/available 2>/dev/null | jq -r '.tools[].tool_id' 2>/dev/null || echo "无法获取工具列表"

echo -e "\n🎉 健康检查完成!"
```

#### 性能监控
```bash
# 监控系统资源使用
top -p $(pgrep -f "main.py")

# 监控Redis性能
redis-cli --latency-history -i 1

# 监控网络连接
netstat -an | grep -E ":(8000|8088|8089|8090|8082|8080)"

# 监控日志错误
tail -f logs/main_test.log | grep -i error
```

---

## 🤝 贡献指南

### 🚀 参与开发

1. **Fork 项目** 并创建特性分支
2. **设置开发环境**:
   ```bash
   git clone your-fork-url
   cd agent-data-platform
   python -m venv dev-env
   source dev-env/bin/activate
   pip install -r requirements.txt
   pip install microsandbox
   pip install pytest pytest-cov  # 开发依赖
   ```
3. **编写测试** 确保新功能正确工作
4. **运行测试套件**:
   ```bash
   python -m pytest tests/ -v
   python test_system_validation.py
   ```
5. **更新文档** 包括README和代码注释
6. **提交PR** 并等待代码审查

### 📝 代码规范

- **Python**: 遵循PEP 8规范
- **注释**: 中英文混合，关键部分必须有注释
- **测试**: 新功能必须包含单元测试
- **文档**: 更新相关的README和API文档
- **MicroSandbox**: 所有代码执行必须通过MicroSandbox进行

### 🐛 问题报告

请在GitHub Issues中报告问题，包含：
- 详细的错误信息和堆栈跟踪
- 复现步骤
- 系统环境信息 (OS, Python版本, Redis版本)
- 日志文件 (logs/main_test.log)
- MicroSandbox版本信息

**问题报告模板**:
```markdown
## 问题描述
[简要描述问题]

## 环境信息
- OS: [操作系统]
- Python版本: [python --version]
- MicroSandbox版本: [pip show microsandbox]
- Redis版本: [redis-cli --version]

## 复现步骤
1. [步骤1]
2. [步骤2]
3. [错误出现]

## 期望行为
[描述期望的正确行为]

## 实际行为  
[描述实际发生的错误行为]

## 错误日志
```
[粘贴相关的错误日志]
```

## 额外信息
[任何其他相关信息]
```

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 📞 联系与支持

- **项目主页**: [GitHub Repository](https://github.com/your-username/agent-data-platform)
- **问题报告**: [GitHub Issues](https://github.com/your-username/agent-data-platform/issues)
- **功能请求**: [GitHub Discussions](https://github.com/your-username/agent-data-platform/discussions)
- **文档Wiki**: [项目Wiki](https://github.com/your-username/agent-data-platform/wiki)

---

## 🎉 致谢

感谢所有为此项目做出贡献的开发者和研究人员。特别感谢：

- **MCP协议团队** - 提供标准化的工具通信协议
- **Google Gemini团队** - 提供强大的LLM推理能力  
- **MicroSandbox团队** - 提供安全的代码执行环境
- **Redis团队** - 提供高性能的消息队列解决方案
- **开源社区** - 提供丰富的工具和库支持

---

## 🚀 快速命令参考

```bash
# === 安装和启动 ===
pip install -r requirements.txt && pip install microsandbox
export GEMINI_API_KEY=your_key
python main.py

# === 健康检查 ===
curl http://localhost:8000/health

# === 基础任务提交 ===
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"task_type":"code","input":"测试MicroSandbox: print(\"Hello!\")"}'

# === 多步推理任务 ===
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"task_type":"research","input":"深度分析AI发展趋势","max_steps":15,"context":{"session_id":"research_session"}}'

# === 会话记忆任务 ===
# 第一个任务建立上下文
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"task_type":"reasoning","input":"我正在研究机器学习","context":{"session_id":"my_session"}}'
# 第二个任务使用上下文
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"task_type":"code","input":"基于刚才的研究方向，生成算法代码","context":{"session_id":"my_session"}}'

# === 查看任务 ===
curl http://localhost:8000/api/v1/tasks/TASK_ID

# === 监控 ===
tail -f logs/main_test.log
redis-cli XLEN tasks:reasoning

# === 数据飞轮监控 ===
# 监控轨迹文件变化（观察飞轮运转）
tail -f output/trajectories/trajectories_collection.json

# 监控种子任务生成（观察学习成果）  
watch -n 10 "wc -l output/seed_tasks.jsonl 2>/dev/null || echo '0 种子任务'"

# 监控合成系统日志
tail -f logs/main_test.log | grep -E "(合成|Synthesis|轨迹|种子任务)"

# === 验证数据飞轮效果 ===
# 检查飞轮核心文件
ls -la output/trajectories/trajectories_collection.json output/seed_tasks.jsonl output/task_essences.json

# 统计学习成果
echo "种子任务数量: $(wc -l output/seed_tasks.jsonl 2>/dev/null | awk '{print $1}' || echo '0')"

# === 测试记忆和学习功能 ===
python -m pytest tests/test_memory_manager.py -v
python -m pytest tests/test_step_planner.py -v

# === 清理 ===
python cleanup_ports.py
redis-cli FLUSHDB
```

---

*Agent Data Platform - 让AI代理更智能，让任务执行更安全* 🚀🛡️
