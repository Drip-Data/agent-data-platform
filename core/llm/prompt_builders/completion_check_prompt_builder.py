import logging
from typing import Dict, Any, List
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class CompletionCheckPromptBuilder(IPromptBuilder):
    """构建任务完成检查提示"""
    def build_prompt(self, task_description: str, steps: List[Dict], 
                                   current_outputs: List[str]) -> List[Dict[str, Any]]:
        """检查任务是否完成"""
        
        # 分析任务描述中的子任务
        sub_tasks = self._extract_sub_tasks(task_description)
        
        # 分析已执行的工具调用
        tool_calls = self._extract_tool_calls(steps)
        
        # 构建详细的步骤分析
        step_analysis = self._build_step_analysis(steps)
        
        prompt_content = f"""你是一个严格的任务完成度检查器。请仔细分析任务是否真正完成。

## 原始任务描述
{task_description}

## 识别的子任务
{self._format_sub_tasks(sub_tasks)}

## 已执行的工具调用记录
{self._format_tool_calls(tool_calls)}

## 执行步骤详细分析
{step_analysis}

## 当前所有输出内容
{self._format_outputs(current_outputs)}

## 检查要求
请逐一检查每个子任务是否完成：
1. 每个子任务是否有对应的工具调用？
2. 工具调用是否成功执行？
3. 是否产生了预期的输出结果？
4. 输出结果是否满足任务要求？

## 响应格式
请严格按照以下JSON格式回复：
{{
    "completed": boolean,
    "confidence": float (0.0-1.0),
    "reason": "详细的检查结果说明",
    "sub_task_status": [
        {{
            "task": "子任务描述",
            "completed": boolean,
            "tool_used": "使用的工具",
            "evidence": "完成证据"
        }}
    ],
    "missing_requirements": ["未完成的要求列表"]
}}

注意：只有当所有子任务都真正完成时，才能将completed设为true。"""

        return [{"role": "user", "content": prompt_content}]
    
    def _extract_sub_tasks(self, task_description: str) -> List[str]:
        """从任务描述中提取子任务"""
        sub_tasks = []
        
        # 查找明确的步骤标识符
        import re
        
        # 匹配 "先...然后...最后..." 模式
        step_patterns = [
            r'先(.+?)然后',
            r'然后(.+?)最后',
            r'最后(.+?)(?:\.|$)',
            r'第一步[:：](.+?)(?:\.|第二步|然后|$)',
            r'第二步[:：](.+?)(?:\.|第三步|最后|$)',
            r'第三步[:：](.+?)(?:\.|$)',
            r'1\.(.+?)(?:\.|2\.|$)',
            r'2\.(.+?)(?:\.|3\.|$)',
            r'3\.(.+?)(?:\.|$)'
        ]
        
        for pattern in step_patterns:
            matches = re.findall(pattern, task_description, re.IGNORECASE)
            for match in matches:
                task = match.strip()
                if task and len(task) > 5:  # 过滤太短的匹配
                    sub_tasks.append(task)
        
        # 如果没有找到明确的步骤，按句子分割
        if not sub_tasks:
            sentences = re.split(r'[。；;]', task_description)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 10:  # 只保留有意义的句子
                    sub_tasks.append(sentence)
        
        return sub_tasks[:5]  # 最多5个子任务
    
    def _extract_tool_calls(self, steps: List[Dict]) -> List[Dict]:
        """提取工具调用信息"""
        tool_calls = []
        
        for step in steps:
            if isinstance(step, dict):
                action_type = step.get('action_type', '')
                if 'TOOL_CALL' in str(action_type) or step.get('tool_id'):
                    tool_calls.append({
                        'tool_id': step.get('tool_id', 'unknown'),
                        'action': step.get('action', 'unknown'),
                        'success': step.get('success', False),
                        'observation': step.get('observation', '')[:200] + '...' if len(step.get('observation', '')) > 200 else step.get('observation', '')
                    })
        
        return tool_calls
    
    def _build_step_analysis(self, steps: List[Dict]) -> str:
        """构建步骤分析"""
        analysis = []
        
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                success_marker = "✅" if step.get('success') else "❌"
                step_type = step.get('action_type', 'unknown')
                observation = step.get('observation', '')[:150] + '...' if len(step.get('observation', '')) > 150 else step.get('observation', '')
                
                analysis.append(f"{success_marker} 步骤{i} ({step_type}): {observation}")
        
        return '\n'.join(analysis) if analysis else "无详细步骤记录"
    
    def _format_sub_tasks(self, sub_tasks: List[str]) -> str:
        """格式化子任务列表"""
        if not sub_tasks:
            return "未识别到明确的子任务"
        
        formatted = []
        for i, task in enumerate(sub_tasks, 1):
            formatted.append(f"{i}. {task}")
        
        return '\n'.join(formatted)
    
    def _format_tool_calls(self, tool_calls: List[Dict]) -> str:
        """格式化工具调用"""
        if not tool_calls:
            return "无工具调用记录"
        
        formatted = []
        for call in tool_calls:
            status = "✅ 成功" if call['success'] else "❌ 失败"
            formatted.append(f"- {call['tool_id']}.{call['action']} ({status})")
            if call['observation']:
                formatted.append(f"  输出: {call['observation']}")
        
        return '\n'.join(formatted)
    
    def _format_outputs(self, current_outputs: List[str]) -> str:
        """格式化输出内容"""
        if not current_outputs:
            return "无输出内容"
        
        formatted = []
        for i, output in enumerate(current_outputs, 1):
            # 限制每个输出的长度
            truncated = output[:300] + '...' if len(output) > 300 else output
            formatted.append(f"输出{i}: {truncated}")
        
        return '\n'.join(formatted)