# Agent Data Platform – Enhanced Reasoning Runtime 快速上手指南

> 适用版本：`main.py`（2025-06-13 之后修订）

---

## 服务一览

| 组件 | 主要职责 | 端口 |
|------|-----------|------|
| ToolScore MCP Server | WebSocket 接入 / 工具路由 | **8081** (`ws://localhost:8081/websocket`)
| ToolScore Monitoring / HTTP API | 工具查询、执行、实时事件 | **8082** (`http://localhost:8082`)
| Python-Executor MCP Server | Python 代码执行 | **8083** (`ws://localhost:8083/mcp`)
| Task API | 外部提交任务 / 查询 | **8000**
| Redis | 任务队列 & 缓存 | **6379**

> `main.py` 现已在启动流程中同时拉起上述全部组件，并自动将 **EnhancedReasoningRuntime** 注入任务消费队列 `tasks:reasoning`。

---

## 一键启动

```bash
# 确保 Redis 已在本机 6379 端口运行
redis-server &

# 启动平台（根目录）
python main.py
```

启动成功后日志将出现：

```
ToolScore MCP Server 已启动在端口 8081
Python Executor MCP Server 已启动在端口 8083 (已手动注册)
Task API 已启动在端口 8000
Enhanced Reasoning Runtime 已启动并接入任务队列 (tasks:reasoning)
Agent Data Platform 启动成功！
```

---

## 发送任务

### 方式 1：直接调用 ToolScore HTTP API

```bash
curl -X POST http://localhost:8082/api/v1/tools/execute \
     -H 'Content-Type: application/json' \
     -d '{
  "tool_id": "python-executor-mcp-server",
  "action": "python_execute",
  "parameters": {"code": "print(6*20)"}
}'
```

返回示例：

```json
{
  "success": true,
  "result": {
    "stdout": "120\n",
    "stderr": "",
    "return_code": 0
  },
  "processing_time_ms": 35
}
```

### 方式 2：经由 EnhancedReasoningRuntime（推荐）

Enhanced 运行时会监听 Redis Stream `tasks:reasoning`，消费任务并自动调用 ToolScore。

```python
import asyncio, json, redis.asyncio as redis
from core.interfaces import TaskSpec, TaskType

a_sync = redis.from_url("redis://localhost:6379")

async def push_task():
    task = TaskSpec(task_id="", task_type=TaskType.CODE,
                    description="请用 python 计算 6*20 并输出结果")
    await a_sync.xadd("tasks:reasoning", {"task": task.json()})
    print("任务已提交：", task.task_id)

asyncio.run(push_task())
```

可通过 Task API 查询任务状态：

```
curl http://localhost:8000/tasks/<task_id>
```

---

## 关键环境变量

| 变量 | 作用 | 默认 | 已在 `main.py` 中设置 |
|------|------|------|-----------------------|
| `TOOLSCORE_HTTP_URL` | EnhancedRuntime 访问 ToolScore HTTP API | `http://localhost:8082` | ✅ |
| `TOOLSCORE_URL` | EnhancedRuntime 访问 ToolScore MCP WS | `ws://localhost:8081/websocket` | ✅ |

如需调整端口，只需修改 `main.py` 中的 `os.environ.setdefault(...)` 行。

---

## 常见问题

1. **Redis 未运行** → EnhancedRuntime 无法消费任务。
   * 解决：`redis-server`。
2. **端口冲突** → 保证 `8081 / 8082 / 8083 / 8000` 空闲。
3. **LLM Key 缺失** → 设置 `GEMINI_API_KEY` 或将 `provider` 改为你有权限的模型。

---

## 目录结构速览

```
agent-data-platform/
├── main.py                     # 统一启动入口（含 Enhanced Runtime）
├── core/
│   └── toolscore/              # ToolScore 核心模块
├── mcp_servers/               # 各语言 MCP Server
├── runtimes/
│   └── reasoning/
│       ├── enhanced_runtime.py # 运行时逻辑
│       └── ...
└── docs/
    └── quickstart_enhanced_runtime.md  # ← 本文档
```

---

**现在，你可以放心地向 Task 队列发送各种推理任务，EnhancedReasoningRuntime 将自动通过 ToolScore 调用最佳工具完成任务🎉** 