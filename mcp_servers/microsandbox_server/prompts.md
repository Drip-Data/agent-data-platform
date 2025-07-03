# MicroSandbox MCP Server - 内置Prompt指南

## 🔒 服务概述
安全的Python代码执行沙盒服务，提供隔离的代码运行环境，支持包管理和会话控制。

## 🔧 工具分类与使用指南

### 💻 核心操作
- **microsandbox_execute**: 执行Python代码
  - 参数: `code` (required), `session_id` (optional), `timeout` (optional)
  - 示例: `<microsandbox><microsandbox_execute>print('Hello World'); result = 2 + 3; print(result)</microsandbox_execute></microsandbox>`
  - 用途: 在安全沙盒中执行任意Python代码

- **microsandbox_install_package**: 安装Python包
  - 参数: `package_name` (required), `version` (optional), `session_id` (optional)
  - 示例: `<microsandbox><microsandbox_install_package>numpy</microsandbox_install_package></microsandbox>`
  - 用途: 在沙盒环境中安装第三方Python包

### 🎛️ 会话管理
- **microsandbox_list_sessions**: 列出活跃会话
  - 参数: 无
  - 示例: `<microsandbox><microsandbox_list_sessions></microsandbox_list_sessions></microsandbox>`
  - 用途: 查看当前所有活跃的沙盒会话

- **microsandbox_close_session**: 关闭指定会话
  - 参数: `session_id` (required)
  - 示例: `<microsandbox><microsandbox_close_session>my-session-id</microsandbox_close_session></microsandbox>`
  - 用途: 关闭特定的沙盒会话，释放资源

- **microsandbox_cleanup_expired**: 清理过期会话
  - 参数: `max_age` (optional) - 最大年龄秒数
  - 示例: `<microsandbox><microsandbox_cleanup_expired></microsandbox_cleanup_expired></microsandbox>`
  - 用途: 自动清理超时或过期的会话

### 📊 监控诊断
- **microsandbox_get_performance_stats**: 获取性能统计
  - 参数: 无
  - 示例: `<microsandbox><microsandbox_get_performance_stats></microsandbox_get_performance_stats></microsandbox>`
  - 用途: 获取沙盒的性能指标和资源使用统计

- **microsandbox_get_health_status**: 获取健康状态
  - 参数: 无
  - 示例: `<microsandbox><microsandbox_get_health_status></microsandbox_get_health_status></microsandbox>`
  - 用途: 检查沙盒服务的健康状态和可用性

## 💡 使用模式

### 🎯 快速代码执行
```xml
<microsandbox><microsandbox_execute>
# 计算斐波那契数列
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(f"第10项斐波那契数: {fibonacci(10)}")
</microsandbox_execute></microsandbox>
```

### 📦 包管理工作流
```xml
<!-- 1. 安装必要的包 -->
<microsandbox><microsandbox_install_package>pandas</microsandbox_install_package></microsandbox>

<!-- 2. 执行使用该包的代码 -->
<microsandbox><microsandbox_execute>
import pandas as pd
data = {'A': [1, 2, 3], 'B': [4, 5, 6]}
df = pd.DataFrame(data)
print(df)
</microsandbox_execute></microsandbox>
```

### 🔬 科学计算示例
```xml
<!-- 安装科学计算包 -->
<microsandbox><microsandbox_install_package>numpy</microsandbox_install_package></microsandbox>
<microsandbox><microsandbox_install_package>matplotlib</microsandbox_install_package></microsandbox>

<!-- 执行科学计算 -->
<microsandbox><microsandbox_execute>
import numpy as np
import matplotlib.pyplot as plt

# 生成数据
x = np.linspace(0, 2*np.pi, 100)
y = np.sin(x)

# 计算统计信息
mean_y = np.mean(y)
std_y = np.std(y)

print(f"Sin函数的均值: {mean_y:.4f}")
print(f"Sin函数的标准差: {std_y:.4f}")
</microsandbox_execute></microsandbox>
```

## ⚠️ 安全特性

1. **沙盒隔离**: 所有代码在隔离环境中运行，无法访问主机系统
2. **资源限制**: 自动限制CPU、内存和执行时间
3. **会话隔离**: 不同会话之间完全隔离，变量不共享
4. **自动清理**: 过期会话自动清理，防止资源泄露

## 🔧 错误处理

### 常见错误与解决方案
- **导入错误**: 先使用`microsandbox_install_package`安装所需包
- **语法错误**: 检查Python代码语法的正确性
- **超时错误**: 优化代码逻辑或增加timeout参数
- **内存不足**: 减少数据集大小或优化算法

### 最佳实践
1. **代码组织**: 将复杂逻辑分解为多个小的执行块
2. **包管理**: 在执行代码前先安装所有需要的包
3. **会话复用**: 使用session_id在多次调用间保持变量状态
4. **资源监控**: 定期检查性能统计，避免资源耗尽