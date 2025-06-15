# Agent Data Platform - 测试文档

## 📋 概述

本测试套件旨在确保 Agent Data Platform 的所有核心组件正常工作，特别关注：
- 🔒 **安全性** - 代码执行沙箱、认证、权限控制
- 🏗️ **架构完整性** - 组件间交互、依赖管理
- 🚀 **性能** - 异步操作、并发处理
- 🛡️ **健壮性** - 错误处理、降级机制

## 🗂️ 测试结构

```
tests/
├── conftest.py                    # pytest 配置和全局 fixtures
├── test_enhanced_runtime.py       # Enhanced Runtime 核心逻辑测试
├── test_core_components.py        # 基础组件测试（新增）
├── test_task_api.py              # Task API 端点测试（新增）
├── test_toolscore_core_manager.py # ToolScore 核心管理器测试（新增）
├── test_security_critical.py      # 安全关键测试（新增）
├── test_mcp_registration.py       # MCP 注册流程测试
├── test_real_time_tool_client.py  # 实时工具客户端测试
└── test_toolscore_client.py       # ToolScore 客户端测试
```

## 🚀 快速开始

### 安装测试依赖

```bash
# 使用测试运行器安装
python run_tests.py --install-deps

# 或手动安装
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

### 运行测试

```bash
# 运行所有测试
python run_tests.py

# 仅运行单元测试（快速）
python run_tests.py --unit

# 运行安全测试
python run_tests.py --security

# 运行特定文件
python run_tests.py -f tests/test_task_api.py

# 并行运行以加速
python run_tests.py --parallel -w 4

# 生成覆盖率报告
python run_tests.py --coverage
```

## 📊 测试覆盖范围

### 1. 核心组件测试 (`test_core_components.py`)
- ✅ ServiceManager 依赖拓扑解析
- ✅ ToolScore 即时工具注册
- ✅ Dispatcher 任务队列管理
- ✅ Redis 降级模式

### 2. Task API 测试 (`test_task_api.py`)
- ✅ RESTful 端点完整性
- ✅ 任务提交与状态查询
- ✅ 错误处理与降级
- ✅ Redis 连接管理

### 3. ToolScore 管理器测试 (`test_toolscore_core_manager.py`)
- ✅ 工具注册与缓存
- ✅ WebSocket 事件通知
- ✅ Redis 事件发布
- ✅ 动态工具安装准备

### 4. 安全测试 (`test_security_critical.py`)
- ⚠️ Python Executor 沙箱隔离（当前缺失）
- ⚠️ MCP WebSocket 认证（当前缺失）
- ⚠️ 工具注册验证（当前缺失）
- ⚠️ API 密钥安全（明文存储）

### 5. Enhanced Runtime 测试 (`test_enhanced_runtime.py`)
- ✅ 任务执行流程
- ✅ 工具缺口检测与安装
- ✅ LLM 交互记录
- ✅ 轨迹保存

## 🔍 测试标记 (Markers)

测试使用以下标记分类：

- `@pytest.mark.unit` - 单元测试（独立、快速）
- `@pytest.mark.integration` - 集成测试（需要外部服务）
- `@pytest.mark.security` - 安全相关测试
- `@pytest.mark.slow` - 慢速测试（>1秒）
- `@pytest.mark.asyncio` - 异步测试

使用标记运行特定类型测试：
```bash
pytest -m unit          # 仅单元测试
pytest -m "not slow"    # 排除慢速测试
pytest -m security      # 仅安全测试
```

## 🛠️ 测试工具

### Fixtures

常用的测试 fixtures（见 `conftest.py`）：

- `mock_redis` - 模拟 Redis 客户端
- `temp_workspace` - 临时工作目录
- `sample_task_spec` - 示例任务规范
- `sample_tool_spec` - 示例工具规范
- `mock_llm_response` - 模拟 LLM 响应

### Mock 策略

所有外部依赖都使用 Mock 对象：
- Redis → `AsyncMock`
- WebSocket → `AsyncMock`
- HTTP 客户端 → `AsyncMock`
- Docker → `MagicMock`
- 文件系统 → `tmp_path` fixture

## 📈 覆盖率目标

当前覆盖率目标：
- 总体覆盖率: **80%**
- 核心模块: **90%**
- 安全相关: **95%**

查看覆盖率报告：
```bash
# 生成并打开 HTML 报告
python run_tests.py --coverage
# 报告位置: htmlcov/index.html
```

## 🐛 已知问题

### 高优先级
1. **Python Executor 无沙箱** - 任意代码执行风险
2. **WebSocket 无认证** - 未授权访问风险
3. **工具注册无验证** - 恶意工具注入风险

### 中优先级
1. **端口硬编码** - 配置不一致
2. **错误信息泄露** - 可能暴露敏感信息
3. **测试覆盖不足** - 部分关键路径未测试

## 🔧 调试技巧

### 1. 运行单个测试
```bash
pytest tests/test_task_api.py::test_submit_task_success -v
```

### 2. 查看详细日志
```bash
pytest --log-cli-level=DEBUG
```

### 3. 进入调试器
```python
import pdb; pdb.set_trace()  # 在测试中添加断点
```

### 4. 保存失败的测试
```bash
pytest --lf  # 仅运行上次失败的测试
```

## 📝 编写新测试

### 测试模板
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.unit
@pytest.mark.asyncio
async def test_feature_name():
    """测试功能描述"""
    # Arrange - 准备测试数据
    mock_dep = AsyncMock()
    
    # Act - 执行测试
    result = await function_under_test(mock_dep)
    
    # Assert - 验证结果
    assert result.success is True
    mock_dep.method.assert_called_once_with(expected_args)
```

### 最佳实践
1. **隔离性** - 每个测试独立，不依赖其他测试
2. **可重复** - 测试结果一致，不受环境影响
3. **快速** - 单元测试应在毫秒级完成
4. **清晰** - 测试名称描述测试内容
5. **完整** - 覆盖正常和异常情况

## 🚨 安全测试重点

基于 `test_security_critical.py` 的发现，以下安全改进是必需的：

1. **立即修复**
   - Python Executor 添加 Docker 沙箱
   - MCP WebSocket 添加 JWT 认证
   - 工具注册添加签名验证

2. **短期改进**
   - API 密钥使用环境变量或密钥管理服务
   - 错误消息清理敏感信息
   - 添加请求速率限制

3. **长期规划**
   - 实现细粒度权限系统
   - 添加审计日志
   - 定期安全扫描

## 📞 联系方式

如有测试相关问题，请：
1. 查看测试日志 `tests/test.log`
2. 运行 `pytest --pdb` 进入调试模式
3. 提交 Issue 到项目仓库

---

**记住**: 好的测试是系统质量的保证！ 🎯