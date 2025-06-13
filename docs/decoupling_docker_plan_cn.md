# ToolScore 去 Docker 解耦方案

> 目标：完全摆脱 Docker / Compose 依赖，使平台在纯 Python 虚拟环境 (venv) 内即可安装、运行、测试全部功能。

---

## 1. 与 Docker 耦合的现状

| 位置 | 作用 | 典型调用 |
|------|------|---------|
| `core/toolscore/core_manager.py` | 容器恢复、创建持久化服务 | `docker.from_env()`, `containers.run()` |
| `core/toolscore/dynamic_mcp_manager.py` | 安装 MCP Server 时 `docker build/pull/run` | 大量 `docker.*` / `subprocess('docker …')` |
| `docker-compose.yml`, 根 `Dockerfile`, `runtimes/**/Dockerfile` | 系统编排与镜像构建 | — |
| `scripts/load_test.sh` 等 | 调用 `docker compose` | — |

---

## 2. 设计原则

1. **Runner 抽象**：用接口屏蔽"启动/停止/健康检查"实现，可插拔 `DockerRunner` / `ProcessRunner`。
2. **Process 优先**：默认使用 `ProcessRunner`，直接在本机 venv 启动 MCP Server（git clone → pip install -e . → python main.py）。
3. **向下兼容**：保留 DockerRunner 以便未来可回切容器。
4. **安全隔离**：进程模式需设置 `venv`、端口占用检查、超时回收。

---

## 3. 任务拆分

| # | 文件 / 目录 | 变更内容 |
|---|-------------|----------|
| 1 | `core/toolscore/runners/` | 新建 `__init__.py` + `base.py` (接口) + `docker_runner.py` (旧逻辑) + `process_runner.py` (新逻辑) |
| 2 | `core/toolscore/core_manager.py` | • 删除 `docker.from_env()` 依赖<br>• 注入 `self.runner: BaseRunner`，默认 `ProcessRunner` |
| 3 | `core/toolscore/dynamic_mcp_manager.py` | • 替换所有 `docker_*` 安装实现 -> `ProcessRunner.install_server()`<br>• 移除 Dockerfile 生成器 |
| 4 | WebSocket/监控 | 容器字段改为 `process_status`, `pid` |
| 5 | 项目根 | 删除 `docker-compose.yml`, `Dockerfile`, `runtimes/**/Dockerfile`, `docker/` 目录 |
| 6 | 脚本 & 文档 | 更新脚本到 `venv` 流程；修改 `README` & CI |
| 7 | 测试 | 本地跑 `pytest` 确认工具安装 -> 调用 -> 轨迹保存链路正常 |

---

## 4. `Runner` 接口草案

```python
# core/toolscore/runners/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseRunner(ABC):
    @abstractmethod
    async def install_server(self, candidate: dict) -> Dict[str, Any]:
        """安装并启动 MCP Server，返回 {success, endpoint, pid, error_msg}"""

    @abstractmethod
    async def stop_server(self, server_id: str) -> bool:
        """停止并清理"""

    @abstractmethod
    async def health_check(self, endpoint: str) -> bool:
        """端点健康检查"""
```

`ProcessRunner` 将：
1. `git clone` -> 临时目录；
2. `pip install -e .` 或检测 `package.json` 走 `npm install`；
3. `subprocess.Popen([...])` 启动，并写入 `pidfile`；
4. 端口选取：使用 `DynamicMCPManager._allocate_port()`；
5. 健康检查：HTTP/WS ping。

---

## 5. 逐步实施计划

1. **Stage-A：构建 Runner 抽象**
   * 新建 `runners` 目录 & `BaseRunner` / `DockerRunner` / `ProcessRunner`。
   * 在 `CoreManager` 注入 `self.runner`，暂时仍使用 `DockerRunner`（保持可运行）。

2. **Stage-B：实现 ProcessRunner**
   * 最小化流程：`python -m venv`, `pip install -e .`, `python server.py --port {}`。
   * 修改 `CoreManager` & `DynamicMCPManager` 切换默认 runner。

3. **Stage-C：移除 Docker 专属代码**
   * 执行大规模删除：Dockerfile / compose / docker dir。
   * 删除或重构 `_install_docker_*`、`docker_client.*` 调用。

4. **Stage-D：测试 & 文档**
   * 本地 `make dev-up`：创建 venv、安装依赖、启动 ToolScore + Reasoning Runtime。
   * 运行 `tests/`，生成轨迹。
   * 更新 `README` 指南。

---

> **接下来**：将从 Stage-A 开始提交代码修改，先创建 Runner 抽象并保证现有流程不受影响。 