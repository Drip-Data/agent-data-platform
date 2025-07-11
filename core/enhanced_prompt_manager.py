#!/usr/bin/env python3
"""
增强型提示管理器 - 集成共享工作区信息
解决工具间"信息孤岛"问题的关键组件
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from .shared_workspace import get_workspace_manager

logger = logging.getLogger(__name__)

class EnhancedPromptManager:
    """增强型提示管理器"""
    
    def __init__(self):
        self.workspace_manager = get_workspace_manager()
    
    def create_tool_integration_prompt(self, session_id: str, task_description: str) -> str:
        """创建工具集成提示，教导Agent如何使用共享工作区"""
        
        # 获取工作区状态
        workspace_context = self._get_workspace_context(session_id)
        
        prompt = f"""
🎯 **任务**: {task_description}

📁 **共享工作区使用指南**

你现在可以使用共享工作区来实现工具间的数据传递！这解决了以往工具间"信息孤岛"的问题。

**工作区状态**:
{workspace_context}

**重要使用原则**:

1. **数据传递流程**:
   - 使用 browser_use 获取数据时，数据会自动保存到共享工作区
   - 在 microsandbox 中执行代码时，会自动加载工作区中的数据
   - 所有工具都共享同一个会话工作区

2. **最佳实践**:
   ✅ **DO (推荐做法)**:
   ```
   # 第一步: 使用browser_use搜索数据
   <browser_use><browser_search_google>最新苹果股票价格</browser_search_google></browser_use>
   
   # 第二步: 在microsandbox中分析数据
   <microsandbox><microsandbox_execute>
   # 自动加载的browser_data变量包含了浏览器搜索的结果
   if browser_data:
       print("浏览器搜索结果:", browser_data['raw_content'])
       # 进行数据分析...
   </microsandbox_execute></microsandbox>
   ```
   
   ❌ **DON'T (避免做法)**:
   ```
   # 避免: 重复获取相同数据
   # 避免: 在microsandbox中重新模拟已有的真实数据
   ```

3. **工作区便利函数**:
   在 microsandbox 中可以直接使用以下函数:
   - `load_workspace_json(filename)` - 加载JSON数据
   - `load_workspace_text(filename)` - 加载文本数据  
   - `save_workspace_data(data, filename)` - 保存数据
   - `list_latest_browser_data()` - 列出浏览器数据
   - `browser_data` - 自动加载的最新浏览器结果

4. **会话管理**:
   - 会话ID: `{session_id}`
   - 同一个任务的所有工具调用都使用相同的会话ID
   - 工具间数据自动共享，无需手动传递

5. **数据格式说明**:
   - 浏览器结果保存为 `browser_result_*.json`
   - 提取的内容保存为 `extracted_content_*.txt`  
   - 分析结果可保存为 `analysis_result_*.json`

**示例工作流程**:

```
任务: 分析最新的科技新闻并生成报告

步骤1: 浏览器搜索
<browser_use><browser_search_google>最新科技新闻</browser_search_google></browser_use>

步骤2: 数据分析 (自动使用浏览器数据)
<microsandbox><microsandbox_execute>
# browser_data 已自动加载
if browser_data:
    content = browser_data['raw_content']
    # 分析新闻内容...
    analysis = {{
        "news_count": len(news_items),
        "key_topics": extract_topics(content),
        "summary": generate_summary(content)
    }}
    
    # 保存分析结果到工作区
    save_workspace_data(analysis, "news_analysis.json")
    print("✅ 分析完成并保存到工作区")
</microsandbox_execute></microsandbox>
```

现在开始执行任务，记住充分利用共享工作区来实现工具间的无缝数据传递！
"""
        
        return prompt
    
    def _get_workspace_context(self, session_id: str) -> str:
        """获取工作区上下文信息"""
        try:
            # 获取工作区路径
            workspace_path = self.workspace_manager.get_session_path(session_id)
            if not workspace_path:
                return f"- 会话 {session_id} 的工作区尚未创建\n- 首次使用工具时会自动创建"
            
            # 获取文件列表
            files = self.workspace_manager.list_session_files(session_id)
            
            context_lines = [
                f"- 会话ID: {session_id}",
                f"- 工作区路径: {workspace_path}",
                f"- 当前文件数量: {len(files)}"
            ]
            
            if files:
                context_lines.append("- 可用文件:")
                for file_info in files[:5]:  # 显示前5个文件
                    size_kb = file_info['size'] / 1024
                    context_lines.append(f"  • {file_info['name']} ({size_kb:.1f}KB, {file_info['extension']})")
                
                if len(files) > 5:
                    context_lines.append(f"  • ... 还有 {len(files) - 5} 个文件")
            else:
                context_lines.append("- 暂无文件 (工具执行后会自动创建)")
            
            return "\n".join(context_lines)
            
        except Exception as e:
            logger.error(f"获取工作区上下文失败: {e}")
            return f"- 工作区状态获取失败: {e}"
    
    def create_microsandbox_enhanced_prompt(self, session_id: str, original_code: str) -> str:
        """为MicroSandbox创建增强提示"""
        
        files = self.workspace_manager.list_session_files(session_id)
        browser_files = [f for f in files if 'browser' in f['name'].lower()]
        
        prompt = f"""
🔧 **代码执行增强提示**

你的代码将在增强的MicroSandbox环境中执行，该环境已自动配置了共享工作区访问：

**自动可用的变量和函数**:
- `WORKSPACE_PATH`: 工作区路径
- `AVAILABLE_FILES`: 可用文件列表 {[f['name'] for f in files]}
- `browser_data`: 自动加载的浏览器数据 {'(已加载)' if browser_files else '(暂无)'}

**便利函数**:
- `load_workspace_json(filename)`, `load_workspace_text(filename)`
- `save_workspace_data(data, filename, format='json')`
- `list_latest_browser_data()`

**你的代码**:
```python
{original_code}
```

执行时会自动添加工作区访问功能，你可以直接使用上述变量和函数。
"""
        return prompt
    
    def create_task_completion_summary(self, session_id: str, task_description: str) -> str:
        """创建任务完成总结"""
        
        try:
            files = self.workspace_manager.list_session_files(session_id)
            
            summary = f"""
📋 **任务完成总结**

**任务**: {task_description}
**会话ID**: {session_id}
**完成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**生成的文件** ({len(files)} 个):
"""
            
            if files:
                for file_info in files:
                    size_kb = file_info['size'] / 1024
                    summary += f"- {file_info['name']} ({size_kb:.1f}KB, {file_info['extension']})\n"
            else:
                summary += "- 无文件生成\n"
            
            summary += f"""
**工作区优势展示**:
✅ 实现了工具间数据无缝传递
✅ 避免了数据重复获取和模拟
✅ 提供了完整的执行历史记录
✅ 支持多种数据格式的存储和读取

工作区路径: {self.workspace_manager.get_session_path(session_id)}
"""
            
            return summary
            
        except Exception as e:
            logger.error(f"生成任务总结失败: {e}")
            return f"任务完成，但总结生成失败: {e}"


# 全局实例
_prompt_manager = None

def get_prompt_manager() -> EnhancedPromptManager:
    """获取全局提示管理器实例"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = EnhancedPromptManager()
    return _prompt_manager