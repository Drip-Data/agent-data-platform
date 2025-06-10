# Agent Data Platform

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-brightgreen)

一个生产级的、可扩展的、用于构建高质量 Agent 轨迹数据的平台。

## 📖 概述

Agent Data Platform 是一个专为运行 AI Agent 并捕获其完整决策轨迹而设计的集成系统。它允许 Agent 使用多种强大的工具（如代码执行器、浏览器），并通过一个健壮的、基于消息队列的架构来处理复杂的、多步骤的任务。

本平台的核心目标是自动化地生成高质量的 Agent 轨迹数据，这些数据对于 Agent 的评估、微调和深入研究至关重要。

## ✨ 核心特性

- **可扩展架构**: 基于 Docker Compose 和 Redis 队列，可以轻松横向扩展各个运行时组件。
- **多工具支持**: 内置了生产级的 Python 代码执行器和基于 Playwright 的浏览器导航工具。
- **强大的智能推理**: 使用先进的 LLM（如 Gemini）进行任务分解、工具选择和决策。
- **详细的轨迹追踪**: 自动记录任务执行的每一步，包括思考链、工具调用参数、执行结果（Observation），并将最终轨迹保存为 JSON 文件。
- **标准化的工具接口**: 通过 MCP (Multi-Capability Protocol) 协议和 ToolScore 服务，实现了工具的标准化注册、发现和调用。
- **易于部署和使用**: 只需几条命令即可启动整个平台，并通过简单的 API 调用来提交任务。


## 🚀 快速开始

只需三个步骤，即可在本地运行整个平台并提交您的第一个 Agent 任务。

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
接下来，编辑 `.env` 文件，并填入您的 `GEMINI_API_KEY`。

```.env
# .env
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
```

### 3. 构建并启动服务

```bash
docker-compose up -d --build
```
这个命令会构建所有服务的 Docker 镜像并以后台模式启动它们。第一次启动可能需要几分钟时间来下载和安装依赖。

## 🧪 测试您的 Agent

服务启动后，您可以通过 `dispatcher` 的 API 来提交任务。

### 样例 1: 执行 Python 代码

提交一个计算斐波那契数的复杂算法任务。

```bash
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{
  "task_type": "reasoning",
  "input": "使用Python，编写一个递归函数来计算第10个斐波那契数并返回结果。",
  "priority": "high"
}'
```

### 样例 2: 使用浏览器

提交一个访问网页并提取标题的浏览器任务。

```bash
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{
  "task_type": "reasoning",
  "input": "访问 https://datapresso.ai/，并告诉我网站的标题是什么",
  "priority": "high"
}'
```

### 样例 3: 多步Web交互任务

提交一个在 Google 搜索特定关键词，并提取第一个结果信息的任务。这需要Agent执行导航、输入、点击和提取文本等多个步骤。

```bash
curl -X POST http://localhost:8000/api/v1/tasks -H "Content-Type: application/json" -d '{
  "task_type": "reasoning",
  "input": "使用浏览器访问 google.com，搜索 "Datapresso"，然后告诉我第一个搜索结果的标题和链接摘要。",
  "priority": "high"
}'
```

### 验证结果

任务执行后，其轨迹会保存在 `enhanced-reasoning-runtime` 容器中。您可以通过以下命令查看最新的轨迹数据来验证任务是否成功：

```bash
# 等待约30秒让任务执行完成
sleep 30

# 查看轨迹文件内容
docker exec agent-data-platform-enhanced-reasoning-runtime-1 cat /app/output/trajectories/trajectories_collection.json | jq .[-1]
```
在返回的 JSON 中，查找 `"success": true` 来确认任务是否成功完成。

## 📁 项目结构

```
agent-data-platform/
├── core/                    # 核心调度、接口和工具逻辑
├── mcp_servers/             # 所有 MCP 工具服务器的实现
│   ├── browser_navigator_server/
│   └── python_executor_server/
├── runtimes/                # 运行时环境
│   └── reasoning/           # 智能推理运行时
├── .env.example             # 环境变量模板
├── .gitignore               # Git 忽略文件
├── docker-compose.yml       # 服务编排文件
└── README.md                # 本文档
```

## 🤝 贡献

欢迎任何形式的贡献！请随时 Fork 项目、创建分支并提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证。
