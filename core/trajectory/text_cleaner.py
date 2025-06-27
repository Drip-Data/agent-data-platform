"""
轨迹文本清理器
Trajectory text cleaner for improved readability
"""

import re
import json
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class TrajectoryTextCleaner:
    """轨迹文本清理器"""
    
    def __init__(self):
        # 转义符映射 - 使用正确的正则表达式转义
        self.escape_patterns = [
            (r'\\n', '\n'),      # 匹配 \n 转为换行
            (r'\\t', '\t'),      # 匹配 \t 转为制表符
            (r'\\"', '"'),       # 匹配 \" 转为引号
            (r'\\r', '\r'),      # 匹配 \r 转为回车
            (r'\\\\', '\\'),     # 匹配 \\ 转为单个反斜杠
            (r'\\/', '/'),       # 匹配 \/ 转为斜杠
        ]
        
        # 常见的工具输出模式
        self.tool_output_patterns = [
            r'工具执行成功:\s*(.+)',
            r'Tool execution successful:\s*(.+)',
            r'Result:\s*(.+)',
            r'Output:\s*(.+)',
        ]
    
    def clean_llm_output(self, raw_output: str) -> str:
        """清理LLM原始输出"""
        if not raw_output:
            return ""
        
        # 1. 移除转义符
        cleaned = self._remove_escape_sequences(raw_output)
        
        # 2. 提取工具输出内容
        extracted = self._extract_tool_content(cleaned)
        
        # 3. 解析JSON内容
        json_content = self._extract_json_content(extracted)
        
        # 4. 格式化为可读文本
        final_content = self._format_readable_content(json_content or extracted)
        
        return final_content
    
    def clean_thinking_process(self, raw_thinking: str) -> Dict[str, str]:
        """清理和结构化thinking过程"""
        if not raw_thinking:
            return {}
        
        # 移除转义符
        cleaned = self._remove_escape_sequences(raw_thinking)
        
        # 解析步骤结构
        structured = self._parse_thinking_steps(cleaned)
        
        return structured
    
    def _remove_escape_sequences(self, text: str) -> str:
        """移除转义序列"""
        if not text:
            return text
            
        cleaned = text
        # 使用字符串替换而不是正则表达式来避免转义问题
        escape_mappings = {
            '\\n': '\n',      # 文字反斜杠n 转为换行
            '\\t': '\t',      # 文字反斜杠t 转为制表符
            '\\"': '"',       # 文字反斜杠引号 转为引号
            '\\r': '\r',      # 文字反斜杠r 转为回车
            '\\\\': '\\',     # 文字反斜杠反斜杠 转为单个反斜杠
            '\\/': '/',       # 文字反斜杠斜杠 转为斜杠
        }
        
        for escape_seq, replacement in escape_mappings.items():
            cleaned = cleaned.replace(escape_seq, replacement)
        
        return cleaned
    
    def _extract_tool_content(self, text: str) -> str:
        """提取工具输出内容"""
        for pattern in self.tool_output_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return text
    
    def _extract_json_content(self, text: str) -> Optional[str]:
        """提取JSON内容"""
        try:
            # 尝试直接解析
            if text.strip().startswith('{'):
                parsed = json.loads(text)
                # 如果有answer字段，优先返回
                if isinstance(parsed, dict):
                    if 'answer' in parsed:
                        return parsed['answer']
                    elif 'content' in parsed:
                        return parsed['content']
                    elif 'result' in parsed:
                        return parsed['result']
            
            # 查找JSON块
            json_pattern = r'\{.*\}'
            match = re.search(json_pattern, text, re.DOTALL)
            if match:
                json_str = match.group(0)
                # 先尝试将单引号替换为双引号
                json_str = json_str.replace("'", '"')
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    if 'answer' in parsed:
                        return parsed['answer']
                    elif 'content' in parsed:
                        return parsed['content']
                        
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Failed to parse JSON content: {e}")
        
        return None
    
    def _format_readable_content(self, content: str) -> str:
        """格式化为可读内容"""
        if not content:
            return ""
        
        # 移除多余的空行
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # 确保段落间有适当的间距
        content = re.sub(r'([.!?])\s*\n([A-Z])', r'\1\n\n\2', content)
        
        # 清理开头和结尾的空白
        content = content.strip()
        
        return content
    
    def _parse_thinking_steps(self, thinking_text: str) -> Dict[str, str]:
        """解析thinking步骤"""
        structured = {}
        
        # 查找STEP模式 - 修正正则表达式
        step_pattern = r'STEP\s+(\d+)\s*[-:]\s*([^:]+):\s*(.+?)(?=STEP\s+\d+|$)'
        matches = re.findall(step_pattern, thinking_text, re.DOTALL | re.IGNORECASE)
        
        for step_num, step_name, step_content in matches:
            key = f"step_{step_num}_{step_name.strip().lower().replace(' ', '_').replace('-', '_')}"
            structured[key] = step_content.strip()
        
        # 如果没有找到STEP模式，尝试其他模式
        if not structured:
            # 查找numbered patterns (1., 2., etc.)
            numbered_pattern = r'(\d+)\.\s*([^\n]+)\n(.+?)(?=\d+\.|$)'
            matches = re.findall(numbered_pattern, thinking_text, re.DOTALL)
            
            for num, title, content in matches:
                key = f"point_{num}_{title.strip().lower().replace(' ', '_')[:20]}"
                structured[key] = content.strip()
        
        # 如果仍然没有结构，作为整体保存
        if not structured:
            structured['full_thinking'] = thinking_text
        
        return structured

class TrajectoryMarkdownFormatter:
    """轨迹Markdown格式化器"""
    
    def __init__(self):
        self.text_cleaner = TrajectoryTextCleaner()
    
    def format_step_as_markdown(self, step_data: Dict[str, Any], step_number: int) -> str:
        """将步骤格式化为Markdown"""
        
        # 清理数据
        thinking = step_data.get('thinking', '')
        tool_output = step_data.get('tool_output', '')
        execution_code = step_data.get('execution_code', '')
        
        # 清理输出
        cleaned_output = self.text_cleaner.clean_llm_output(tool_output)
        structured_thinking = self.text_cleaner.clean_thinking_process(thinking)
        
        # 构建Markdown
        markdown_parts = []
        
        # 标题
        action_type = step_data.get('action_type', 'unknown')
        tool_id = self._extract_tool_id(step_data.get('tool_input', {}))
        action = self._extract_action(step_data.get('tool_input', {}))
        
        markdown_parts.append(f"## Step {step_number}: {action_type.replace('_', ' ').title()}")
        
        if tool_id and action:
            markdown_parts.append(f"**Tool**: `{tool_id}` | **Action**: `{action}`")
        
        # 推理过程
        if structured_thinking:
            markdown_parts.append("### 🧠 Reasoning Process")
            for key, value in structured_thinking.items():
                clean_key = key.replace('_', ' ').title()
                markdown_parts.append(f"- **{clean_key}**: {value}")
        
        # 执行细节
        if execution_code:
            try:
                exec_data = json.loads(execution_code)
                markdown_parts.append("### ⚙️ Execution Details")
                markdown_parts.append("```json")
                markdown_parts.append(json.dumps(exec_data, indent=2, ensure_ascii=False))
                markdown_parts.append("```")
            except:
                pass
        
        # 性能指标
        duration = step_data.get('duration', 0)
        success = step_data.get('success', True)
        
        markdown_parts.append("### 📊 Performance")
        markdown_parts.append(f"- **Duration**: {duration:.2f}s")
        markdown_parts.append(f"- **Status**: {'✅ Success' if success else '❌ Failed'}")
        
        # 结果
        if cleaned_output:
            markdown_parts.append("### 📝 Result")
            # 限制输出长度
            if len(cleaned_output) > 2000:
                markdown_parts.append(f"{cleaned_output[:2000]}...\n\n*[Content truncated for readability]*")
            else:
                markdown_parts.append(cleaned_output)
        
        return "\n\n".join(markdown_parts)
    
    def format_trajectory_summary(self, trajectory_data: Dict[str, Any]) -> str:
        """格式化轨迹摘要"""
        
        task_name = trajectory_data.get('task_name', 'Unknown Task')
        task_description = trajectory_data.get('task_description', '')
        success = trajectory_data.get('success', False)
        total_duration = trajectory_data.get('total_duration', 0)
        steps = trajectory_data.get('steps', [])
        
        summary_parts = []
        
        # 任务信息
        summary_parts.append(f"# 🎯 Task Execution: {task_name}")
        summary_parts.append(f"**Description**: {task_description}")
        summary_parts.append(f"**Status**: {'✅ Success' if success else '❌ Failed'}")
        summary_parts.append(f"**Duration**: {total_duration:.2f}s")
        summary_parts.append(f"**Steps**: {len(steps)}")
        
        # 统计信息
        successful_steps = sum(1 for step in steps if step.get('success', True))
        summary_parts.append(f"**Success Rate**: {successful_steps}/{len(steps)} ({successful_steps/len(steps)*100:.1f}%)")
        
        return "\n\n".join(summary_parts)
    
    def _extract_tool_id(self, tool_input: Dict[str, Any]) -> str:
        """提取工具ID"""
        return tool_input.get('_tool_id', tool_input.get('tool_id', ''))
    
    def _extract_action(self, tool_input: Dict[str, Any]) -> str:
        """提取动作"""
        return tool_input.get('_action', tool_input.get('action', ''))