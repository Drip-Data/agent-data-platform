# Agent Data Platform 开发者指南

## 如何开发和注册新工具

1. 在 `tools/` 目录下新建一个 Python 文件，例如 `my_hello_tool.py`
2. 实现 `core.interfaces.LocalToolInterface` 接口，或使用 `@tool_function` 装饰器注册函数。

### 示例：类方式
```python
from core.interfaces import LocalToolInterface, LocalToolSpec

class HelloWorldTool(LocalToolInterface):
    @property
    def tool_spec(self):
        return LocalToolSpec(
            tool_id="hello_world",
            name="Hello World 工具",
            description="返回 Hello World!",
            actions=[{"name": "say_hello", "description": "输出Hello World", "parameters": {}}],
            type="function"
        )
    async def execute(self, action, parameters):
        if action == "say_hello":
            return {"success": True, "result": "Hello World!"}
        return {"success": False, "error": "未知动作"}
    async def shutdown(self):
        pass
```

### 示例：函数方式
```python
from core.toolscore.tool_registry import tool_function

@tool_function(name="HelloFunc", description="Hello函数工具")
def hello_func():
    return {"success": True, "result": "Hello from function!"}
```

3. 保存后重启 main.py，工具会自动被注册。

## 工具调试建议
- 可用 pytest 对工具单独测试
- 日志输出可在 core/logging_service.py 配置

## 其他开发建议
- 所有新依赖请写入 requirements.txt
- 推理引擎扩展请参考 runtimes/reasoning/runtime.py

---
如有问题欢迎提Issue或PR！
