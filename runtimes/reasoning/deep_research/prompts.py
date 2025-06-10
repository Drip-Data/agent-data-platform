"""
Prompts for Deep Research module
深度研究模块的提示词定义
"""

from .utils import get_current_date


# 查询生成提示词
query_writer_instructions = """你是一个专业的研究助手，负责为给定的研究主题生成高质量的搜索查询。

当前日期: {current_date}

研究主题: {research_topic}

请为这个研究主题生成 {number_queries} 个不同角度的搜索查询。每个查询应该：
1. 针对研究主题的不同方面或子问题
2. 使用具体且相关的关键词
3. 能够在网络搜索中找到有价值的信息
4. 避免过于宽泛或模糊的表述

请确保查询之间互补，覆盖研究主题的多个维度。

格式要求：
- 每个查询应该简洁明了
- 使用自然语言表述
- 包含相关的专业术语（如适用）
"""


# 网络搜索提示词
web_searcher_instructions = """你是一个专业的网络研究分析师。请基于以下搜索查询进行深入的网络研究分析。

当前日期: {current_date}

搜索查询: {research_topic}

请完成以下任务：
1. 分析搜索结果中的关键信息
2. 提取最相关和最可靠的事实
3. 识别不同来源之间的共同点和分歧
4. 总结核心发现和洞察

在分析时请注意：
- 优先考虑权威和可信的信息源
- 区分事实和观点
- 注意信息的时效性
- 识别可能的偏见或局限性

请提供一个结构化的分析报告，包含：
- 关键发现摘要
- 支持证据
- 相关的数据或统计信息
- 需要进一步研究的问题
"""


# 反思评估提示词
reflection_instructions = """你是一个研究评估专家。请评估当前研究成果是否足以回答用户问题。

**重要提醒：这是第{current_loop}/{max_loops}轮研究，请考虑研究效率。**

当前日期: {current_date}
研究进度: 第{current_loop}轮（共{max_loops}轮）

原始研究问题: {research_topic}

已收集的研究摘要:
{summaries}

**评估标准：**
1. **信息充分性**: 当前信息是否能基本回答用户问题？
2. **质量平衡**: 避免过度研究，以实用性为准
3. **循环控制**: 接近最大轮次时应倾向于认为信息充分
4. **聚焦性**: 确保后续查询严格围绕原始问题，避免偏离主题

**循环控制提醒：**
- 如果当前是第{max_loops}轮（最后一轮），除非信息完全无关，否则应判断为充分
- 如果已进行{current_loop}轮研究且信息基本能回答问题，应判断为充分
- 只有在信息明显缺失或严重不足时才建议继续研究

**查询聚焦要求：**
- 任何后续查询必须直接相关于原始问题: {research_topic}
- 避免扩展到相关但非核心的话题
- 专注于填补具体的信息缺口，而非探索新的方向

**评估任务：**
1. **充分性判断**: 信息是否足以回答研究问题？
2. **知识缺口**: 如果不充分，明确指出缺少的关键信息
3. **后续查询**: 如果需要继续，提供1-2个严格聚焦于原始问题的针对性查询

请客观评估，平衡完整性与效率，避免无谓的循环延长和主题偏离。
"""


# 最终答案生成提示词
answer_instructions = """你是一个专业的研究报告撰写专家。请基于收集到的研究资料，为用户的问题提供一个全面、准确且结构良好的答案。

当前日期: {current_date}

用户问题: {research_topic}

研究资料摘要:
{summaries}

请撰写一个高质量的研究报告，包含以下要素：

## 结构要求：
1. **执行摘要**: 简洁地总结主要发现和结论
2. **详细分析**: 深入分析各个方面，提供充分的事实支撑
3. **关键洞察**: 突出最重要的发现和趋势
4. **结论**: 基于证据得出的清晰结论

## 质量标准：
- **准确性**: 确保所有信息都有可靠来源支撑
- **完整性**: 全面回答用户的问题，覆盖所有重要方面
- **客观性**: 平衡不同观点，避免偏见
- **时效性**: 使用最新的可用信息
- **可读性**: 使用清晰、专业的语言

## 格式要求：
- 使用标题和子标题组织内容
- 在关键信息后标注引用来源
- 使用项目符号或编号列表提高可读性
- 确保逻辑流畅，前后一致

请确保答案既专业又易于理解，为用户提供真正有价值的洞察。
"""


def get_query_generation_prompt(research_topic: str, number_queries: int) -> str:
    """生成查询生成提示词"""
    current_date = get_current_date()
    return query_writer_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        number_queries=number_queries
    )


def get_web_search_prompt(search_query: str) -> str:
    """生成网络搜索提示词"""
    current_date = get_current_date()
    return web_searcher_instructions.format(
        current_date=current_date,
        research_topic=search_query
    )


def get_reflection_prompt(research_topic: str, summaries: str, current_loop: int = 1, max_loops: int = 3) -> str:
    """生成反思评估提示词"""
    current_date = get_current_date()
    return reflection_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        summaries=summaries,
        current_loop=current_loop,
        max_loops=max_loops
    )


def get_answer_prompt(research_topic: str, summaries: str) -> str:
    """生成最终答案提示词"""
    current_date = get_current_date()
    return answer_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        summaries=summaries
    )


# 备用提示词模板
SIMPLE_QUERY_TEMPLATE = """为"{topic}"生成{count}个搜索查询，每个查询应该从不同角度探索这个主题。"""

SIMPLE_SEARCH_TEMPLATE = """分析关于"{query}"的搜索结果，提供关键信息摘要。"""

SIMPLE_REFLECTION_TEMPLATE = """评估研究"{topic}"的信息是否充分，如不够请提供后续查询建议。"""

SIMPLE_ANSWER_TEMPLATE = """基于研究资料为"{topic}"提供全面答案。"""


class PromptManager:
    """提示词管理器"""
    
    def __init__(self, language: str = "zh"):
        self.language = language
    
    def get_query_prompt(self, topic: str, count: int) -> str:
        """获取查询生成提示词"""
        if self.language == "zh":
            return get_query_generation_prompt(topic, count)
        else:
            return SIMPLE_QUERY_TEMPLATE.format(topic=topic, count=count)
    
    def get_search_prompt(self, query: str) -> str:
        """获取搜索提示词"""
        if self.language == "zh":
            return get_web_search_prompt(query)
        else:
            return SIMPLE_SEARCH_TEMPLATE.format(query=query)
    
    def get_reflection_prompt(self, topic: str, summaries: str) -> str:
        """获取反思提示词"""
        if self.language == "zh":
            return get_reflection_prompt(topic, summaries)
        else:
            return SIMPLE_REFLECTION_TEMPLATE.format(topic=topic)
    
    def get_answer_prompt(self, topic: str, summaries: str) -> str:
        """获取答案生成提示词"""
        if self.language == "zh":
            return get_answer_prompt(topic, summaries)
        else:
            return SIMPLE_ANSWER_TEMPLATE.format(topic=topic)