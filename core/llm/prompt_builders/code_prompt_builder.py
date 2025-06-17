import logging
from typing import Dict, Any, List
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class CodePromptBuilder(IPromptBuilder):
    """构建代码生成提示"""
    def build_prompt(self, description: str, language: str) -> List[Dict[str, Any]]:
        """构建代码生成提示，增强思考过程捕获"""
        prompt_content = f"""请根据以下描述生成{language}代码。

首先，详细思考如何解决这个问题，包括可能的算法、数据结构以及实现步骤。
在你的思考过程中，分析不同的解决方案并选择最佳方案。

描述：{description}

要求：
1. 先详细描述你的思考过程，包括你考虑的不同方法
2. 代码应该完整且可执行
3. 包含必要的注释
4. 处理可能的异常情况
5. 输出结果到控制台

==== 思考过程 ====
(请在这里详细写出你的思考过程，包括算法选择、数据结构、实现思路等)

==== 代码实现 ====
(在此处生成最终代码)
"""
        return [{"role": "user", "content": prompt_content}]