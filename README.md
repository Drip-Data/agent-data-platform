# Agent Data Platform

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-brightgreen)

一个生产级的、可扩展的、支持动态工具扩展的 AI Agent 数据构建平台。

## 📖 概述

Agent Data Platform 是一个专为运行 AI Agent 并捕获其完整决策轨迹而设计的集成系统。平台的**核心创新**在于 AI Agent 能够**主动发现工具缺口、搜索并安装新的MCP服务器工具**，实现真正的自我进化能力。

系统支持多种强大的工具（代码执行、浏览器导航、动态工具安装），通过健壮的、基于消息队列的架构来处理复杂的、多步骤的任务，并自动生成高质量的 Agent 轨迹数据用于评估、微调和研究。

## ✨ 核心特性

### 🧠 智能决策系统
- **双版本Runtime**: 基础版本 + 增强版本（支持动态MCP工具管理）
- **LLM驱动决策**: 使用先进的LLM（Gemini）进行任务分解、工具选择和智能推理
- **上下文感知**: 维护执行上下文，从失败中学习，避免重复错误

### 🔧 动态工具管理
- **MCP工具注册机制**: 智能工具缺口检测和自动工具安装
- **多源搜索**: 支持GitHub、Docker Hub等多个工具源的并行搜索
- **安全评估**: 信任作者验证、安全性评分、Docker隔离运行

### 🏗️ 可扩展架构
- **模块化设计**: Core、Runtimes、ToolScore三大核心模块
- **MCP协议支持**: 标准化的工具接口和跨进程通信
- **Docker容器化**: 基于Docker Compose的服务编排

### 📊 完整的学习闭环
- **轨迹追踪**: 详细记录每步执行的思考链、工具调用和结果
- **任务合成**: 从轨迹中提取任务本质，生成新的训练数据
- **监控指标**: Prometheus + Grafana 监控体系

## 🚀 快速开始

### 1. 环境准备

确保您的机器上安装了 [Docker](https://www.docker.com/products/docker-desktop/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

### 2. 克隆与配置

```bash
# 克隆仓库
git clone https://github.com/Drip-Data/agent-data-platform.git
cd agent-data-platform

# 从模板创建环境变量文件
cp .env.example .env
```

编辑 `.env` 文件，填入您的API密钥：

```env
# LLM API配置
GEMINI_API_KEY=your_gemini_api_key
GEMINI_API_URL=your_gemini_api_url

# 功能开关
DISABLE_CACHE=false
SAVE_INDIVIDUAL_TRAJECTORIES=false
```

### 3. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 检查服务状态
docker-compose ps
```

## 🧪 测试您的Agent

### 基础推理任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{
  "task_type": "reasoning",
  "input": "使用Python计算第10个斐波那契数并返回结果",
  "priority": "high"
}'
```

### 浏览器导航任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{
  "task_type": "reasoning", 
  "input": "访问 https://datapresso.ai/，并告诉我网站的标题",
  "priority": "high"
}'
```

### 复杂多步骤任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{
  "task_type": "reasoning",
  "input": "搜索新加坡国立大学IORA研究所的教授信息，并生成研究领域分析图表",
  "priority": "high"
}'
```

### 查看执行结果

```bash
# 查看最新轨迹
docker exec -it agent-data-platform-reasoning-runtime-1 cat /app/output/trajectories/trajectories_collection.json | jq .[-1]

# 查看服务日志
docker-compose logs -f reasoning-runtime
```

## 🏗️ 系统架构

### 核心模块

1. **Core模块** - 任务分发和基础服务
   - `TaskDispatcher` - 任务分发器
   - `LLMClient` - LLM集成客户端
   - `Interfaces` - 核心接口定义

2. **Runtimes模块** - 智能执行引擎
   - `ReasoningRuntime` - 基础推理运行时
   - `EnhancedReasoningRuntime` - 增强版本（支持动态工具管理）
   - `SandboxRuntime` - 代码执行沙盒
   - `WebRuntime` - Web导航运行时

3. **ToolScore模块** - 工具管理平台
   - `UnifiedToolLibrary` - 统一工具库
   - `DynamicMCPManager` - 动态MCP管理器
   - `MCPSearchTool` - MCP搜索工具
   - `ToolGapDetector` - 工具缺口检测器

### Runtime版本对比

| 特性 | 基础版本 | 增强版本 |
|------|----------|----------|
| 内置工具 | ✅ browser, python_executor | ✅ 全部基础工具 |
| 动态工具安装 | ❌ | ✅ MCP服务器搜索安装 |
| 智能工具检测 | ❌ | ✅ LLM驱动的工具缺口分析 |
| 上下文感知 | ❌ | ✅ 执行上下文管理 |
| 适用场景 | 简单推理任务 | 复杂自适应任务 |

## 📁 项目结构

```
agent-data-platform/
├── core/                    # 核心调度逻辑
│   ├── interfaces.py        # 接口定义
│   ├── dispatcher.py        # 任务分发器
│   ├── llm_client.py        # LLM客户端
│   ├── toolscore/          # 工具管理模块
│   │   ├── unified_tool_library.py
│   │   ├── dynamic_mcp_manager.py
│   │   ├── mcp_search_tool.py
│   │   └── tool_gap_detector.py
│   └── synthesiscore/      # 任务合成模块
├── runtimes/               # 运行时实现
│   ├── reasoning/          # 推理运行时
│   │   ├── runtime.py      # 基础版本
│   │   ├── enhanced_runtime.py  # 增强版本
│   │   └── tools/          # 内置工具
│   ├── sandbox/            # 代码执行沙盒
│   └── web_navigator/      # Web导航运行时
├── mcp_servers/            # MCP工具服务器
│   ├── browser_navigator_server/
│   └── python_executor_server/
├── docs/                   # 文档目录
├── scripts/                # 部署脚本
├── config/                 # 配置文件
├── docker-compose.yml      # 服务编排
└── tasks.jsonl            # 任务定义文件
```

## 📚 详细文档

- **[完整任务执行流程详解](MCP任务执行流程详解.md)** - 深入了解Agent执行机制
- **[MCP主动选择机制使用指南](MCP_主动选择机制使用指南.md)** - 动态工具管理指南
- **[系统架构分析](ARCHITECTURE_ANALYSIS.md)** - 架构设计和实现状况
- **[快速开始指南](QUICK_START.md)** - 详细的部署和使用说明
- **[外部API配置指南](docs/外部API配置指南.md)** - LLM API配置说明
- **[外部 MCP 服务器注册接口](docs/外部MCP服务器注册接口.md)** - 统一注册外部服务器的方法
- **[官方 MCP 服务器列表](docs/外部MCP服务器注册接口.md#获取官方服务器列表)** - 自动获取官方可用服务器

## 🔧 高级配置

### 环境变量

```bash
# Redis配置
REDIS_URL=redis://redis:6379
REDIS_MAX_CONNECTIONS=20

# 任务配置
MAX_CONCURRENT_TASKS=10
TASK_TIMEOUT=300

# 监控配置
METRICS_PORT=8001
HEALTH_CHECK_INTERVAL=30
```

### 性能调优

```bash
# 扩展运行时实例
docker-compose up -d --scale reasoning-runtime=4

# 调整并发限制
export MAX_CONCURRENT_TASKS=20

# 优化内存使用
export MEMORY_LIMIT=4g
```

## 📊 监控和运维

### 监控面板

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Runtime Metrics**: http://localhost:8001/metrics

### 关键指标

- 任务完成率和失败率
- 平均处理时间
- 队列大小
- 缓存命中率
- 动态工具安装统计

## 🔍 故障排查

### 常见问题

1. **服务启动失败** - 检查端口占用和磁盘空间
2. **任务执行卡住** - 检查Redis队列和重启运行时
3. **工具调用失败** - 验证工具服务器状态
4. **内存溢出** - 限制内存使用或增加资源

### 调试命令

```bash
# 查看服务状态
docker-compose ps

# 查看实时日志
docker-compose logs -f reasoning-runtime

# 检查队列状态
docker exec $(docker-compose ps -q redis) redis-cli xlen tasks:reasoning

# 健康检查
curl http://localhost:8001/health
```

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 LICENSE 文件了解详情。

## 🙏 致谢

- **MCP协议** - 标准化的工具通信协议
- **Docker** - 容器化部署支持
- **Redis** - 高性能任务队列
- **Playwright** - 现代Web自动化
- **Prometheus & Grafana** - 监控和可视化

---

**一句话总结**：Agent Data Platform是一个支持动态工具扩展的智能Agent系统，AI可以根据任务需求主动搜索安装新工具，实现真正的自我进化！🚀
