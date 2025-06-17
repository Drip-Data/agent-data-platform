# Agent Data Platform

🚀 **智能代理数据平台** - 基于MCP协议的企业级AI任务执行与学习框架

---

## 📖 项目概述

**Agent Data Platform** 是一个先进的智能代理系统，专为**自动化AI任务执行**、**轨迹学习**和**大规模数据处理**而设计。该平台采用**模块化微服务架构**，结合**大语言模型推理能力**和**可扩展工具生态**，为复杂任务的智能化处理和持续学习提供完整解决方案。

### 🎯 核心价值

- **🤖 智能决策**: 基于Gemini LLM的自主任务分析和代码生成
- **🔧 工具生态**: 基于MCP协议的可扩展工具服务器架构  
- **📚 轨迹学习**: 从执行轨迹中学习并生成新的训练任务
- **⚡ 高性能**: Redis驱动的异步任务队列和并发处理
- **🔒 安全执行**: 沙箱化代码执行环境，确保系统安全
- **📊 全链路追踪**: 完整的任务执行轨迹记录和分析
- **🌐 标准化接口**: RESTful API和WebSocket支持

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
│  Python      │  Browser      │  Search       │  Custom MCP     │
│  Executor    │  Navigator    │  Tool         │  Servers        │
│  Server      │  Server       │  Server       │                 │
├─────────────────────────────────────────────────────────────────┤
│         Redis队列 & 配置管理 & 监控系统                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚡ 快速开始

### 📋 环境要求

- **Python**: 3.9+ (推荐 3.11+)
- **Redis**: 6.0+ (用于任务队列和缓存)
- **内存**: 最少 4GB (推荐 8GB+)
- **操作系统**: Linux/macOS/Windows (Linux 生产环境推荐)

### 🚀 一键启动

```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd agent-data-platform

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动Redis (如果尚未运行)
# macOS: brew services start redis
# Ubuntu: sudo systemctl start redis-server
# Windows: 手动启动 Redis 服务

# 4. 配置环境变量
export GEMINI_API_KEY=your_gemini_api_key_here
# 可选: export OPENAI_API_KEY=your_openai_key (作为备用)

# 5. 启动平台 (所有服务将自动启动)
python main.py
```

### 🧪 提交测试任务

```bash
# 等待服务启动完成 (通常 10-30 秒)
# 查看启动日志获取 Task API 端口 (通常是 8000)

# 示例任务 1: 数学计算
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "input": "计算1到100的平方和",
       "description": "数学计算任务"
     }'

# 示例任务 2: 代码生成
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{
       "input": "创建一个Python函数，实现快速排序算法",
       "description": "代码生成任务"
     }'

# 查看任务结果 (使用返回的 task_id)
curl "http://localhost:8000/api/v1/tasks/{task_id}"
```

### 📊 批量测试

```bash
# 运行预定义的测试任务集
python scripts/batch_test_tasks.py --tasks-file tasks.jsonl

# 验证系统健康状态
python test_system_validation.py
```

---

## 🏗️ 系统架构详解

### 🔧 核心组件

#### 1. **Task API Service** (任务接口服务)
- **端口**: 8000 (自动分配)
- **功能**: RESTful API，任务提交、状态查询、结果获取
- **特性**: 支持并发请求、实时状态更新、错误处理

#### 2. **Enhanced Reasoning Runtime** (增强推理运行时)
- **作用**: 统一任务执行引擎，处理所有类型任务
- **能力**: LLM推理、工具调用、多步工作流编排
- **特性**: 智能工具选择、错误恢复、轨迹记录

#### 3. **ToolScore System** (工具评分系统)
- **端口**: 8089 (WebSocket), 8088 (HTTP监控)
- **功能**: 统一工具管理、动态工具注册、能力匹配
- **特性**: 实时工具发现、负载均衡、健康检查

#### 4. **Synthesis System** (合成学习系统)
- **功能**: 轨迹分析、模式提取、种子任务生成
- **特性**: 自动学习、任务合成、质量评估
- **输出**: 新的训练任务和改进建议

### 🛠️ MCP 工具服务器

#### Python Executor Server (端口: 8081)
```python
# 支持的工具
- python_execute: 安全的Python代码执行
- python_analyze: 代码静态分析
- python_visualize: 数据可视化
- python_install_package: 动态包安装
```

#### Browser Navigator Server (端口: 8082)
```python
# 支持的工具  
- navigate_to_url: 页面导航
- get_page_content: 内容提取
- click_element: 元素交互
- fill_form: 表单填写
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
│ Reasoning       │    │ System       │    │ (Python/Web/... )│
│ Runtime         │    │              │    │                 │
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

### 📁 配置文件说明

#### `config/llm_config.yaml` - LLM配置
```yaml
default_provider: "gemini"
providers:
  gemini:
    model: "gemini-2.5-flash-preview-05-20"
    api_key_env: "GEMINI_API_KEY"
  openai:
    model: "gpt-4"
    api_key_env: "OPENAI_API_KEY"
```

#### `config/ports_config.yaml` - 端口配置
```yaml
services:
  task_api: 8000
  redis: 6379
  
mcp_servers:
  toolscore_mcp: 8089
  toolscore_http: 8088
  python_executor: 8081
  browser_navigator: 8082
  search_tool: 8080
```

#### `config/routing_config.yaml` - 路由配置
```yaml
task_routing:
  mode: "unified"
  default_queue: "tasks:reasoning"
  runtime: "enhanced-reasoning-runtime"
```

### 🔧 环境变量

```bash
# 必需的环境变量
export GEMINI_API_KEY=your_gemini_api_key

# 可选的环境变量
export OPENAI_API_KEY=your_openai_api_key        # 备用LLM
export REDIS_URL=redis://localhost:6379          # Redis连接
export LOG_LEVEL=INFO                            # 日志级别
export WORKER_THREADS=4                          # 工作线程数
```

### 🐳 Docker 部署

```bash
# 构建镜像
docker build -t agent-data-platform .

# 运行容器
docker run -d \
  --name agent-platform \
  -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -v $(pwd)/output:/app/output \
  agent-data-platform
```

---

## 🧪 测试指南

### 📋 测试类型

#### 1. **单元测试**
```bash
# 运行所有单元测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_synthesis_focus.py -v

# 运行带覆盖率的测试
python -m pytest tests/ --cov=core --cov=services
```

#### 2. **集成测试**
```bash
# 测试核心组件集成
python -m pytest tests/test_synthesis_focus.py -m integration

# 测试安全功能
python -m pytest tests/test_security_critical.py -m security
```

#### 3. **系统验证测试**
```bash
# 全面系统健康检查
python test_system_validation.py

# 检查所有服务状态
python -c "
from services.service_manager import ServiceManager
sm = ServiceManager()
print('✅ 所有核心服务可用')
"
```

#### 4. **性能测试**
```bash
# 批量任务测试
python scripts/batch_test_tasks.py --tasks-file tasks.jsonl --concurrent 5

# 压力测试
python scripts/stress_test.py --requests 100 --duration 60
```

### 🔍 测试结果说明

运行 `python test_system_validation.py` 应该显示:
```
🎉 SYSTEM VALIDATION: SUCCESS
Your agent data platform is ready for operation!
Total: 7/7 components validated
```

### 📊 测试覆盖的功能

- ✅ **Synthesis System**: 轨迹学习和任务合成
- ✅ **Task Execution**: 任务执行和工具调用  
- ✅ **MCP Servers**: Python执行器、浏览器导航、搜索工具
- ✅ **Service Management**: 服务生命周期管理
- ✅ **Configuration**: 配置加载和验证
- ✅ **Security**: 沙箱执行和权限控制

---

## 📚 使用示例

### 🔥 基础任务示例

#### 数学计算任务
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/tasks",
    json={
        "input": "使用Python计算斐波那契数列的前20项",
        "description": "数学计算任务"
    }
)
task_id = response.json()["task_id"]
print(f"任务ID: {task_id}")
```

#### 数据分析任务
```python
response = requests.post(
    "http://localhost:8000/api/v1/tasks", 
    json={
        "input": "生成一个随机数据集，并创建散点图可视化",
        "description": "数据可视化任务"
    }
)
```

#### Web自动化任务
```python
response = requests.post(
    "http://localhost:8000/api/v1/tasks",
    json={
        "input": "访问https://example.com并提取页面标题",
        "description": "网页信息提取"
    }
)
```

### 🚀 高级功能示例

#### 批量任务处理
```python
# 创建任务文件 batch_tasks.jsonl
tasks = [
    {"input": "计算质数", "description": "数学任务1"},
    {"input": "数据可视化", "description": "图表任务1"},
    {"input": "网页爬取", "description": "Web任务1"}
]

# 批量提交
python scripts/batch_test_tasks.py --tasks-file batch_tasks.jsonl
```

#### 轨迹分析和学习
```python
# 查看生成的轨迹文件
cat output/trajectories/trajectories_collection.json

# 触发合成学习
curl -X POST "http://localhost:8000/api/v1/synthesis/trigger"

# 查看生成的种子任务
cat output/seed_tasks.jsonl
```

---

## 🔧 开发指南

### 📂 项目结构

```
agent-data-platform/
├── main.py                     # 主入口，启动所有服务
├── config/                     # 配置文件目录
│   ├── llm_config.yaml         # LLM提供商配置
│   ├── ports_config.yaml       # 端口分配配置
│   └── routing_config.yaml     # 任务路由配置
├── core/                       # 核心模块
│   ├── config_manager.py       # 配置管理器
│   ├── task_manager.py         # 任务管理器
│   ├── llm_client.py          # LLM客户端
│   ├── interfaces.py          # 数据结构定义
│   ├── synthesiscore/         # 合成学习系统
│   │   ├── synthesis.py       # 轨迹学习核心
│   │   └── synthesis_api.py   # 合成API
│   └── toolscore/             # 工具管理系统
│       ├── unified_tool_library.py  # 统一工具库
│       ├── mcp_server.py            # MCP服务器基类
│       └── mcp_connector.py         # MCP连接器
├── services/                   # 服务层
│   ├── service_manager.py      # 服务管理器
│   ├── task_api_service.py     # 任务API服务
│   └── toolscore_service.py    # ToolScore服务
├── mcp_servers/               # MCP工具服务器
│   ├── python_executor_server/ # Python执行服务器
│   ├── browser_navigator_server/ # 浏览器导航服务器
│   └── search_tool_server/     # 搜索工具服务器
├── runtimes/                  # 运行时系统
│   └── reasoning/
│       └── enhanced_runtime.py # 增强推理运行时
├── tests/                     # 测试套件
│   ├── test_synthesis_focus.py # 合成系统测试
│   └── test_system_validation.py # 系统验证测试
├── output/                    # 输出目录
│   ├── trajectories/          # 轨迹文件
│   └── seed_tasks.jsonl       # 生成的种子任务
└── requirements.txt           # Python依赖
```

### 🛠️ 开发工作流

#### 1. **添加新的MCP工具服务器**
```python
# 1. 创建新服务器目录
mkdir mcp_servers/my_new_server

# 2. 实现工具类
class MyNewTool:
    def __init__(self):
        self.name = "my_new_tool"
    
    async def execute(self, params):
        # 实现工具逻辑
        return {"result": "success"}

# 3. 注册到配置
# 在 config/mcp_servers.json 中添加服务器配置
```

#### 2. **扩展任务类型**
```python
# 1. 在 core/interfaces.py 添加新任务类型
class TaskType(Enum):
    CODE = "code"
    WEB = "web" 
    REASONING = "reasoning"
    MY_NEW_TYPE = "my_new_type"  # 新增

# 2. 在运行时处理新类型
# 修改 runtimes/reasoning/enhanced_runtime.py
```

#### 3. **自定义LLM提供商**
```python
# 1. 创建新提供商类
class MyLLMProvider(LLMProvider):
    def __init__(self, config):
        self.config = config
    
    async def generate(self, prompt, **kwargs):
        # 实现LLM调用逻辑
        return response

# 2. 注册到 core/llm_providers/
```

### 🔧 调试技巧

#### 启用详细日志
```bash
export LOG_LEVEL=DEBUG
python main.py
```

#### 查看服务状态
```python
from services.service_manager import ServiceManager
sm = ServiceManager()
# 检查各服务状态
```

#### 监控任务队列
```bash
# 连接Redis查看队列
redis-cli
LLEN tasks:reasoning  # 查看队列长度
LRANGE tasks:reasoning 0 -1  # 查看队列内容
```

---

## 🚨 故障排除

### 常见问题与解决方案

#### 🔧 服务启动失败
```bash
# 问题: Redis连接失败
# 解决: 确保Redis服务运行
brew services start redis  # macOS
sudo systemctl start redis-server  # Ubuntu

# 问题: 端口占用
# 解决: 修改config/ports_config.yaml中的端口配置
```

#### 🔧 任务执行失败
```bash
# 问题: LLM API调用失败
# 解决: 检查API密钥和网络连接
export GEMINI_API_KEY=your_valid_key

# 问题: MCP服务器无响应
# 解决: 检查MCP服务器状态
curl http://localhost:8088/health  # ToolScore健康检查
```

#### 🔧 测试失败
```bash
# 问题: 导入错误
# 解决: 确保PYTHONPATH设置正确
export PYTHONPATH=/path/to/agent-data-platform:$PYTHONPATH

# 问题: 权限错误
# 解决: 检查文件权限
chmod +x scripts/*.py
```

### 📊 监控和诊断

#### 查看服务健康状态
```bash
# 检查所有服务端点
curl http://localhost:8000/health      # Task API
curl http://localhost:8088/health      # ToolScore
curl http://localhost:8081/health      # Python Executor (如果实现)
```

#### 查看任务执行轨迹
```bash
# 查看最新轨迹文件
ls -la output/trajectories/
cat output/trajectories/trajectories_collection.json | jq .
```

#### 系统性能监控
```bash
# Redis性能监控
redis-cli info stats

# 系统资源监控  
top -p $(pgrep -f main.py)
```

---

## 🤝 贡献指南

### 🚀 参与开发

1. **Fork 项目** 并创建特性分支
2. **编写测试** 确保新功能正确工作
3. **更新文档** 包括README和代码注释
4. **提交PR** 并等待代码审查

### 📝 代码规范

- **Python**: 遵循PEP 8规范
- **注释**: 中英文混合，关键部分必须有注释
- **测试**: 新功能必须包含单元测试
- **文档**: 更新相关的README和API文档

### 🐛 问题报告

请在GitHub Issues中报告问题，包含：
- 详细的错误信息和堆栈跟踪
- 复现步骤
- 系统环境信息
- 日志文件 (如果适用)

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 📞 联系与支持

- **项目主页**: [GitHub Repository](https://github.com/your-username/agent-data-platform)
- **问题报告**: [GitHub Issues](https://github.com/your-username/agent-data-platform/issues)
- **功能请求**: [GitHub Discussions](https://github.com/your-username/agent-data-platform/discussions)

---

## 🎉 致谢

感谢所有为此项目做出贡献的开发者和研究人员。特别感谢：

- **MCP协议团队** - 提供标准化的工具通信协议
- **Google Gemini团队** - 提供强大的LLM推理能力  
- **Redis团队** - 提供高性能的消息队列解决方案
- **开源社区** - 提供丰富的工具和库支持

---

*Agent Data Platform - 让AI代理更智能，让任务执行更高效* 🚀