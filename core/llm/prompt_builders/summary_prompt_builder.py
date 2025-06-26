import logging
from typing import Dict, Any, List
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class SummaryPromptBuilder(IPromptBuilder):
    """构建任务执行总结提示"""
    def build_prompt(self, task_description: str, steps: List[Dict], 
                                   final_outputs: List[str]) -> List[Dict[str, Any]]:
        """生成任务执行总结"""
        step_descriptions = []
        for step in steps:
            if isinstance(step, dict):
                desc = step.get('description') or step.get('observation') or step.get('action_type', 'Unknown step')
                step_descriptions.append(str(desc))
            else:
                step_descriptions.append(str(step))
        
        prompt_content = f"""请根据以下描述生成任务执行总结：

任务描述：{task_description}

步骤：
{'; '.join(step_descriptions)}

最终输出：{'; '.join(final_outputs[:3])}
"""
        return [{"role": "user", "content": prompt_content}]