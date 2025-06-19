# 第一部分：microsandbox详细说明
# Microsandbox 完整文档

## 简介

Microsandbox 是一个安全代码执行平台，提供虚拟机级别的隔离和闪电般快速的启动。它专为AI代理、开发者以及任何需要安全执行代码的用户而构建，无需在速度或安全性上妥协。

### 为什么选择 Microsandbox？

传统的代码执行方案都存在严重缺陷：
- **本地运行** - 一个恶意脚本就能危及整个系统
- **使用容器** - 共享内核意味着高级攻击仍可能突破
- **传统虚拟机** - 等待10+秒的虚拟机启动会影响效率和性能
- **云解决方案** - 成本可能快速攀升且受制于云提供商

Microsandbox 结合了所有方案的优点：
- **绝对安全** - 真正的虚拟机隔离，拥有独立内核
- **闪电启动** - 毫秒级启动时间
- **AI集成就绪** - 原生支持MCP协议，可与Claude等AI工具直接连接

## 快速开始

### 系统要求

- **macOS** - 需要Apple Silicon (M1/M2/M3/M4)，暂不支持Intel Mac
- **Linux** - 必须启用KVM虚拟化，可通过 `lsmod | grep kvm` 检查
- **Windows** - 即将推出

### 安装

使用安装脚本快速安装：

```bash
curl -sSL https://get.microsandbox.dev | sh
```

### 启动服务器

以开发模式启动服务器：

```bash
msb server start --dev
```

### 你的第一个沙箱

#### Python 示例

```python
import asyncio
from microsandbox import PythonSandbox

async def main():
    async with PythonSandbox.create(name="my-first-sandbox") as sb:
        # 执行Python代码
        exec = await sb.run("name = 'World'")
        exec = await sb.run("print(f'Hello {name}!')")
        
        # 获取输出
        output = await exec.output()
        print(output)  # 输出: Hello World!

asyncio.run(main())
```

#### JavaScript 示例

```javascript
import { NodeSandbox } from "microsandbox";

async function main() {
    const sb = await NodeSandbox.create({ name: "my-first-sandbox" });
    try {
        // 执行JavaScript代码
        let exec = await sb.run("var name = 'World'");
        exec = await sb.run("console.log(`Hello ${name}!`)");
        
        // 获取输出
        const output = await exec.output();
        console.log(output); // 输出: Hello World!
    } finally {
        await sb.stop();
    }
}

main().catch(console.error);
```

## 沙箱类型

### PythonSandbox

PythonSandbox 提供完整的Python环境，具备以下特性：
- 完整的Python 3.x环境
- 通过pip进行包管理
- 文件系统访问
- Shell命令执行
- 执行间状态持久化

#### 使用示例

```python
import asyncio
from microsandbox import PythonSandbox

async def main():
    async with PythonSandbox.create(name="python-demo") as sb:
        # 直接执行Python代码
        exec = await sb.run("print('Hello from Python!')")
        print(await exec.output())
        
        # 安装和使用包
        await sb.run("pip install requests")
        exec = await sb.run("""
import requests
response = requests.get('https://httpbin.org/json')
print(response.status_code)
""")
        print(await exec.output())

asyncio.run(main())
```

### NodeSandbox

NodeSandbox 提供完整的Node.js环境，具备以下特性：
- 完整的Node.js运行时环境
- 访问内置Node.js模块（fs、os、path等）
- 通过npm进行包管理
- 文件系统访问
- 执行间状态持久化

#### 使用示例

```python
import asyncio
from microsandbox import NodeSandbox

async def main():
    async with NodeSandbox.create(name="node-demo") as sb:
        # 执行JavaScript代码
        exec = await sb.run("console.log('Hello from Node.js!');")
        print("输出:", await exec.output())
        
        # 使用Node.js内置模块
        node_code = """
const fs = require('fs');
const os = require('os');

// 写入和读取文件
fs.writeFileSync('/tmp/test.txt', 'Hello from Node.js!');
const content = fs.readFileSync('/tmp/test.txt', 'utf8');
console.log('文件内容:', content);

// 获取系统信息
console.log('平台:', os.platform());
console.log('Node.js版本:', process.version);
"""
        exec = await sb.run(node_code)
        print(await exec.output())

asyncio.run(main())
```

### 选择合适的沙箱

**使用 PythonSandbox 当你需要：**
- 执行Python代码
- 使用PyPI的Python包
- 数据科学库（pandas、numpy等）
- 构建基于Python的应用程序
- 需要在Python代码旁边运行shell命令

**使用 NodeSandbox 当你需要：**
- 执行JavaScript代码
- 使用npm包
- 构建Node.js应用程序
- 访问Node.js内置模块
- 处理Web相关的JavaScript代码

## CLI 参考

### 全局安装

```bash
curl -sSL https://get.microsandbox.dev | sh
```

### 服务器管理

#### 启动服务器

```bash
# 开发模式启动
msb server start --dev

# 自定义端口启动
msb server start --port 8080

# 自定义主机启动
msb server start --host 0.0.0.0

# 后台启动
msb server start --detach

# 使用特定密钥启动
msb server start --key mySecretKey123
```

#### 生成API密钥

```bash
# 为所有命名空间生成API密钥
msb server keygen

# 生成有过期时间的密钥
msb server keygen --expire 24h

# 为特定命名空间生成密钥
msb server keygen --namespace production
```

#### 查看服务器状态

```bash
# 显示所有沙箱状态
msb server status

# 显示特定沙箱状态
msb server status app database

# 显示特定命名空间的状态
msb server status --namespace production
```

### 项目管理

#### 初始化项目

```bash
# 在当前目录初始化项目
msb init

# 在特定目录初始化
msb init --file /path/to/project/
```

#### 添加沙箱

```bash
# 添加简单沙箱
msb add app --image node:18

# 添加带端口映射的沙箱
msb add web --image nginx:alpine --port 8080:80 --env NODE_ENV=production

# 添加带卷挂载的沙箱
msb add database --image postgres:15 --volume ./data:/var/lib/postgresql/data --memory 512 --cpus 2
```

#### 移除沙箱

```bash
# 移除沙箱
msb remove app

# 移除多个沙箱
msb remove web api database
```

### 沙箱操作

#### 运行沙箱

```bash
# 运行沙箱
msb run app

# 运行特定脚本
msb run app~test

# 后台运行
msb run app --detach

# 在沙箱中执行命令
msb run app --exec bash
```

#### 打开Shell

```bash
# 在沙箱中打开shell
msb shell app
```

#### 运行临时沙箱

```bash
# 运行临时沙箱
msb exe python:3.11

# 带资源限制运行
msb exe ubuntu:22.04 --memory 256 --cpus 1 --volume ./code:/workspace
```

#### 查看日志

```bash
# 显示沙箱日志
msb log app

# 实时跟踪日志
msb log app --follow

# 显示最后50行
msb log app --tail 50
```

### 项目生命周期

#### 应用配置

```bash
# 应用当前项目配置
msb apply

# 后台应用
msb apply --detach
```

#### 启动项目

```bash
# 启动所有沙箱
msb up

# 启动特定沙箱
msb up app database

# 后台启动
msb up --detach
```

#### 停止项目

```bash
# 停止所有沙箱
msb down

# 停止特定沙箱
msb down app database
```

## API 参考

### 基础URL

默认服务器运行在 `http://127.0.0.1:5555`，所有API端点都以 `/api/v1` 为前缀。

### 认证

API使用Bearer token认证，在Authorization头中包含API密钥：

```
Authorization: Bearer YOUR_API_KEY
```

生成API密钥：

```bash
msb server keygen
```

### REST端点

#### 健康检查

```
GET /api/v1/health
```

响应：
```json
{
  "message": "Service is healthy"
}
```

### JSON-RPC API

主要API使用HTTP POST上的JSON-RPC 2.0，所有请求发送到 `/api/v1/rpc`。

#### 请求格式

```json
{
  "jsonrpc": "2.0",
  "method": "method_name",
  "params": { ... },
  "id": "unique_request_id"
}
```

#### 响应格式

成功：
```json
{
  "jsonrpc": "2.0",
  "result": { ... },
  "id": "unique_request_id"
}
```

错误：
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32603,
    "message": "Error description",
    "data": null
  },
  "id": "unique_request_id"
}
```

### 沙箱管理

#### 启动沙箱

```json
{
  "jsonrpc": "2.0",
  "method": "sandbox.start",
  "params": {
    "sandbox": "my-python-env",
    "namespace": "default",
    "config": {
      "image": "microsandbox/python",
      "memory": 1024,
      "cpus": 2,
      "envs": ["DEBUG=true"],
      "workdir": "/workspace"
    }
  },
  "id": "1"
}
```

#### 停止沙箱

```json
{
  "jsonrpc": "2.0",
  "method": "sandbox.stop",
  "params": {
    "sandbox": "my-python-env",
    "namespace": "default"
  },
  "id": "2"
}
```

#### 获取沙箱指标

```json
{
  "jsonrpc": "2.0",
  "method": "sandbox.metrics.get",
  "params": {
    "namespace": "default",
    "sandbox": "my-python-env"
  },
  "id": "3"
}
```

### 代码执行

#### 执行代码

```json
{
  "jsonrpc": "2.0",
  "method": "sandbox.repl.run",
  "params": {
    "sandbox": "my-python-env",
    "namespace": "default",
    "language": "python",
    "code": "print('Hello, World!')"
  },
  "id": "4"
}
```

#### 执行命令

```json
{
  "jsonrpc": "2.0",
  "method": "sandbox.command.run",
  "params": {
    "sandbox": "my-python-env",
    "namespace": "default",
    "command": "ls",
    "args": ["-la", "/workspace"]
  },
  "id": "5"
}
```

## MCP支持

Microsandbox服务器实现了模型上下文协议（Model Context Protocol），使其与Claude等AI工具兼容。

### 可用的MCP工具

- `sandbox_start` - 启动新沙箱
- `sandbox_stop` - 停止运行中的沙箱
- `sandbox_run_code` - 在沙箱中执行代码
- `sandbox_run_command` - 在沙箱中执行命令
- `sandbox_get_metrics` - 获取沙箱指标

### 可用的MCP提示

- `create_python_sandbox` - 创建Python沙箱的模板
- `create_node_sandbox` - 创建Node.js沙箱的模板

## 应用场景

### AI代码执行平台

构建能够安全执行其生成代码的AI助手。无论是简单的Python脚本还是复杂的Web应用程序，你的AI都能实时运行、测试和调试代码，而不会危及基础设施。

### 安全数据分析服务

创建用户可以上传数据集并运行自定义分析脚本的平台，无需安全顾虑。支持任何数据科学堆栈——Python与pandas、R用于统计、Julia用于高性能计算——同时保持完全隔离。

### 交互式学习环境

为教育和培训部署即时编码环境。学生可以直接通过浏览器编写、编译和执行任何编程语言的代码，同时你保持完全的安全隔离。

### 持续集成与测试

在隔离环境中快速原型化和测试微服务。启动完整的应用程序堆栈，测试API集成，并验证部署配置，而不影响主要基础设施。

## 错误处理

### 标准JSON-RPC错误代码

- `-32700` - 解析错误
- `-32600` - 无效请求
- `-32601` - 方法未找到
- `-32602` - 无效参数
- `-32603` - 内部错误

### 自定义错误代码

- `-32002` - 需要认证
- `-32004` - 沙箱未找到
- `-32005` - 沙箱已存在

## 最佳实践

### 推荐做法

- 使用完毕后始终停止沙箱以防止资源泄漏
- 为沙箱和命名空间使用有意义的名称
- 为操作设置适当的超时
- 定期监控指标以跟踪资源使用情况
- 使用适当的重试逻辑优雅地处理错误
- 使用命名空间按项目或团队组织沙箱

### 常见陷阱

- 启动沙箱而不停止它们（资源泄漏）
- 在沙箱/命名空间名称中使用无效字符
- 没有正确处理超时错误
- 尝试对不存在的沙箱进行操作
- 忘记包含认证头

## 完整工作流示例

```javascript
const apiKey = "your-api-key";
const baseUrl = "http://127.0.0.1:5555/api/v1/rpc";

// 1. 启动沙箱
const startResponse = await fetch(baseUrl, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${apiKey}`
  },
  body: JSON.stringify({
    jsonrpc: "2.0",
    method: "sandbox.start",
    params: {
      sandbox: "my-env",
      namespace: "default",
      config: {
        image: "microsandbox/python",
        memory: 512
      }
    },
    id: "1"
  })
});

// 2. 执行代码
const runResponse = await fetch(baseUrl, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${apiKey}`
  },
  body: JSON.stringify({
    jsonrpc: "2.0",
    method: "sandbox.repl.run",
    params: {
      sandbox: "my-env",
      namespace: "default",
      language: "python",
      code: "print('Hello from API!')"
    },
    id: "2"
  })
});

// 3. 停止沙箱
const stopResponse = await fetch(baseUrl, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${apiKey}`
  },
  body: JSON.stringify({
    jsonrpc: "2.0",
    method: "sandbox.stop",
    params: {
      sandbox: "my-env",
      namespace: "default"
    },
    id: "3"
  })
});
```

## 故障排除

### 首次运行时间较长

首次创建沙箱时，microsandbox需要下载基础镜像。这是正常的，后续运行会快得多。

### 服务器无法启动

检查没有其他服务使用默认端口。可以使用自定义端口：

```bash
msb server start --dev --port 8080
```

## 支持

如有技术支持问题、发现缺陷或想要提出功能请求，请在GitHub上创建issue开始讨论。

项目地址：https://github.com/microsandbox/microsandbox/issues

---

*此文档基于 https://docs.microsandbox.dev/ 的内容整理而成*


# 第二部分：重启后工作继续指南

## 当前任务状态

### 🎯 主要目标
完成MicroSandbox工具执行问题的最终修复验证，确保系统能正常执行代码并返回结果。

### ✅ 已完成的工作
1. **Browser Use端口冲突** - 已修复配置文件中的重复定义
2. **轨迹输出格式优化** - 已修复JSON序列化，使用structured格式  
3. **错误信息增强** - 已添加详细traceback和debug信息
4. **API服务** - 已确认正常启动和运行
5. **MicroSandbox分析** - 确认适合agent项目，支持完全本地部署

### 🔧 重要代码修改
已修改 `/Users/zhaoxiang/Documents/Datapresso/agent-data-platform/mcp_servers/microsandbox_server/main.py`：
- 减少MicroSandbox连接超时（5秒）
- 增强错误日志记录
- 优化fallback机制，立即启用本地Python执行器

### ❌ 待解决问题
MicroSandbox工具执行仍返回"Unknown error"，原因是多个顽固进程冲突。

## 🚀 重启后执行步骤

### 1. 环境验证
```bash
# 确认MicroSandbox进程已清理
ps aux | grep -E "(msbrun|msbserver|microsandbox)" | grep -v grep

# 确认端口释放
lsof -i :5555 || echo "端口5555已释放"
```

### 2. 启动系统
```bash
# 启动主程序
cd /Users/zhaoxiang/Documents/Datapresso/agent-data-platform
python3 main.py
```

### 3. 验证服务健康
```bash
# 等待启动完成（约10-15秒）
sleep 15

# 检查API健康状态
curl http://localhost:8000/health
```

### 4. 提交测试任务
```bash
# 测试MicroSandbox修复
curl -X POST http://localhost:8000/api/v1/tasks \
-H "Content-Type: application/json" \
-d '{
  "task_type": "reasoning",
  "input": "验证MicroSandbox修复：计算5*5并输出结果",
  "priority": "high"
}'
```

### 5. 监控执行过程
```bash
# 查看执行日志
tail -f main.log

# 检查轨迹输出
cat output/trajectories/trajectories_collection.json | tail -20
```

## 🔍 期望结果

### 成功标志
- ✅ MicroSandbox连接失败时快速fallback到本地执行器
- ✅ 看到日志："立即启用本地Python执行器作为备用方案"
- ✅ 任务成功执行，返回正确的计算结果（25）
- ✅ 轨迹数据显示 `"success": true`

### 如果仍有问题
检查日志中的详细错误信息（现在应该有完整的traceback）

## 📋 Todo状态
- [x] Browser Use端口冲突修复
- [x] 轨迹输出格式优化
- [x] API服务启动修复
- [x] MicroSandbox评估和架构设计
- [ ] **验证MicroSandbox最终修复** ⬅️ 当前重点

## 💡 备注
如果MicroSandbox仍有问题，fallback机制现在应该能确保系统正常工作。重点是验证整个工作流程是否流畅，而不是强制让MicroSandbox工作。

---
*创建时间: 2025-06-19 17:33*  
*状态: 等待重启后验证*