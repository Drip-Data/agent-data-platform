# Agent Data Platform

🚀 **智能代理数据平台** - 基于MCP协议的企业级AI任务执行框架

---

## 📖 项目概述

**Agent Data Platform** 是一个先进的智能代理系统，专为**自动化AI任务执行**和**大规模数据处理**而设计。该平台采用**模块化微服务架构**，结合**大语言模型推理能力**和**可扩展工具生态**，为复杂任务的智能化处理提供完整解决方案。

### 🎯 核心价值

- **🤖 智能决策**: 基于Gemini LLM的自主任务分析和代码生成
- **🔧 工具生态**: 基于MCP协议的可扩展工具服务器架构  
- **⚡ 高性能**: Redis驱动的异步任务队列和并发处理
- **🔒 安全执行**: 沙箱化代码执行环境，确保系统安全
- **📊 全链路追踪**: 完整的任务执行轨迹记录和分析
- **🌐 标准化接口**: RESTful API和WebSocket支持

---

## ⚡ 快速开始

只需 3 步，即可本地跑通首个任务：

1. 克隆仓库并安装依赖  
```bash
git clone https://github.com/your-username/agent-data-platform.git
cd agent-data-platform
pip install -r requirements.txt   # 或使用 conda，详见后文
```

2. 配置 API Key 并启动服务  
```bash
export GEMINI_API_KEY=你的_Gemini_API_Key
python main.py              # 一条命令启动全部核心组件
```

3. 提交测试任务
```bash
# 任务API端口现在是自动分配的，请根据实际启动日志获取端口
# 默认情况下，Task API 会尝试使用 8000 端口，如果被占用则自动分配
# 假设Task API运行在 http://localhost:8000 (或自动分配的端口)
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{"input": "请计算1+2+...+100的和", "description": "首个测试任务"}'
```

几秒后，你将收到包含 `task_id` 的响应。随后运行：

```bash
# 假设Task API运行在 http://localhost:8000 (或自动分配的端口)
curl http://localhost:8000/api/v1/tasks/<task_id>
```

即可查看执行结果。

👉 想批量压测？试试：`python scripts/batch_test_tasks.py --tasks-file tasks.jsonl`。
