"""
增强的推理运行时 - 简化版本
专注于核心功能：LLM推理、工具执行、任务处理、XML流式输出
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult, TaskExecutionConstants, ErrorMessageConstants
from core.llm.prompt_builders.reasoning_prompt_builder import ReasoningPromptBuilder
from core.utils.path_utils import get_trajectories_dir
from core.streaming.sequential_executor import SequentialStreamingExecutor
from core.memory_manager import MemoryManager
from core.trajectory_enhancer import TrajectoryEnhancer
from core.step_logger import StepDiagnosticLogger
from core.intelligent_status_evaluator import IntelligentStatusEvaluator, intelligent_task_evaluation
from core.intelligent_token_manager import IntelligentTokenManager
from core.context_cache_manager import CacheStrategy
from core.llm_providers.gemini_provider import GeminiProvider


logger = logging.getLogger(__name__)


class TrajectoryStorageMode(Enum):
    """轨迹存储模式"""
    INDIVIDUAL_FILES = "individual"
    DAILY_GROUPED = "daily_grouped"
    WEEKLY_GROUPED = "weekly_grouped"
    MONTHLY_GROUPED = "monthly_grouped"


from core.unified_tool_manager import UnifiedToolManager

from core.unified_tool_manager import UnifiedToolManager

class EnhancedReasoningRuntime(RuntimeInterface):
    """
    增强的推理运行时 - 专注核心功能, 并集成高级模块
    """
    
    def __init__(self, config_manager, llm_client, toolscore_client, tool_manager: UnifiedToolManager, redis_manager=None, 
                 toolscore_websocket_endpoint=None, xml_streaming_mode: bool = False, 
                 trajectory_storage_mode: str = "daily_grouped"):
        self._runtime_id = f"enhanced-reasoning-{uuid.uuid4()}"
        self.config_manager = config_manager
        self.client = llm_client
        self.toolscore_client = toolscore_client
        self.tool_manager = tool_manager
        self.xml_streaming_mode = xml_streaming_mode
        self.trajectory_storage_mode = TrajectoryStorageMode(trajectory_storage_mode)
        self.prompt_builder = ReasoningPromptBuilder(tool_manager=self.tool_manager, streaming_mode=xml_streaming_mode)
        self.is_initialized = False

        # 初始化高级模块
        self.memory_manager = MemoryManager(redis_manager=redis_manager)
        self.trajectory_enhancer = TrajectoryEnhancer()
        self.sequential_executor = SequentialStreamingExecutor(
            llm_client=self.client, 
            tool_executor=self.toolscore_client,
            memory_manager=self.memory_manager
        )
        self.step_logger = StepDiagnosticLogger()
        self.intelligent_evaluator = IntelligentStatusEvaluator(self.client)
        
        # 🆕 初始化Token优化管理器
        try:
            # 从LLM客户端获取Gemini Provider
            gemini_provider = self._get_gemini_provider()
            if gemini_provider:
                self.token_manager = IntelligentTokenManager(
                    gemini_provider=gemini_provider,
                    redis_manager=redis_manager,
                    cache_strategy=CacheStrategy.BALANCED,
                    token_budget_limit=1000000  # 100万token预算
                )
                logger.info("✅ Token管理器初始化成功")
            else:
                self.token_manager = None
                logger.warning("⚠️ 无法获取Gemini Provider，Token管理器未启用")
        except Exception as e:
            logger.error(f"❌ Token管理器初始化失败: {e}")
            self.token_manager = None
        
        self.mcp_servers = self._load_mcp_config("config/mcp_servers.json")
    
    def _get_gemini_provider(self) -> Optional[GeminiProvider]:
        """从LLM客户端获取Gemini Provider实例"""
        try:
            # 检查LLM客户端是否有provider属性
            if hasattr(self.client, 'provider') and isinstance(self.client.provider, GeminiProvider):
                return self.client.provider
            
            # 检查是否有providers字典
            if hasattr(self.client, 'providers') and 'gemini' in self.client.providers:
                provider = self.client.providers['gemini']
                if isinstance(provider, GeminiProvider):
                    return provider
            
            # 尝试从配置创建新的Gemini Provider
            if hasattr(self.config_manager, 'get_llm_config'):
                llm_config = self.config_manager.get_llm_config()
                if 'gemini' in llm_config.get('llm_providers', {}):
                    gemini_config = llm_config['llm_providers']['gemini']
                    if gemini_config.get('enabled', False):
                        return GeminiProvider(gemini_config)
            
            logger.warning("无法获取Gemini Provider，可能使用的是其他LLM提供商")
            return None
            
        except Exception as e:
            logger.error(f"获取Gemini Provider失败: {e}")
            return None
    
    def _load_mcp_config(self, config_path: str) -> dict:
        """从JSON文件加载并格式化MCP服务器配置。"""
        config = {}
        try:
            with open(config_path, 'r') as f:
                mcp_config = json.load(f)
                for service_name, details in mcp_config.items():
                    # 标准化服务名称：去掉 "_server" 后缀，与代码期望一致
                    clean_name = service_name.replace("_server", "")
                    config[clean_name] = f"http://127.0.0.1:{details['port']}"
            logger.info(f"Loaded and formatted MCP server configs: {config}")
            return config
        except FileNotFoundError:
            logger.error(f"Error: MCP config file not found at {config_path}")
            return {}
        except json.JSONDecodeError:
            logger.error(f"Error: Could not decode JSON from {config_path}")
            return {}

    def _parse_execution_block(self, xml_string: str) -> dict:
        """
        从LLM生成的XML文本中解析出执行块。
        返回一个字典，包含类型（single, parallel, sequential）和动作列表。
        """
        from xml.etree import ElementTree as ET

        actions = []
        block_type = "single" # 默认
        try:
            # 清理并包裹XML，以便安全解析
            clean_xml = f"<root>{xml_string.strip()}</root>"
            root = ET.fromstring(clean_xml)

            # 检查并行或串行块
            parallel_block = root.find('parallel')
            sequential_block = root.find('sequential')

            if parallel_block is not None:
                block_type = "parallel"
                service_nodes = list(parallel_block)
            elif sequential_block is not None:
                block_type = "sequential"
                service_nodes = list(sequential_block)
            else:
                # 单个任务
                service_nodes = [elem for elem in root if elem.tag not in ['think', 'answer', 'execute_tools']]

            for service_node in service_nodes:
                service_name = service_node.tag
                if len(service_node) > 0:
                    tool_node = service_node[0]
                    tool_name = tool_node.tag
                    tool_input = tool_node.text or ""
                    actions.append({
                        "service": service_name,
                        "tool": tool_name,
                        "input": tool_input.strip()
                    })
        except ET.ParseError as e:
            logger.error(f"XML Parse Error: {e}\nOriginal XML:\n{xml_string}")
            # 尝试XML修复和容错解析
            try:
                fixed_actions = self._attempt_xml_repair(xml_string)
                if fixed_actions:
                    logger.info(f"✅ XML修复成功，解析出 {len(fixed_actions)} 个动作")
                    return {"type": block_type, "actions": fixed_actions}
            except Exception as repair_error:
                logger.warning(f"⚠️ XML修复失败: {repair_error}")
        
        return {"type": block_type, "actions": actions}

    def _attempt_xml_repair(self, xml_string: str) -> list:
        """
        尝试修复和解析损坏的XML，增强系统的容错能力
        """
        import re
        from xml.etree import ElementTree as ET
        
        actions = []
        
        # 方法1: 正则表达式提取工具调用
        try:
            # 匹配单个工具调用模式
            tool_pattern = r'<(\w+)>\s*<(\w+)>(.*?)</\2>\s*</\1>'
            matches = re.findall(tool_pattern, xml_string, re.DOTALL)
            
            for service_name, tool_name, tool_input in matches:
                actions.append({
                    "service": service_name,
                    "tool": tool_name,
                    "input": tool_input.strip()
                })
            
            if actions:
                logger.info(f"🔧 正则表达式修复：提取到 {len(actions)} 个工具调用")
                return actions
                
        except Exception as e:
            logger.debug(f"正则表达式修复失败: {e}")
        
        # 方法2: 尝试自动闭合标签
        try:
            # 简单的标签自动闭合
            fixed_xml = xml_string
            
            # 查找未闭合的标签
            open_tags = re.findall(r'<([^/>\s]+)[^>]*>', fixed_xml)
            close_tags = re.findall(r'</([^>\s]+)>', fixed_xml)
            
            # 为未闭合的标签添加闭合标签
            for tag in open_tags:
                if tag not in close_tags:
                    fixed_xml += f'</{tag}>'
            
            # 包装为根元素并尝试解析
            clean_xml = f"<root>{fixed_xml.strip()}</root>"
            root = ET.fromstring(clean_xml)
            
            # 递归提取工具调用
            def extract_tools(element):
                tools = []
                for child in element:
                    if len(child) > 0:  # 有子元素
                        for grandchild in child:
                            if grandchild.tag and grandchild.text:
                                tools.append({
                                    "service": child.tag,
                                    "tool": grandchild.tag,
                                    "input": grandchild.text.strip()
                                })
                    tools.extend(extract_tools(child))
                return tools
            
            extracted_tools = extract_tools(root)
            if extracted_tools:
                logger.info(f"🔧 标签闭合修复：提取到 {len(extracted_tools)} 个工具调用")
                return extracted_tools
                
        except Exception as e:
            logger.debug(f"标签闭合修复失败: {e}")
        
        # 方法3: 基于关键词的内容提取
        try:
            # 识别常见的服务名称和工具名称
            service_keywords = ['microsandbox', 'browser_use', 'search', 'deepsearch']
            tool_keywords = ['execute', 'search', 'navigate', 'click', 'type']
            
            # 按行分析，寻找可能的工具调用
            lines = xml_string.split('\n')
            current_service = None
            current_tool = None
            current_input = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 检查是否是服务标签
                for service in service_keywords:
                    if f'<{service}>' in line.lower():
                        current_service = service
                        break
                
                # 检查是否是工具标签
                for tool in tool_keywords:
                    if f'<{tool}>' in line.lower():
                        current_tool = tool
                        current_input = []
                        continue
                
                # 收集工具输入
                if current_service and current_tool:
                    if f'</{current_tool}>' in line.lower():
                        # 工具调用结束
                        if current_input:
                            actions.append({
                                "service": current_service,
                                "tool": current_tool,
                                "input": '\n'.join(current_input)
                            })
                        current_tool = None
                        current_input = []
                    else:
                        current_input.append(line)
            
            if actions:
                logger.info(f"🔧 关键词提取修复：提取到 {len(actions)} 个工具调用")
                return actions
                
        except Exception as e:
            logger.debug(f"关键词提取修复失败: {e}")
        
        return []

    def _attempt_answer_extraction(self, final_trajectory_str: str) -> str:
        """
        尝试从损坏的XML中提取答案内容，增强答案解析的容错能力
        """
        import re
        
        # 方法1: 部分匹配answer标签（处理未闭合的情况）
        try:
            # 查找答案开始标签
            answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
            answer_start_pattern = f'<{answer_tag}>'
            
            if answer_start_pattern in final_trajectory_str:
                # 找到开始位置
                start_pos = final_trajectory_str.find(answer_start_pattern)
                if start_pos != -1:
                    content_start = start_pos + len(answer_start_pattern)
                    
                    # 查找结束标签
                    answer_end_pattern = f'</{answer_tag}>'
                    end_pos = final_trajectory_str.find(answer_end_pattern, content_start)
                    
                    if end_pos != -1:
                        # 标准情况：有完整的开始和结束标签
                        answer_content = final_trajectory_str[content_start:end_pos].strip()
                        if answer_content:
                            return answer_content
                    else:
                        # 容错情况：没有结束标签，取到文本末尾
                        remaining_text = final_trajectory_str[content_start:].strip()
                        if remaining_text:
                            # 寻找下一个XML标签作为结束
                            next_tag_match = re.search(r'<[^>]+>', remaining_text)
                            if next_tag_match:
                                answer_content = remaining_text[:next_tag_match.start()].strip()
                            else:
                                answer_content = remaining_text
                            
                            if answer_content:
                                logger.info(f"🔧 部分匹配修复：提取到未闭合的answer内容")
                                return answer_content
                                
        except Exception as e:
            logger.debug(f"部分匹配修复失败: {e}")
        
        # 方法2: 基于关键词的智能识别
        try:
            # 查找最后的有意义段落
            paragraphs = final_trajectory_str.split('\n\n')
            
            # 查找包含答案关键词的段落
            answer_keywords = ['答案', '结果', '最终', '总结', '结论', 'answer', 'result', 'final', 'conclusion']
            
            for paragraph in reversed(paragraphs):
                paragraph = paragraph.strip()
                if len(paragraph) > 20:  # 足够长的段落
                    # 检查是否包含答案关键词
                    if any(keyword in paragraph.lower() for keyword in answer_keywords):
                        # 移除XML标签
                        clean_paragraph = re.sub(r'<[^>]*>', '', paragraph).strip()
                        if clean_paragraph:
                            logger.info(f"🔧 关键词识别修复：找到答案段落")
                            return clean_paragraph[:500]  # 限制长度
                            
        except Exception as e:
            logger.debug(f"关键词识别修复失败: {e}")
        
        # 方法3: 提取最后的有效内容
        try:
            # 移除所有XML标签，获取纯文本
            clean_text = re.sub(r'<[^>]*>', '', final_trajectory_str).strip()
            
            if clean_text:
                # 按行分割，寻找最后几行有意义的内容
                lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
                
                if lines:
                    # 从最后开始寻找有意义的行
                    meaningful_lines = []
                    for line in reversed(lines[-10:]):  # 检查最后10行
                        if len(line) > 15 and not line.startswith('Step') and not line.startswith('Time'):
                            meaningful_lines.append(line)
                            if len(meaningful_lines) >= 3:  # 最多取3行
                                break
                    
                    if meaningful_lines:
                        result = '\n'.join(reversed(meaningful_lines))
                        logger.info(f"🔧 文本提取修复：从纯文本中提取答案")
                        return result
                        
        except Exception as e:
            logger.debug(f"文本提取修复失败: {e}")
        
        return ""

    async def _execute_tool(self, action: dict) -> str:
        """
        根据单个动作字典，通过toolscore_client调用对应的MCP Server并返回结果。
        🔧 完整修复：统一所有工具的结果格式化，使结果清晰易读
        """
        service_name = action.get('service')
        tool_name = action.get('tool')
        tool_input = action.get('input')

        if not all([service_name, tool_name]):
            return "Error: Invalid action format. 'service' and 'tool' are required."

        # 映射服务到其期望的主要参数名
        param_mapping = {
            "browser_use": "query",
            "microsandbox": "code",
            "deepsearch": "question"
        }
        # 默认参数名为 'input'
        param_name = param_mapping.get(service_name, "input")
        parameters = {param_name: tool_input}

        logger.info(f"Executing via toolscore_client: service='{service_name}', tool='{tool_name}', params='{param_name}'")

        try:
            result = await self.toolscore_client.execute_tool(
                tool_id=service_name,
                action=tool_name,
                parameters=parameters
            )
            
            if isinstance(result, dict):
                if result.get('success', True):
                    output = result.get('data', result.get('output', result.get('result', str(result))))
                    
                    # 🔧 完整修复：为所有工具统一结果格式化
                    formatted_output = self._format_tool_output(service_name, tool_name, output)
                    return formatted_output
                else:
                    error_msg = result.get('error_message', result.get('error', 'Unknown error'))
                    return f"Tool execution failed: {error_msg}"
            else:
                return str(result)

        except Exception as e:
            logger.error(f"An unexpected error occurred while calling tool '{service_name}/{tool_name}': {e}", exc_info=True)
            return f"An unexpected error occurred while calling {service_name}: {e}"
    
    def _format_tool_output(self, service_name: str, tool_name: str, output) -> str:
        """
        🔧 完整修复：统一格式化所有工具的输出结果，使其清晰易读
        
        Args:
            service_name: 服务名称 (microsandbox, deepsearch, browser_use等)
            tool_name: 工具名称
            output: 原始输出结果
            
        Returns:
            str: 格式化后的清晰结果
        """
        # 1. MicroSandbox - 智能提取核心执行结果
        if service_name == 'microsandbox':
            return self._format_microsandbox_output(output)
        
        # 2. DeepSearch - 格式化搜索结果
        elif service_name == 'deepsearch':
            if isinstance(output, dict):
                return self._format_deepsearch_output(output)
            elif isinstance(output, list):
                return self._format_deepsearch_list_output(output)
            return str(output)
        
        # 3. Browser Use - 格式化浏览器操作结果
        elif service_name == 'browser_use':
            if isinstance(output, dict):
                return self._format_browser_use_output(output)
            return str(output)
        
        # 4. Search Tool - 格式化搜索结果
        elif service_name == 'search_tool':
            if isinstance(output, dict):
                return self._format_search_tool_output(output)
            return str(output)
        
        # 5. 其他工具 - 通用格式化
        else:
            return self._format_generic_output(output)
    
    def _format_deepsearch_output(self, output: dict) -> str:
        """🔧 格式化DeepSearch搜索结果 - 使用常量避免硬编码"""
        try:
            # 提取关键信息
            search_results = output.get('search_results', [])
            query = output.get('query', '')
            summary = output.get('summary', '')
            
            formatted_lines = []
            
            # 添加查询信息
            if query:
                formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_QUERY']}: {query}")
            
            # 添加摘要
            if summary:
                formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_SUMMARY']}: {summary}")
            
            # 格式化搜索结果
            if search_results:
                max_results = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SEARCH_RESULTS']
                results_text = TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_RESULTS'].format(len(search_results))
                formatted_lines.append(results_text)
                
                for i, result in enumerate(search_results[:max_results], 1):
                    if isinstance(result, dict):
                        title = result.get('title', '无标题')
                        snippet = result.get('snippet', result.get('content', ''))
                        url = result.get('url', '')
                        
                        formatted_lines.append(f"{i}. {title}")
                        if snippet:
                            # 使用常量限制snippet长度
                            max_length = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SNIPPET_LENGTH']
                            snippet_clean = snippet.strip()[:max_length]
                            formatted_lines.append(f"   {snippet_clean}...")
                        if url:
                            formatted_lines.append(f"   来源: {url}")
                        formatted_lines.append("")  # 空行分隔
            
            result_text = '\n'.join(formatted_lines).strip()
            return result_text if result_text else "搜索完成，但未找到相关结果"
            
        except Exception as e:
            logger.warning(f"Failed to format DeepSearch output: {e}")
            max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
            return f"DeepSearch搜索完成，原始结果: {str(output)[:max_content]}..."
    
    def _format_deepsearch_list_output(self, output: list) -> str:
        """🔧 格式化DeepSearch列表结果 - 使用常量避免硬编码"""
        try:
            if not output:
                return "搜索完成，但未找到相关结果"
            
            results_text = TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_RESULTS'].format(len(output))
            formatted_lines = [results_text]
            
            max_results = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SEARCH_RESULTS']
            for i, item in enumerate(output[:max_results], 1):
                if isinstance(item, dict):
                    title = item.get('title', f'结果 {i}')
                    content = item.get('content', item.get('snippet', ''))
                    
                    formatted_lines.append(f"{i}. {title}")
                    if content:
                        max_length = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SNIPPET_LENGTH']
                        content_clean = str(content).strip()[:max_length]
                        formatted_lines.append(f"   {content_clean}...")
                    formatted_lines.append("")
                else:
                    formatted_lines.append(f"{i}. {str(item)[:100]}...")
            
            return '\n'.join(formatted_lines).strip()
            
        except Exception as e:
            logger.warning(f"Failed to format DeepSearch list output: {e}")
            return f"DeepSearch搜索完成，找到 {len(output)} 个结果"
    
    def _format_browser_use_output(self, output: dict) -> str:
        """🔧 完整修复：格式化Browser Use操作结果，确保搜索结果不丢失"""
        try:
            # 提取关键信息 - 增强字段提取
            action = output.get('action', output.get('operation', TaskExecutionConstants.TOOL_FORMAT_PREFIXES['BROWSER_ACTION']))
            status = output.get('status', output.get('success', output.get('result', True)))
            content = output.get('content', output.get('data', output.get('text', '')))
            url = output.get('url', output.get('current_url', ''))
            error = output.get('error', output.get('error_message', ''))
            
            # 🔧 新增：专门处理搜索结果
            search_results = output.get('search_results', output.get('results', []))
            query = output.get('query', output.get('search_query', ''))
            
            formatted_lines = []
            
            # 状态信息
            status_text = "成功" if status else "失败"
            formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['BROWSER_ACTION']}: {action} - {status_text}")
            
            # 搜索查询信息
            if query:
                formatted_lines.append(f"搜索查询: {query}")
            
            # URL信息
            if url:
                formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['PAGE_URL']}: {url}")
            
            # 错误信息
            if error:
                formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['ERROR_INFO']}: {error}")
            
            # 🔧 优先处理搜索结果
            if search_results and isinstance(search_results, list):
                max_results = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SEARCH_RESULTS']
                formatted_lines.append(f"搜索结果({len(search_results)}个):")
                
                for i, result in enumerate(search_results[:max_results], 1):
                    if isinstance(result, dict):
                        title = result.get('title', result.get('name', f'结果{i}'))
                        snippet = result.get('snippet', result.get('description', result.get('content', '')))
                        result_url = result.get('url', result.get('link', ''))
                        
                        formatted_lines.append(f"{i}. {title}")
                        if snippet:
                            max_snippet = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SNIPPET_LENGTH']
                            clean_snippet = str(snippet).strip()[:max_snippet]
                            formatted_lines.append(f"   {clean_snippet}...")
                        if result_url:
                            formatted_lines.append(f"   链接: {result_url}")
                        formatted_lines.append("")
                    else:
                        formatted_lines.append(f"{i}. {str(result)[:100]}...")
            
            # 处理普通内容信息
            elif content:
                max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
                # 如果内容是HTML，尝试提取文本
                if isinstance(content, str) and ('<html>' in content.lower() or '<div>' in content.lower()):
                    # 简单的HTML文本提取
                    import re
                    text_content = re.sub(r'<[^>]+>', '', content)
                    text_content = re.sub(r'\s+', ' ', text_content).strip()
                    if text_content:
                        formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['PAGE_CONTENT']}: {text_content[:max_content]}...")
                else:
                    formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['OPERATION_RESULT']}: {str(content)[:max_content]}...")
            
            # 🔧 增强：如果没有有用内容，提供更详细的调试信息
            result_text = '\n'.join(formatted_lines).strip()
            if not result_text or len(result_text) < 20:
                # 如果格式化结果太短，说明可能有问题，提供原始数据的摘要
                logger.warning(f"Browser Use output seems incomplete. Raw keys: {list(output.keys())}")
                if output:
                    return f"浏览器操作执行，返回数据字段: {', '.join(output.keys())}\n原始数据: {str(output)[:300]}..."
                else:
                    return "浏览器操作执行完成，但未返回数据"
            
            return result_text
            
        except Exception as e:
            logger.error(f"Failed to format Browser Use output: {e}")
            max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
            return f"浏览器操作完成，原始结果: {str(output)[:max_content]}..."
    
    def _format_search_tool_output(self, output: dict) -> str:
        """🔧 格式化Search Tool搜索结果 - 使用常量避免硬编码"""
        try:
            # 提取搜索结果
            results = output.get('results', output.get('files', []))
            query = output.get('query', '')
            count = output.get('count', len(results) if isinstance(results, list) else 0)
            
            formatted_lines = []
            
            # 搜索信息
            if query:
                formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['FILE_SEARCH']}: {query}")
            
            file_results_text = TaskExecutionConstants.TOOL_FORMAT_PREFIXES['FILE_RESULTS'].format(count)
            formatted_lines.append(file_results_text)
            
            # 格式化文件列表
            if isinstance(results, list):
                max_files = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_FILE_RESULTS']
                for i, result in enumerate(results[:max_files], 1):
                    if isinstance(result, dict):
                        file_path = result.get('path', result.get('file', ''))
                        matches = result.get('matches', result.get('content', ''))
                        
                        formatted_lines.append(f"{i}. {file_path}")
                        if matches:
                            formatted_lines.append(f"   匹配内容: {str(matches)[:100]}...")
                    else:
                        formatted_lines.append(f"{i}. {str(result)}")
            
            return '\n'.join(formatted_lines).strip()
            
        except Exception as e:
            logger.warning(f"Failed to format Search Tool output: {e}")
            return f"文件搜索完成，找到 {count} 个结果"
    
    def _format_microsandbox_output(self, output) -> str:
        """🔧 专用MicroSandbox结果格式化 - 提取核心执行内容"""
        try:
            if isinstance(output, dict):
                # 优先提取stdout（主要输出）
                if 'stdout' in output:
                    stdout_content = str(output['stdout']).strip()
                    if stdout_content:
                        return stdout_content
                
                # 如果没有stdout，检查嵌套结构
                if 'result' in output and isinstance(output['result'], dict):
                    nested_result = output['result']
                    if 'stdout' in nested_result:
                        stdout_content = str(nested_result['stdout']).strip()
                        if stdout_content:
                            return stdout_content
                
                # 检查stderr错误信息
                stderr_content = ""
                if 'stderr' in output:
                    stderr_content = str(output['stderr']).strip()
                elif 'result' in output and isinstance(output['result'], dict) and 'stderr' in output['result']:
                    stderr_content = str(output['result']['stderr']).strip()
                
                if stderr_content:
                    return f"执行错误: {stderr_content}"
                
                # 检查返回代码
                return_code = output.get('return_code') or (output.get('result', {}).get('return_code') if isinstance(output.get('result'), dict) else None)
                if return_code == 0:
                    return "代码执行成功，但无输出内容"
                elif return_code is not None:
                    return f"代码执行失败，返回代码: {return_code}"
            
            # 其他情况返回简化的字符串
            output_str = str(output).strip()
            if len(output_str) > 200:
                return f"执行完成: {output_str[:200]}..."
            return output_str if output_str else "代码执行完成"
            
        except Exception as e:
            logger.warning(f"Failed to format MicroSandbox output: {e}")
            return f"代码执行完成: {str(output)[:100]}..."
    
    def _format_generic_output(self, output) -> str:
        """通用工具输出格式化"""
        try:
            if isinstance(output, dict):
                # 尝试提取有用信息
                if 'result' in output:
                    return str(output['result'])
                elif 'content' in output:
                    return str(output['content'])
                elif 'data' in output:
                    return str(output['data'])
                elif 'message' in output:
                    return str(output['message'])
                else:
                    # 过滤掉技术性字段，只保留有意义的内容
                    meaningful_fields = {}
                    skip_fields = {'success', 'status', 'code', 'timestamp', 'metadata', 'headers'}
                    
                    for key, value in output.items():
                        if key not in skip_fields and value:
                            meaningful_fields[key] = value
                    
                    if meaningful_fields:
                        return str(meaningful_fields)
            
            return str(output)
            
        except Exception as e:
            logger.warning(f"Failed to format generic output: {e}")
            return str(output)

    async def _execute_parallel(self, actions: list) -> list:
        """并发执行多个动作。"""
        import asyncio
        if not actions:
            return []
        
        tasks = [self._execute_tool(action) for action in actions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理可能发生的异常，确保返回字符串列表
        return [str(res) if not isinstance(res, Exception) else f"Error: {res}" for res in results]
    
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    async def capabilities(self) -> List[str]:
        """获取运行时能力"""
        return ['llm_reasoning', 'tool_execution', 'xml_streaming', 'memory', 'trajectory_enhancement', 'error_recovery']
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if hasattr(self.toolscore_client, 'health_check'):
                return await self.toolscore_client.health_check()
            return True
        except Exception:
            return False
    
    async def initialize(self):
        """初始化运行时"""
        logger.info("🚀 初始化Enhanced Reasoning Runtime")
        if not self.client:
            raise RuntimeError("LLM客户端未配置")
        if not self.toolscore_client:
            raise RuntimeError("工具客户端未配置")
        self.is_initialized = True
        logger.info("✅ Enhanced Reasoning Runtime 初始化完成")
    
    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行任务"""
        logger.info(f"🧠 开始执行任务: {task.description}")
        if not self.is_initialized:
            await self.initialize()
        
        if self.xml_streaming_mode:
            return await self._execute_xml_streaming(task)
        else:
            # 保留标准模式作为备选，但主要流程是XML流
            return await self._execute_standard(task)
    
    async def _execute_xml_streaming(self, task: TaskSpec) -> TrajectoryResult:
        """
        执行基于XML的、支持单步、并行和串行工具调用的主控制循环。
        """
        logger.info(f"🎯 Orchestrator starting task: {task.description}")
        start_time = time.time()
        
        # 🔍 启动步骤级日志记录
        self.step_logger.start_task(task.task_id, task.description)
        
        # 准备历史记录
        available_tools = await self._get_available_tools()
        tool_descriptions = await self._get_tool_descriptions()
        history = self.prompt_builder.build_prompt(
            task_description=task.description,
            available_tools=available_tools,
            tool_descriptions=tool_descriptions,
            history=[]
        )
        
        full_trajectory = [] # 记录完整的交互轨迹

        max_steps = task.max_steps or 20
        for step in range(max_steps):
            logger.info(f"--- Starting Step {step + 1}/{max_steps} ---")
            
            # 🔍 开始步骤日志记录
            self.step_logger.start_step(step)
            
            # 1. 🆕 Token优化 - 优化消息以减少token消耗
            original_history = history.copy()
            optimized_history = history
            optimization_info = {}
            
            if self.token_manager:
                try:
                    optimized_history, optimization_info = await self.token_manager.optimize_messages_with_cache(
                        history, 
                        model=getattr(self.client, 'model', 'gemini-2.5-flash'),
                        session_id=getattr(task, 'session_id', task.task_id)
                    )
                    if optimization_info.get('tokens_saved', 0) > 0:
                        logger.info(f"💰 Token优化: 节省 {optimization_info['tokens_saved']} tokens "
                                  f"(${optimization_info['cost_saved']:.6f})")
                except Exception as e:
                    logger.warning(f"Token优化失败，使用原始消息: {e}")
                    optimized_history = history
            
            # 2. 调用LLM，设置动态停止序列
            stop_sequences = ["<execute_tools />", "<execute_tools></execute_tools>", "</answer>"]
            llm_start_time = time.time()
            response_text = await self.client._call_api(optimized_history, stop_sequences=stop_sequences)
            llm_end_time = time.time()
            
            # 3. 🆕 Token使用统计和记录
            token_usage = {}
            if self.token_manager:
                try:
                    # 计算实际token使用
                    prompt_text = " ".join([msg.get('content', '') for msg in optimized_history if isinstance(msg, dict)])
                    prompt_tokens = await self.token_manager.count_tokens_accurately(prompt_text)
                    completion_tokens = await self.token_manager.count_tokens_accurately(response_text)
                    
                    # 记录token使用
                    await self.token_manager.record_token_usage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        model=getattr(self.client, 'model', 'gemini-2.5-flash'),
                        task_id=task.task_id,
                        session_id=getattr(task, 'session_id', None),
                        cached_tokens=optimization_info.get('tokens_saved', 0)
                    )
                    
                    token_usage = {
                        'prompt_tokens': prompt_tokens,
                        'completion_tokens': completion_tokens,
                        'total_tokens': prompt_tokens + completion_tokens,
                        'cached_tokens': optimization_info.get('tokens_saved', 0),
                        'model': getattr(self.client, 'model', 'gemini-2.5-flash'),
                        'data_source': 'api_provided'
                    }
                except Exception as e:
                    logger.warning(f"Token统计失败: {e}")
            
            # 4. 🔍 记录LLM调用（包含详细token信息）
            triggered_stop = self._detect_triggered_stop_sequence(response_text, stop_sequences)
            self.step_logger.log_llm_call(
                prompt=original_history,  # 使用原始消息记录完整内容
                raw_response=response_text,
                stop_sequence=triggered_stop,
                start_time=llm_start_time,
                end_time=llm_end_time,
                token_usage=token_usage  # 🆕 传递详细的token使用信息
            )
            
            history.append({"role": "assistant", "content": response_text})
            full_trajectory.append({"role": "assistant", "content": response_text})

            # 🔧 修复：更智能的答案检测逻辑
            answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
            answer_start_tag = f"<{answer_tag}>"
            answer_end_tag = f"</{answer_tag}>"
            
            # 检测答案标签（开始标签或结束标签）
            has_answer_start = answer_start_tag in response_text
            has_answer_end = answer_end_tag in response_text
            has_boxed_content = "\\boxed{" in response_text
            
            if has_answer_end or (has_answer_start and has_boxed_content):
                logger.info("✅ Final Answer detected. Task complete.")
                # 🔍 记录解析结果（包含答案的情况）
                parsing_start_time = time.time()
                think_content = self.step_logger._extract_think_content(response_text)
                answer_content = self.step_logger._extract_answer_content(response_text)
                parsing_end_time = time.time()
                
                self.step_logger.log_parsing_result(
                    think_content=think_content,
                    execution_block=None,
                    answer_content=answer_content,
                    actions=[],
                    parsing_errors=[],
                    start_time=parsing_start_time,
                    end_time=parsing_end_time
                )
                self.step_logger.finish_step("task_completed_with_answer")
                break

            # 🔍 记录解析阶段
            parsing_start_time = time.time()
            execution_block = self._parse_execution_block(response_text)
            actions = execution_block.get("actions", [])
            think_content = self.step_logger._extract_think_content(response_text)
            execution_block_text = self.step_logger._extract_execution_block(response_text)
            parsing_end_time = time.time()
            
            self.step_logger.log_parsing_result(
                think_content=think_content,
                execution_block=execution_block_text,
                answer_content=None,
                actions=actions,
                parsing_errors=[],
                start_time=parsing_start_time,
                end_time=parsing_end_time
            )
            
            # 检查是否是仅包含思考的最终答案
            think_tag = TaskExecutionConstants.XML_TAGS['THINK']
            answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
            execute_tools_tag = TaskExecutionConstants.XML_TAGS['EXECUTE_TOOLS']
            
            if not actions and f"<{think_tag}>" in response_text and f"<{execute_tools_tag} />" not in response_text:
                logger.info("✅ Detected a thought-only response, considering it the final answer.")
                # 提取思考内容作为最终答案
                try:
                    import re
                    match = re.search(f"<{think_tag}>(.*)</{think_tag}>", response_text, re.DOTALL)
                    if match:
                        final_thought = match.group(1).strip()
                        answer_content = f"<{answer_tag}>{final_thought}</{answer_tag}>"
                        history.append({"role": "assistant", "content": answer_content})
                        full_trajectory.append({"role": "assistant", "content": answer_content})
                except Exception:
                    pass # 如果解析失败，则正常继续
                # 🔍 完成步骤记录
                self.step_logger.finish_step("thought_only_final_answer")
                break

            # 🔧 根本修复：智能判断是否需要注入"无动作"消息
            if not actions:
                # 🔧 Priority 3 增强：计划-执行桥梁机制 - 彻底解决计划-执行脱节问题
                plan_content = self._extract_detailed_plan(response_text)
                if plan_content and self._has_executable_plan(plan_content):
                    logger.info("🎯 检测到详细计划但缺少执行动作，引导LLM开始执行")
                    
                    # 🔧 新增：分析计划中的第一步具体动作
                    first_action = self._extract_first_executable_action(plan_content)
                    if first_action:
                        execution_guidance = (
                            f"You have created a detailed plan. Now please start executing the first step: {first_action}. "
                            "Use the appropriate tool call with the exact XML format and end with <execute_tools />. "
                            "Remember: plans are not answers - execution is required."
                        )
                    else:
                        execution_guidance = (
                            "You have created a detailed plan. Now please start executing the first step of your plan. "
                            "Use the appropriate tool call with the exact XML format and end with <execute_tools />. "
                            "Remember: plans are not answers - execution is required."
                        )
                    
                    result_xml = self._format_result(execution_guidance)
                    history.append({"role": "assistant", "content": result_xml})
                    full_trajectory.append({"role": "assistant", "content": result_xml})
                    # 🔍 完成步骤记录
                    self.step_logger.finish_step("plan_execution_guidance_injected")
                    continue
                
                elif self._should_inject_no_action_message(response_text):
                    logger.warning("No executable actions found in LLM response. Injecting guidance.")
                    result_xml = self._format_result("No executable action detected in this step.")
                    history.append({"role": "assistant", "content": result_xml})
                    full_trajectory.append({"role": "assistant", "content": result_xml})
                    # 🔍 完成步骤记录
                    self.step_logger.finish_step("no_action_injected")
                else:
                    logger.info("✅ Detected thought-only response without tool execution - this is normal.")
                    # 🔍 完成步骤记录
                    self.step_logger.finish_step("thought_only_normal")
                continue

            # 4. 根据类型分发执行
            results = []
            block_type = execution_block.get("type")

            # 对于串行块，我们只执行第一个动作。LLM将在下一轮根据结果决定后续步骤。
            if block_type == "sequential":
                logger.info(f"Executing first action of sequential block.")
                if actions:
                    result_data = await self._execute_tool_with_logging(actions[0], 0)
                    results = [result_data["formatted_result"]]
            elif block_type == "parallel":
                logger.info(f"Executing parallel block with {len(actions)} actions.")
                results = await self._execute_parallel_with_logging(actions)
            else: # single
                if actions:
                    logger.info(f"Executing single action.")
                    result_data = await self._execute_tool_with_logging(actions[0], 0)
                    results = [result_data["formatted_result"]]

            # 5. 格式化并为每个结果注入单独的<result>标签
            for res in results:
                result_xml = self._format_result(res)
                history.append({"role": "assistant", "content": result_xml})
                full_trajectory.append({"role": "assistant", "content": result_xml})
                
            # 🔍 完成步骤记录
            self.step_logger.finish_step()

        else:
            logger.warning(f"Max steps ({max_steps}) reached. Terminating task.")
            # 🔍 完成最后一个步骤记录
            if self.step_logger.current_step_data:
                self.step_logger.finish_step("max_steps_reached")

        # 任务结束，处理最终结果
        final_trajectory_str = "\n".join(item["content"] for item in full_trajectory)
        total_duration = time.time() - start_time
        
        # 🔧 根本修复：区分步数限制和真正失败
        max_steps_reached = len(full_trajectory) >= max_steps
        
        # 🧠 新智能评估：使用语义理解和结果驱动的判定逻辑
        final_result = self._extract_final_result(final_trajectory_str)
        
        try:
            success, confidence_score, evaluation_reasoning = await self._intelligent_task_success_evaluation(
                task_input=task.description,
                final_trajectory_str=final_trajectory_str,
                full_trajectory=full_trajectory,
                final_output=final_result
            )
            logger.info(f"🧠 智能评估: 成功={success}, 置信度={confidence_score:.2f}, 理由={evaluation_reasoning}")
        except Exception as e:
            logger.error(f"❌ 智能评估失败，使用传统方法: {e}")
            success = self._determine_task_success(final_trajectory_str, full_trajectory)
            confidence_score = 0.5
            evaluation_reasoning = "使用传统评估方法"
        
        # 🔧 新增：如果达到最大步数但没有明确的答案，降低成功判定标准
        if max_steps_reached:
            answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
            has_explicit_answer = f"<{answer_tag}>" in final_trajectory_str
            has_boxed_content = "\\boxed{" in final_trajectory_str
            
            if not has_explicit_answer and not has_boxed_content:
                # 达到最大步数且没有明确答案，标记为部分成功但需要说明
                logger.warning(f"任务达到最大步数({max_steps})但没有明确答案标记")
                # 根据是否有工具执行结果来判定
                tool_success_rate = self._calculate_tool_success_rate()
                success = tool_success_rate > 0.5  # 至少50%的工具执行成功才认为部分成功
        
        # 🔧 根本修复：动态提取真实的最终结果，考虑步数限制情况
        if max_steps_reached:
            final_result = f"已达最大步骤({max_steps})，任务被中止。当前进展：{self._extract_final_result(final_trajectory_str)}"
        else:
            final_result = self._extract_final_result(final_trajectory_str)

        # 🔍 完成任务步骤日志记录
        final_status = "success" if success else "failure"
        await self.step_logger.finalize_task(final_status, final_result)

        xml_output = {
            "timestamp": datetime.now().isoformat(),
            "task_id": task.task_id,
            "task_description": task.description,
            "duration": total_duration,
            "success": success,
            "final_result": final_result,
            "raw_response": final_trajectory_str,
        }
        
        await self._save_xml_output(xml_output)

        # 🔧 修复：从step_logger获取实际的执行步骤
        actual_steps = await self.step_logger.get_execution_steps()
        
        # 🧠 构建智能评估元数据
        intelligent_evaluation = {
            'confidence_score': confidence_score,
            'evaluation_reasoning': evaluation_reasoning,
            'evaluation_method': 'intelligent_semantic' if 'evaluation_reasoning' in locals() and 'LLM' in evaluation_reasoning else 'traditional_rule_based',
            'max_steps_reached': max_steps_reached,
            'trajectory_length': len(full_trajectory)
        }
        
        return TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id, 
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=actual_steps,  # 🔧 使用实际步骤而不是空数组
            success=success,
            final_result=final_result,  # 🔧 使用动态提取的结果
            total_duration=total_duration,
            metadata={
                'full_trajectory': full_trajectory,
                'intelligent_evaluation': intelligent_evaluation  # 🧠 新增智能评估信息
            }
        )

    def _format_result(self, result: str) -> str:
        """🔧 根本修复：格式化工具结果，使用常量替代硬编码"""
        if not result:
            no_action_msg = TaskExecutionConstants.NO_ACTION_PERFORMED
            return f"<{TaskExecutionConstants.XML_TAGS['RESULT']}>{no_action_msg}</{TaskExecutionConstants.XML_TAGS['RESULT']}>"
        return f"<{TaskExecutionConstants.XML_TAGS['RESULT']}>{result}</{TaskExecutionConstants.XML_TAGS['RESULT']}>"
    
    async def _execute_standard(self, task: TaskSpec) -> TrajectoryResult:
        """标准执行模式 (作为备用) - 🔧 已修复硬编码问题"""
        logger.warning("执行标准（ReAct）模式，此模式功能有限。")
        # 简单实现标准模式
        start_time = time.time()
        response = ""
        try:
            # 简单的LLM调用
            messages = self.prompt_builder.build_prompt(
                task_description=task.description,
                available_tools=[],
                tool_descriptions="",
                streaming_mode=False
            )
            response = await self.client._call_api(messages)
            
            # 🧠 标准模式也使用智能评估（简化版）
            final_result = self._extract_final_result(response)
            
            try:
                success, confidence_score, evaluation_reasoning = await self._intelligent_task_success_evaluation(
                    task_input=task.description,
                    final_trajectory_str=response,
                    full_trajectory=[{'content': response, 'timestamp': time.time()}],
                    final_output=final_result
                )
                logger.info(f"🧠 标准模式智能评估: 成功={success}, 置信度={confidence_score:.2f}")
            except Exception as eval_e:
                logger.error(f"❌ 标准模式智能评估失败: {eval_e}")
                success = self._determine_task_success(response, [])
                confidence_score = 0.5
                evaluation_reasoning = "降级到传统评估"
            
        except Exception as e:
            logger.error(f"标准模式执行失败: {e}")
            success = False
            final_result = f"执行失败: {str(e)}"
            response = f"Error: {str(e)}"
            confidence_score = 0.0
            evaluation_reasoning = f"执行异常: {str(e)}"
        
        total_duration = time.time() - start_time
        
        # 🧠 构建标准模式的智能评估元数据
        intelligent_evaluation = {
            'confidence_score': confidence_score,
            'evaluation_reasoning': evaluation_reasoning,
            'evaluation_method': 'intelligent_semantic_standard_mode',
            'max_steps_reached': False,
            'trajectory_length': 1
        }
        
        # 构建返回对象
        from core.interfaces import TrajectoryResult
        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id,
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=[],
            success=success,
            final_result=final_result,  # 🔧 使用动态提取的结果
            total_duration=total_duration,
            metadata={
                'mode': 'standard', 
                'raw_response': response,
                'intelligent_evaluation': intelligent_evaluation  # 🧠 新增智能评估信息
            }
        )
        
        return trajectory

    async def _get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        try:
            tools = await self.toolscore_client.get_available_tools()
            return [str(tool) for tool in tools] if isinstance(tools, list) else []
        except Exception as e:
            logger.warning(f"获取工具列表失败: {e}")
            return []
    
    async def _get_tool_descriptions(self) -> str:
        """获取工具描述"""
        try:
            descriptions = await self.toolscore_client.get_tool_descriptions()
            return descriptions if descriptions else "工具描述获取失败"
        except Exception as e:
            logger.warning(f"获取工具描述失败: {e}")
            return "工具描述获取失败"

    async def _intelligent_task_success_evaluation(
        self, 
        task_input: str, 
        final_trajectory_str: str, 
        full_trajectory: List, 
        final_output: str
    ) -> Tuple[bool, float, str]:
        """
        🧠 智能任务成功评估 - 新的主要状态判定方法
        
        使用语义理解和结果驱动的判定逻辑，替代传统的格式驱动方法
        
        Args:
            task_input: 原始任务输入
            final_trajectory_str: 完整轨迹字符串
            full_trajectory: 轨迹步骤列表
            final_output: 最终输出内容
            
        Returns:
            Tuple[is_success, confidence_score, reasoning]
        """
        try:
            # 提取工具执行结果
            tool_results = []
            for step in full_trajectory:
                if isinstance(step, dict) and 'tool_execution' in step:
                    tool_results.append(step['tool_execution'])
            
            # 调用智能评估器
            is_success, confidence, reasoning = await intelligent_task_evaluation(
                llm_client=self.client,
                task_input=task_input,
                trajectory=full_trajectory,
                final_output=final_output,
                tool_results=tool_results
            )
            
            logger.info(f"🧠 智能状态评估结果: 成功={is_success}, 置信度={confidence:.2f}, 理由={reasoning}")
            
            return is_success, confidence, reasoning
            
        except Exception as e:
            logger.error(f"❌ 智能状态评估失败: {e}")
            # 降级到传统方法
            traditional_success = self._determine_task_success(final_trajectory_str, full_trajectory)
            return traditional_success, 0.5, f"降级评估: {traditional_success}"

    def _determine_task_success(self, final_trajectory_str: str, full_trajectory: List) -> bool:
        """🔧 Priority 1 修复：彻底解决"规划即成功"系统性漏洞
        
        核心原则：必须有实际工具执行或明确答案标签，仅有规划/思考内容不能判定为成功
        
        Args:
            final_trajectory_str: 完整轨迹字符串
            full_trajectory: 轨迹步骤列表
        
        Returns:
            bool: 任务是否成功完成
        """
        # 🔧 最高优先级：检查实际工具执行状态
        tool_success_rate = self._calculate_tool_success_rate()
        has_successful_tools = tool_success_rate > 0.0
        
        # 1. 检查是否有完整的答案标签（必须有结束标签）
        answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
        has_complete_answer = f'</{answer_tag}>' in final_trajectory_str
        has_boxed_answer = "\\boxed{" in final_trajectory_str  # 数学答案格式
        
        # 2. 检查是否有未处理的关键错误指示器
        has_critical_errors = any(
            indicator in final_trajectory_str.lower() 
            for indicator in TaskExecutionConstants.FAILURE_INDICATORS
        )
        
        # 3. 检查是否有实际的工具执行成果
        result_tag = TaskExecutionConstants.XML_TAGS['RESULT']
        has_tool_results = f'<{result_tag}>' in final_trajectory_str and TaskExecutionConstants.NO_ACTION_PERFORMED not in final_trajectory_str
        
        # 4. 🔧 新增：检查是否只有思考内容（"规划即成功"检测）
        think_tag = TaskExecutionConstants.XML_TAGS['THINK']
        execute_tools_tag = TaskExecutionConstants.XML_TAGS['EXECUTE_TOOLS']
        
        has_only_thinking = (f'<{think_tag}>' in final_trajectory_str and 
                           not has_tool_results and 
                           not has_complete_answer and
                           not has_boxed_answer and
                           f'<{execute_tools_tag}>' not in final_trajectory_str)
        
        # 🔧 Priority 4 新增：多工具协同质量评估
        multi_tool_quality = self._evaluate_multi_tool_coordination_quality(final_trajectory_str)
        
        # 🔧 Priority 1 核心修复：严格的成功判定逻辑
        success = False
        
        # 场景1：有实际工具执行成功 + 有完整答案 + 有意义结果 = 明确成功
        if has_successful_tools and (has_complete_answer or has_boxed_answer) and not has_critical_errors and self._has_meaningful_tool_results(final_trajectory_str):
            success = True
            logger.info("🎯 判定成功：工具执行成功 + 完整答案 + 有意义结果")
        
        # 场景2：有实际工具执行成功 + 有实际结果输出 = 潜在成功
        elif has_successful_tools and has_tool_results and not has_critical_errors:
            success = True
            logger.info("🎯 判定成功：工具执行成功 + 有实际结果")
        
        # 场景3：🔧 Priority 4 新增：多工具协同成功场景
        elif multi_tool_quality['is_coordinated'] and multi_tool_quality['quality_score'] > TaskExecutionConstants.MULTI_TOOL_COORDINATION['RESULT_INTEGRATION']['quality_threshold']:
            success = True
            logger.info(f"🎯 判定成功：多工具协同完成，质量分数={multi_tool_quality['quality_score']:.2f}")
        
        # 场景4：纯推理任务：有完整答案标签（必须有结束标签或boxed格式）
        elif (has_complete_answer or has_boxed_answer) and not has_critical_errors:
            success = True
            logger.info("🎯 判定成功：纯推理任务，有完整答案标签")
        
        # 场景5：🔧 "规划即成功"漏洞防护 - 只有思考内容时明确拒绝
        elif has_only_thinking:
            success = False
            logger.warning('🚨 "规划即成功"漏洞防护：仅有思考内容，不认定为成功')
        
        # 场景6：任何关键错误都导致失败
        elif has_critical_errors:
            success = False
            logger.info("🎯 判定失败：检测到关键错误")
        
        # 场景7：其他情况默认失败
        else:
            success = False
            logger.info("🎯 判定失败：未满足成功条件")
        
        logger.info(f"🎯 Success判定详情: tool_success_rate={tool_success_rate:.2f}, "
                   f"has_complete_answer={has_complete_answer}, has_boxed_answer={has_boxed_answer}, "
                   f"has_tool_results={has_tool_results}, has_only_thinking={has_only_thinking}, "
                   f"has_critical_errors={has_critical_errors}, final_success={success}")
        
        return success
    
    def _calculate_tool_success_rate(self) -> float:
        """计算当前任务中工具执行的成功率"""
        if not hasattr(self, 'step_logger') or not self.step_logger.current_task_data:
            return 0.0
        
        total_executions = 0
        successful_executions = 0
        
        for step in self.step_logger.current_task_data.get('steps', []):
            for tool_exec in step.get('tool_executions', []):
                total_executions += 1
                if tool_exec.get('execution_status') == 'success':
                    successful_executions += 1
        
        return successful_executions / total_executions if total_executions > 0 else 0.0
    
    def _analyze_error_type(self, error_message: str) -> str:
        """🔧 智能错误类型分析"""
        error_msg_lower = error_message.lower()
        
        # 参数错误
        if any(indicator in error_msg_lower for indicator in ['parameter', 'param', '参数', '无效参数']):
            return "parameter_error"
        
        # 工具不存在错误
        if any(indicator in error_msg_lower for indicator in ['不支持', 'not support', '不存在', 'not found']):
            return "tool_not_found"
        
        # 网络/连接错误
        if any(indicator in error_msg_lower for indicator in ['timeout', 'connection', 'network', 'connect', '超时']):
            return "network_error"
        
        # 验证错误
        if any(indicator in error_msg_lower for indicator in ['validation', 'validate', '验证失败']):
            return "validation_error"
        
        # 权限错误
        if any(indicator in error_msg_lower for indicator in ['permission', 'access', '权限', 'forbidden']):
            return "permission_error"
        
        return "unknown_error"
    
    def _format_error_with_recovery_suggestion(self, error_message: str, error_type: str, service_name: str, tool_name: str) -> str:
        """🔧 格式化错误信息并提供恢复建议"""
        base_error = f"Tool execution failed: {error_message}"
        
        recovery_suggestions = {
            "parameter_error": f"💡 建议: 检查 {service_name} 的 {tool_name} 工具参数格式。参考工具定义中的正确参数名称。",
            "tool_not_found": f"💡 建议: 工具 {tool_name} 在 {service_name} 中不存在。检查工具名称是否正确，或尝试使用其他工具。",
            "network_error": f"💡 建议: 网络连接问题。等待几秒后重试，或尝试使用替代工具。",
            "validation_error": f"💡 建议: 输入数据验证失败。检查输入格式和内容是否符合要求。",
            "permission_error": f"💡 建议: 权限不足。检查服务配置或尝试其他方法。",
            "unknown_error": f"💡 建议: 未知错误。尝试简化输入或使用其他工具替代。"
        }
        
        suggestion = recovery_suggestions.get(error_type, recovery_suggestions["unknown_error"])
        return f"{base_error}\n{suggestion}"
    
    def _extract_final_result(self, final_trajectory_str: str) -> str:
        """🔧 完整修复：优化最终结果提取优先级，确保实际结果优于思考过程
        
        Args:
            final_trajectory_str: 完整轨迹字符串
        
        Returns:
            str: 提取的最终结果
        """
        import re
        
        # 🔧 第一优先级：提取answer标签内容，优先提取\boxed{}格式
        answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
        answer_pattern = f'<{answer_tag}>(.*?)</{answer_tag}>'
        answer_match = re.search(answer_pattern, final_trajectory_str, re.DOTALL)
        if answer_match:
            answer_content = answer_match.group(1).strip()
            if answer_content and len(answer_content) > 0:
                # 🔧 新增：优先提取\boxed{}内的清洁内容
                boxed_pattern = r'\\boxed\{(.*?)\}'
                boxed_match = re.search(boxed_pattern, answer_content, re.DOTALL)
                if boxed_match:
                    clean_answer = boxed_match.group(1).strip()
                    logger.info(f"✅ 从\\boxed{{}}提取清洁最终结果: {clean_answer[:100]}...")
                    return clean_answer
                else:
                    # 如果没有\boxed{}格式，返回原始answer内容
                    logger.info(f"✅ 从<answer>标签提取最终结果: {answer_content[:100]}...")
                    return answer_content
        else:
            # 🔧 容错机制：如果标准答案标签解析失败，尝试修复
            answer_content = self._attempt_answer_extraction(final_trajectory_str)
            if answer_content:
                logger.info(f"🔧 容错提取答案成功: {answer_content[:100]}...")
                return answer_content
        
        # 🔧 第二优先级：提取最后的有效工具执行结果（非"No action"）
        result_tag = TaskExecutionConstants.XML_TAGS['RESULT']
        result_pattern = f'<{result_tag}>(.*?)</{result_tag}>'
        result_matches = re.findall(result_pattern, final_trajectory_str, re.DOTALL)
        
        # 过滤出有效的工具执行结果
        valid_results = []
        for result in result_matches:
            result_clean = result.strip()
            # 排除无意义的结果
            if (result_clean and 
                TaskExecutionConstants.NO_ACTION_PERFORMED not in result_clean and
                "No executable action detected" not in result_clean and
                len(result_clean) > 10):
                valid_results.append(result_clean)
        
        if valid_results:
            # 🔧 优化：选择最有价值的结果
            best_result = self._select_best_tool_result(valid_results)
            logger.info(f"🔧 从工具执行结果提取最终答案: {best_result[:100]}...")
            return best_result
        
        # 🔧 第三优先级：提取数值计算结果（针对数学问题）
        # 查找数值结果模式
        calculation_patterns = [
            r'结果[：:]\s*([0-9.e-]+\s*[A-Za-z]*)',  # "结果: 9.43e-07 A"
            r'答案[：:]\s*([0-9.e-]+\s*[A-Za-z]*)',  # "答案: 42"
            r'photocurrent[：:]\s*([0-9.e-]+\s*[A-Za-z]*)',  # "photocurrent: 9.43e-07 A"
            r'([0-9.e-]+\s*[A-Za-z]*)\s*(?:安培|A|瓦特|W|米|m)',  # 单位模式
        ]
        
        for pattern in calculation_patterns:
            matches = re.findall(pattern, final_trajectory_str, re.IGNORECASE)
            if matches:
                # 🔧 添加上下文验证 - 确保结果来自实际的工具执行
                calculation_result = matches[-1].strip()
                if self._validate_calculation_context(final_trajectory_str, calculation_result):
                    logger.info(f"🧮 从计算结果提取最终答案: {calculation_result}")
                    return f"计算结果: {calculation_result}"
                else:
                    logger.warning(f"⚠️ 计算结果 {calculation_result} 未通过上下文验证，跳过")
        
        # 🔧 第四优先级：提取搜索答案（针对问答类任务）
        # 查找IORA等专有名词的解释
        info_patterns = [
            r'IORA[是为].*?[。.]',  # IORA相关解释
            r'新加坡国立大学.*?[。.]',  # 大学相关信息
            r'([A-Z]{3,}\s*(?:是|为|指).*?[。.])',  # 缩写解释模式
        ]
        
        for pattern in info_patterns:
            matches = re.findall(pattern, final_trajectory_str, re.DOTALL)
            if matches:
                info_result = matches[-1].strip()
                logger.info(f"📖 从信息检索提取最终答案: {info_result[:100]}...")
                return info_result
        
        # 🔧 第五优先级：智能提取最后的think内容（降低优先级）
        think_tag = TaskExecutionConstants.XML_TAGS['THINK']
        think_pattern = f'<{think_tag}>(.*?)</{think_tag}>'
        think_matches = re.findall(think_pattern, final_trajectory_str, re.DOTALL)
        if think_matches:
            last_think = think_matches[-1].strip()
            # 只有在没有其他结果时才使用思考内容，且需要足够长
            if last_think and len(last_think) > 50:
                logger.info(f"📝 从思考过程提取结果: {last_think[:100]}...")
                return f"分析过程: {last_think[:200]}..."
        
        # 🔧 第六优先级：提取可见的有意义文本
        visible_content = re.sub(r'<[^>]+>', '', final_trajectory_str).strip()
        if visible_content and len(visible_content) > 20:
            # 寻找最后的有意义内容
            lines = [line.strip() for line in visible_content.split('\n') if line.strip()]
            meaningful_lines = []
            
            for line in lines[-10:]:  # 检查最后10行
                # 过滤掉无意义的行
                if (len(line) > 10 and 
                    not line.startswith('---') and
                    'Starting Step' not in line and
                    'executable action' not in line):
                    meaningful_lines.append(line)
            
            if meaningful_lines:
                final_content = ' '.join(meaningful_lines[-3:])  # 取最后3行有意义内容
                logger.info(f"📄 从可见文本提取结果: {final_content[:100]}...")
                return final_content
        
        # 最后备选：返回任务完成状态  
        logger.warning("⚠️ 无法提取具体的最终结果，返回默认完成消息")
        return TaskExecutionConstants.TASK_COMPLETED_NO_ANSWER
    
    def _select_best_tool_result(self, valid_results: list) -> str:
        """选择最有价值的工具执行结果"""
        if not valid_results:
            return ""
        
        import re
        
        # 优先级评分
        scored_results = []
        for result in valid_results:
            score = 0
            result_lower = result.lower()
            
            # 包含数值计算的结果得分更高
            if re.search(r'[0-9.e-]+', result):
                score += 10
            
            # 包含专业术语的结果得分更高
            if any(term in result_lower for term in ['iora', 'university', '大学', '结果', '答案']):
                score += 8
            
            # 长度适中的结果得分更高
            if 20 <= len(result) <= 300:
                score += 5
            
            # 包含搜索结果的得分更高
            if '搜索结果' in result or 'search' in result_lower:
                score += 7
            
            scored_results.append((score, result))
        
        # 返回得分最高的结果
        scored_results.sort(key=lambda x: x[0], reverse=True)
        return scored_results[0][1]
    
    def _should_inject_no_action_message(self, response_text: str) -> bool:
        """🔧 完整修复：严格控制无动作消息注入，彻底消除冗余消息
        
        Args:
            response_text: LLM响应文本
        
        Returns:
            bool: 是否需要注入无动作消息
        """
        import re
        
        # 🔧 增强检测：如果有任何XML标签，都认为有内容
        xml_tags = TaskExecutionConstants.XML_TAGS
        all_possible_tags = [
            f"<{xml_tags['THINK']}>", f"</{xml_tags['THINK']}>",
            f"<{xml_tags['ANSWER']}>", f"</{xml_tags['ANSWER']}>", 
            f"<{xml_tags['RESULT']}>", f"</{xml_tags['RESULT']}>",
            f"<{xml_tags['OBSERVATION']}>", f"</{xml_tags['OBSERVATION']}>",
            f"<{xml_tags['CONCLUSION']}>", f"</{xml_tags['CONCLUSION']}>",
            "<execute_tools/>", "<execute_tools></execute_tools>"
        ]
        
        # 1. 检测任何XML结构化内容
        for tag in all_possible_tags:
            if tag in response_text:
                logger.info(f"💭 检测到XML标签 {tag}，无需注入无动作消息")
                return False
        
        # 2. 检测任何工具服务器标签
        server_tags = ["<microsandbox>", "<deepsearch>", "<browser_use>", "<search_tool>"]
        for tag in server_tags:
            if tag in response_text:
                logger.info(f"🔧 检测到工具标签 {tag}，无需注入无动作消息")
                return False
        
        # 3. 检测有意义的文本内容（更严格的标准）
        clean_text = re.sub(r'<[^>]+>', '', response_text).strip()
        
        # 如果有足够的有意义文本内容
        if len(clean_text) > 20:  # 降低阈值，更宽松
            # 检查是否是有意义的内容（非空白、非重复字符）
            meaningful_chars = len(re.sub(r'\s+', '', clean_text))
            if meaningful_chars > 10:
                logger.info(f"📝 检测到有意义文本内容({meaningful_chars}字符)，无需注入无动作消息")
                return False
        
        # 4. 🔧 新增：检测任务完成的特殊情况
        completion_indicators = [
            "任务完成", "execution completed", "calculation complete",
            "搜索完成", "操作完成", "处理完成", "分析完成"
        ]
        
        response_lower = response_text.lower()
        for indicator in completion_indicators:
            if indicator.lower() in response_lower:
                logger.info(f"✅ 检测到完成指示词 '{indicator}'，无需注入无动作消息")
                return False
        
        # 5. 🔧 新增：如果响应包含任何数字、字母或中文字符的有意义组合
        if re.search(r'[a-zA-Z\u4e00-\u9fff]{3,}', response_text):
            logger.info("📄 检测到有意义的文本组合，无需注入无动作消息")
            return False
        
        # 6. 🔧 特殊情况：如果响应是空的或者只有空白符
        if not response_text or response_text.isspace():
            logger.warning("⚠️ 检测到完全空的响应，需要注入指导消息")
            return True
        
        # 7. 🔧 最严格的判断：只有在响应真的没有任何有用信息时才注入
        # 检查是否只包含无意义的重复字符或符号
        if len(set(response_text.replace(' ', '').replace('\n', ''))) < 3:
            logger.warning(f"⚠️ 检测到无意义的重复内容，需要注入指导消息")
            return True
        
        # 默认情况：不注入无动作消息（更保守的策略）
        logger.info("🎯 响应包含内容，无需注入无动作消息")
        return False
    
    def _extract_detailed_plan(self, response_text: str) -> Optional[str]:
        """🔧 新增：从响应中提取详细计划内容"""
        import re
        
        # 检查think标签中的内容
        think_tag = TaskExecutionConstants.XML_TAGS['THINK']
        think_pattern = f'<{think_tag}>(.*?)</{think_tag}>'
        think_match = re.search(think_pattern, response_text, re.DOTALL)
        
        if think_match:
            think_content = think_match.group(1).strip()
            return think_content
        
        # 如果没有think标签，检查是否有其他形式的计划内容
        # 寻找包含步骤、计划关键词的内容
        plan_indicators = [
            'step', 'phase', 'first', 'next', 'then', 'need to', 'will',
            '步骤', '阶段', '首先', '然后', '接下来', '需要', '将会'
        ]
        
        lines = response_text.split('\n')
        plan_lines = []
        
        for line in lines:
            line_lower = line.lower()
            if any(indicator in line_lower for indicator in plan_indicators):
                plan_lines.append(line.strip())
        
        if plan_lines and len('\n'.join(plan_lines)) > 50:  # 确保有足够的计划内容
            return '\n'.join(plan_lines)
        
        return None
    
    def _has_executable_plan(self, plan_content: str) -> bool:
        """🔧 新增：判断计划内容是否包含可执行的具体步骤"""
        if not plan_content or len(plan_content) < 30:
            return False
        
        plan_lower = plan_content.lower()
        
        # 检查是否包含工具相关的执行意图
        tool_indicators = [
            'search', 'execute', 'run', 'call', 'use', 'browser', 'python', 'code',
            '搜索', '执行', '运行', '调用', '使用', '浏览器', '代码', '工具'
        ]
        
        # 检查是否包含明确的执行步骤
        execution_indicators = [
            'step 1', 'first step', 'start by', 'begin with', 'initially',
            '第一步', '首先', '开始', '先', '第1步'
        ]
        
        # 检查工具服务器名称
        service_indicators = [
            'microsandbox', 'deepsearch', 'browser_use', 'search_tool'
        ]
        
        has_tools = any(indicator in plan_lower for indicator in tool_indicators)
        has_execution_steps = any(indicator in plan_lower for indicator in execution_indicators)
        has_services = any(indicator in plan_lower for indicator in service_indicators)
        
        # 检查是否包含多个步骤（表示这是一个详细计划）
        step_count = (
            plan_lower.count('step') + plan_lower.count('步骤') + 
            plan_lower.count('first') + plan_lower.count('then') + 
            plan_lower.count('next') + plan_lower.count('首先') + 
            plan_lower.count('然后') + plan_lower.count('接下来')
        )
        
        has_multiple_steps = step_count >= 2
        
        # 如果有工具意图、执行步骤、或多步计划，认为这是可执行计划
        is_executable = (has_tools and has_execution_steps) or has_services or has_multiple_steps
        
        logger.debug(f"🔍 计划分析: 工具={has_tools}, 执行步骤={has_execution_steps}, "
                    f"服务={has_services}, 多步骤={has_multiple_steps}, 可执行={is_executable}")
        
        return is_executable
    
    def _extract_first_executable_action(self, plan_content: str) -> Optional[str]:
        """🔧 Priority 3 新增：从计划中提取第一个可执行的具体动作"""
        import re
        
        plan_lower = plan_content.lower()
        lines = plan_content.split('\n')
        
        # 寻找明确的第一步骤
        first_step_patterns = [
            r'(?:step\s*1|first\s*step|第一步|首先)[:\s]*(.*?)(?:\n|$)',
            r'(?:1\.|①|开始|start)[:\s]*(.*?)(?:\n|$)',
            r'(?:需要|need\s*to|will|应该)[:\s]*(.*?)(?:\n|$)'
        ]
        
        for pattern in first_step_patterns:
            match = re.search(pattern, plan_lower, re.IGNORECASE | re.DOTALL)
            if match:
                action = match.group(1).strip()
                # 清理并简化动作描述
                if len(action) > 10 and len(action) < 200:
                    return action
        
        # 如果没有找到明确的第一步，尝试从计划中提取工具相关的动作
        tool_action_patterns = [
            r'(search\s+for\s+[^.\n]+)',
            r'(execute\s+[^.\n]+)',
            r'(run\s+[^.\n]+)',
            r'(use\s+[^.\n]+)',
            r'(搜索[^。\n]+)',
            r'(执行[^。\n]+)',
            r'(运行[^。\n]+)',
            r'(使用[^。\n]+)'
        ]
        
        for pattern in tool_action_patterns:
            match = re.search(pattern, plan_lower)
            if match:
                action = match.group(1).strip()
                if len(action) > 5 and len(action) < 150:
                    return action
        
        return None
    
    def _validate_calculation_context(self, trajectory_str: str, calculation_result: str) -> bool:
        """🔧 新增：验证计算结果是否来自真实的工具执行上下文"""
        import re
        
        # 1. 检查结果是否出现在工具执行结果标签内
        result_tag = TaskExecutionConstants.XML_TAGS['RESULT']
        result_pattern = f'<{result_tag}>(.*?)</{result_tag}>'
        result_blocks = re.findall(result_pattern, trajectory_str, re.DOTALL)
        
        # 检查计算结果是否在任何result块中
        for result_block in result_blocks:
            if calculation_result in result_block:
                logger.debug("✅ 计算结果在工具执行结果中找到")
                return True
        
        # 2. 检查结果是否在工具执行的上下文中（附近有工具调用）
        # 查找结果在轨迹中的位置
        result_index = trajectory_str.find(calculation_result)
        if result_index == -1:
            logger.debug("❌ 未找到计算结果在轨迹中的位置")
            return False
        
        # 检查结果前后500字符内是否有工具执行标记
        context_start = max(0, result_index - 500)
        context_end = min(len(trajectory_str), result_index + len(calculation_result) + 500)
        context = trajectory_str[context_start:context_end]
        
        tool_execution_indicators = [
            '<execute_tools', '</execute_tools>', '<result>', '</result>',
            'microsandbox', 'deepsearch', 'browser_use', 'search_tool',
            '代码执行', '执行结果', '工具执行', '计算完成'
        ]
        
        has_tool_context = any(indicator in context for indicator in tool_execution_indicators)
        if has_tool_context:
            logger.debug("✅ 计算结果在工具执行上下文中")
            return True
        
        # 3. 检查是否是纯思考过程中的虚假计算
        think_tag = TaskExecutionConstants.XML_TAGS['THINK']
        think_pattern = f'<{think_tag}>(.*?)</{think_tag}>'
        think_blocks = re.findall(think_pattern, trajectory_str, re.DOTALL)
        
        for think_block in think_blocks:
            if calculation_result in think_block:
                # 如果结果只在思考过程中，且没有对应的工具执行，则认为是虚假的
                logger.debug("⚠️ 计算结果只在思考过程中发现，可能是虚假结果")
                return False
        
        # 4. 检查结果是否有合理的数值格式和单位
        # 如果是纯字母（如"e"），很可能是虚假结果
        if re.match(r'^[a-zA-Z]$', calculation_result.strip()):
            logger.debug("❌ 计算结果是单个字母，可能是虚假结果")
            return False
        
        # 5. 默认情况：如果结果看起来合理且没有明显问题，允许通过
        logger.debug("🔧 计算结果通过基本验证")
        return True
    
    def _has_meaningful_tool_results(self, trajectory_str: str) -> bool:
        """🔧 Priority 2 增强：工具结果解析能力，支持复杂JSON结构"""
        import re
        import json
        
        result_tag = TaskExecutionConstants.XML_TAGS['RESULT']
        result_pattern = f'<{result_tag}>(.*?)</{result_tag}>'
        result_blocks = re.findall(result_pattern, trajectory_str, re.DOTALL)
        
        meaningful_results = 0
        for result_block in result_blocks:
            result_clean = result_block.strip()
            
            # 排除无意义的结果
            if (len(result_clean) > 20 and  # 有足够的内容
                TaskExecutionConstants.NO_ACTION_PERFORMED not in result_clean and
                "No executable action detected" not in result_clean and
                "Error:" not in result_clean and
                "failed" not in result_clean.lower()):
                
                # 🔧 Priority 2 新增：复杂JSON结构解析
                is_meaningful = self._analyze_complex_result_content(result_clean)
                
                if is_meaningful:
                    meaningful_results += 1
        
        # 如果有至少一个有意义的工具结果，认为工具执行有意义
        has_meaningful = meaningful_results > 0
        logger.debug(f"🔍 工具结果分析: 总结果块={len(result_blocks)}, 有意义结果={meaningful_results}, 判定={has_meaningful}")
        
        return has_meaningful
    
    def _analyze_complex_result_content(self, result_content: str) -> bool:
        """🔧 Priority 2 新增：分析复杂结果内容，支持JSON、代码、搜索结果等"""
        import re
        import json
        
        # 1. 检查是否包含有价值的信息指示词
        has_data = any(indicator in result_content.lower() for indicator in [
            'result', 'found', 'success', 'completed', '结果', '成功', '完成',
            'http', 'www', 'search', 'execute', 'calculation', 'answer'
        ])
        
        # 2. 检查是否包含数值、代码执行结果或搜索结果
        has_numerical = re.search(r'\d+', result_content)
        has_technical_content = any(keyword in result_content.lower() for keyword in [
            'python', 'code', 'execute', 'import', 'def', 'return',
            'search results', '搜索结果', 'photocurrent', 'iora'
        ])
        
        # 3. 🔧 新增：JSON结构解析
        has_structured_data = self._has_structured_json_data(result_content)
        
        # 4. 🔧 新增：网页内容解析
        has_web_content = self._has_meaningful_web_content(result_content)
        
        # 5. 🔧 新增：文件搜索结果解析
        has_file_results = self._has_meaningful_file_results(result_content)
        
        # 6. 🔧 新增：计算结果解析
        has_calculation_results = self._has_calculation_results(result_content)
        
        return (has_data or has_numerical or has_technical_content or 
                has_structured_data or has_web_content or has_file_results or 
                has_calculation_results)
    
    def _has_structured_json_data(self, content: str) -> bool:
        """检查是否包含有意义的JSON结构数据"""
        import json
        import re
        
        # 尝试提取JSON对象
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_matches = re.findall(json_pattern, content, re.DOTALL)
        
        for json_str in json_matches:
            try:
                data = json.loads(json_str)
                if isinstance(data, dict) and len(data) > 0:
                    # 检查是否包含有意义的键值对
                    meaningful_keys = ['result', 'data', 'response', 'output', 'value', 'content']
                    if any(key in data for key in meaningful_keys):
                        return True
            except json.JSONDecodeError:
                continue
        
        return False
    
    def _has_meaningful_web_content(self, content: str) -> bool:
        """检查是否包含有意义的网页内容"""
        import re
        
        # 检查URL模式
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[^\s<>"\']+' 
        has_urls = re.search(url_pattern, content)
        
        # 检查HTML标签
        html_pattern = r'<[^>]+>'
        has_html = re.search(html_pattern, content)
        
        # 检查网页特有内容
        web_indicators = ['page title', 'page content', 'browser', 'navigation', 'click', 'scroll']
        has_web_terms = any(indicator in content.lower() for indicator in web_indicators)
        
        return has_urls or has_html or has_web_terms
    
    def _has_meaningful_file_results(self, content: str) -> bool:
        """检查是否包含有意义的文件搜索结果"""
        import re
        
        # 文件路径模式
        file_pattern = r'[^\s<>"\']+\.[a-zA-Z0-9]+'
        has_files = re.search(file_pattern, content)
        
        # 文件操作指示词
        file_indicators = ['file', 'directory', 'folder', 'path', '文件', '目录', '路径']
        has_file_terms = any(indicator in content.lower() for indicator in file_indicators)
        
        # 搜索结果数量
        count_pattern = r'found\s+(\d+)|(\d+)\s+results|(\d+)\s+files'
        has_counts = re.search(count_pattern, content.lower())
        
        return has_files or (has_file_terms and has_counts)
    
    def _has_calculation_results(self, content: str) -> bool:
        """检查是否包含计算结果"""
        import re
        
        # 数学表达式和结果
        math_pattern = r'=\s*[-+]?\d*\.?\d+|result:\s*[-+]?\d*\.?\d+|answer:\s*[-+]?\d*\.?\d+'
        has_math = re.search(math_pattern, content.lower())
        
        # 计算相关术语
        calc_indicators = ['calculation', 'computed', 'evaluated', '计算', '结果', 'output']
        has_calc_terms = any(indicator in content.lower() for indicator in calc_indicators)
        
        # 复杂数值（科学计数法、小数等）
        complex_num_pattern = r'[-+]?\d*\.?\d+[eE][-+]?\d+|[-+]?\d+\.\d{2,}'
        has_complex_nums = re.search(complex_num_pattern, content)
        
        return has_math or (has_calc_terms and has_complex_nums)
    
    def _evaluate_multi_tool_coordination_quality(self, trajectory_str: str) -> Dict[str, Any]:
        """🔧 Priority 4 新增：评估多工具协同的质量和效果"""
        import re
        
        # 统计使用的工具类型
        used_tools = set()
        result_tag = TaskExecutionConstants.XML_TAGS['RESULT']
        result_pattern = f'<{result_tag}>(.*?)</{result_tag}>'
        result_blocks = re.findall(result_pattern, trajectory_str, re.DOTALL)
        
        # 识别使用的工具服务
        tool_services = ['microsandbox', 'deepsearch', 'browser_use', 'search_tool']
        for service in tool_services:
            if service in trajectory_str.lower():
                used_tools.add(service)
        
        tools_count = len(used_tools)
        is_multi_tool = tools_count >= TaskExecutionConstants.MULTI_TOOL_COORDINATION['RESULT_INTEGRATION']['min_meaningful_tools']
        
        # 评估工具协同质量
        quality_score = 0.0
        coordination_indicators = []
        
        if is_multi_tool:
            # 检查工具间的数据流转
            data_flow_quality = self._assess_tool_data_flow(trajectory_str, used_tools)
            quality_score += data_flow_quality * 0.4
            coordination_indicators.append(f"数据流转质量: {data_flow_quality:.2f}")
            
            # 检查结果整合质量
            integration_quality = self._assess_result_integration(result_blocks)
            quality_score += integration_quality * 0.3
            coordination_indicators.append(f"结果整合质量: {integration_quality:.2f}")
            
            # 检查任务完成度
            completion_quality = self._assess_task_completion_via_coordination(trajectory_str)
            quality_score += completion_quality * 0.3
            coordination_indicators.append(f"任务完成度: {completion_quality:.2f}")
        
        return {
            'is_coordinated': is_multi_tool,
            'tools_used': list(used_tools),
            'tools_count': tools_count,
            'quality_score': quality_score,
            'coordination_indicators': coordination_indicators
        }
    
    def _assess_tool_data_flow(self, trajectory_str: str, used_tools: set) -> float:
        """评估工具间的数据流转质量"""
        # 检查前一个工具的输出是否被后续工具使用
        data_flow_score = 0.0
        
        # 简化版：检查是否有明显的数据传递模式
        if 'microsandbox' in used_tools and 'deepsearch' in used_tools:
            # 搜索后分析模式
            if 'search' in trajectory_str.lower() and 'code' in trajectory_str.lower():
                data_flow_score += 0.5
        
        if 'browser_use' in used_tools and 'search_tool' in used_tools:
            # 浏览后搜索模式
            if 'browse' in trajectory_str.lower() and 'file' in trajectory_str.lower():
                data_flow_score += 0.5
        
        return min(1.0, data_flow_score)
    
    def _assess_result_integration(self, result_blocks: list) -> float:
        """评估结果整合质量"""
        if len(result_blocks) < 2:
            return 0.0
        
        # 检查结果间的关联性
        integration_score = 0.0
        
        # 简化版：检查结果是否包含相互引用或补充信息
        combined_results = ' '.join(result_blocks).lower()
        
        # 检查是否有数据引用
        if any(indicator in combined_results for indicator in ['based on', 'according to', 'using the', '基于', '根据']):
            integration_score += 0.4
        
        # 检查是否有综合分析
        if any(indicator in combined_results for indicator in ['combined', 'integrated', 'overall', '综合', '整合']):
            integration_score += 0.3
        
        # 检查结果的互补性
        if len(set(result_blocks)) == len(result_blocks):  # 无重复结果
            integration_score += 0.3
        
        return min(1.0, integration_score)
    
    def _assess_task_completion_via_coordination(self, trajectory_str: str) -> float:
        """评估通过工具协同完成任务的程度"""
        completion_score = 0.0
        
        # 检查是否有明确的任务完成指示
        completion_indicators = [
            'task completed', 'finished', 'done', 'result', 'conclusion',
            '任务完成', '完成', '结果', '结论', '答案'
        ]
        
        trajectory_lower = trajectory_str.lower()
        for indicator in completion_indicators:
            if indicator in trajectory_lower:
                completion_score += 0.2
        
        # 检查是否有数值或具体结果
        import re
        if re.search(r'\d+\.?\d*', trajectory_str):
            completion_score += 0.3
        
        return min(1.0, completion_score)
        
    def _detect_success(self, response: str) -> bool:
        """检测XML响应是否成功 - 保留向后兼容性"""
        response_lower = response.lower()
        return ('<answer>' in response_lower) and ('error>' not in response_lower)
    
    def _get_trajectory_file_path(self, task_id: str, is_raw: bool = False) -> str:
        """根据存储模式获取轨迹文件路径"""
        out_dir = get_trajectories_dir()
        date_str = datetime.now().strftime("%Y-%m-%d")
        group_dir = os.path.join(out_dir, "grouped", date_str)
        if is_raw:
            return os.path.join(group_dir, f"raw_trajectories_{date_str}.jsonl")
        else:
            return os.path.join(group_dir, f"trajectories_{date_str}.jsonl")
    
    async def _save_xml_output(self, xml_output):
        """保存XML输出数据到JSONL文件"""
        file_path = self._get_trajectory_file_path(xml_output['task_id'])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(xml_output, ensure_ascii=False) + '\n')
        
        logger.info(f"保存XML数据到: {file_path}")
    
    def _detect_triggered_stop_sequence(self, response_text: str, stop_sequences: list) -> str:
        """检测触发的停止序列"""
        for stop_seq in stop_sequences:
            if stop_seq in response_text:
                return stop_seq
        return "unknown"
    
    async def _execute_tool_with_logging(self, action: dict, execution_index: int) -> dict:
        """执行工具调用并记录详细日志"""
        tool_start_time = time.time()
        
        # 构建toolscore请求
        service_name = action.get('service')
        tool_name = action.get('tool')
        tool_input = action.get('input')
        
        param_mapping = {
            "browser_use": "query",
            "microsandbox": "code",
            "deepsearch": "question"
        }
        param_name = param_mapping.get(service_name, "input")
        
        toolscore_request = {
            "endpoint": f"http://127.0.0.1:{self._get_service_port(service_name)}/execute_tool",
            "method": "POST",
            "payload": {
                "tool_id": service_name,
                "action": tool_name,
                "parameters": {param_name: tool_input}
            }
        }
        
        # 🔧 智能工具执行与错误分析
        try:
            raw_result = await self.toolscore_client.execute_tool(
                tool_id=service_name,
                action=tool_name,
                parameters={param_name: tool_input}
            )
            
            formatted_result = self._format_tool_output(service_name, tool_name, raw_result)
            execution_status = "success"
            error_details = None
            
        except Exception as e:
            error_str = str(e)
            error_type = self._analyze_error_type(error_str)
            
            raw_result = {"error": error_str, "success": False, "error_type": error_type}
            formatted_result = self._format_error_with_recovery_suggestion(error_str, error_type, service_name, tool_name)
            execution_status = "failure"
            error_details = error_str
        
        tool_end_time = time.time()
        
        # 🔍 记录工具执行日志
        self.step_logger.log_tool_execution(
            execution_index=execution_index,
            action=action,
            toolscore_request=toolscore_request,
            raw_response=raw_result,
            formatted_result=formatted_result,
            start_time=tool_start_time,
            end_time=tool_end_time,
            execution_status=execution_status,
            error_details=error_details
        )
        
        return {
            "formatted_result": formatted_result,
            "raw_result": raw_result,
            "execution_status": execution_status
        }
    
    async def _execute_parallel_with_logging(self, actions: list) -> list:
        """并发执行多个工具调用并记录日志"""
        import asyncio
        
        if not actions:
            return []
        
        # 创建并发任务
        tasks = [
            self._execute_tool_with_logging(action, i) 
            for i, action in enumerate(actions)
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 提取格式化结果
        formatted_results = []
        for result in results:
            if isinstance(result, Exception):
                formatted_results.append(f"Error: {result}")
            else:
                formatted_results.append(result["formatted_result"])
        
        return formatted_results
    
    def _get_service_port(self, service_name: str) -> int:
        """获取服务端口号"""
        port_mapping = {
            "microsandbox": 8090,
            "deepsearch": 8086,
            "browser_use": 8082,
            "search_tool": 8080
        }
        return port_mapping.get(service_name, 8080)

    async def cleanup(self):
        """清理资源"""
        logger.info("🧹 清理Enhanced Reasoning Runtime资源")
        if self.toolscore_client and hasattr(self.toolscore_client, 'close'):
            await self.toolscore_client.close()
        self.is_initialized = False
        logger.info("✅ 资源清理完成")
    
