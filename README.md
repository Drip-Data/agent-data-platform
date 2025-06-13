# Agent Data Platform (本地化重构版)

## 简介

本项目是一个完全本地化、无Docker依赖的AI Agent平台，支持本地开发、测试和生产部署。所有服务均为Python实现，工具生态可热插拔扩展。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
pip install playwright
playwright install
```

### 2. 一键启动

- Windows: `run.bat`
- Linux/macOS: `bash run.sh`

### 3. 访问服务

- 工具API: http://localhost:8080/tools/
- 日志、数据、配置均在本地目录

### 4. 开发新工具

详见 DEVELOPMENT.md。

## 目录结构

- core/         # 核心服务（配置、日志、持久化、工具注册/执行等）
- tools/        # 所有本地工具（如PythonExecutor、BrowserNavigator等）
- runtimes/     # 推理引擎与运行时
- tests/        # 单元与集成测试
- main.py       # 应用入口
- requirements.txt
- run.sh / run.bat

## 贡献与扩展

- 详见 DEVELOPMENT.md
- 欢迎PR和Issue

---

**一句话总结**：Agent Data Platform是一个支持动态工具扩展的智能Agent系统，AI可以根据任务需求主动搜索安装新工具，实现真正的自我进化！🚀
