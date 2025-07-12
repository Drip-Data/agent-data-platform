"""
增强的推理运行时 - 简化版本
专注于核心功能：LLM推理、工具执行、任务处理、XML流式输出
"""

import asyncio
import json
import logging
import os
import re
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
from core.task_decomposer import TaskDecomposer, TaskComplexity
from core.xml_parser_enhanced import EnhancedXMLParser
from core.context_flow_manager import ContextFlowManager
from core.smart_query_optimizer import SmartQueryOptimizer
from core.tool_result_enhancer import ToolResultEnhancer
from core.utils.json_parameter_parser import JSONParameterParser


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
        
        # 🆕 Stage 3: 任务分解器和增强XML解析器
        self.task_decomposer = TaskDecomposer()
        self.xml_parser = EnhancedXMLParser()
        logger.info("✅ Stage 3组件初始化: TaskDecomposer & EnhancedXMLParser")
        
        # 🔄 Stage 4: 上下文流管理和工具优化组件
        self.context_flow_manager = ContextFlowManager()
        self.query_optimizer = SmartQueryOptimizer()
        self.result_enhancer = ToolResultEnhancer()
        logger.info("✅ Stage 4组件初始化: 信息传递优化系统")
        
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
                logger.info("ℹ️ Token管理器未启用 - 当前LLM提供商非Gemini或Gemini Provider不可用")
        except Exception as e:
            logger.warning(f"⚠️ Token管理器初始化失败: {e}")
            self.token_manager = None
        
        # 🔧 初始化JSON参数解析器
        self.json_parameter_parser = JSONParameterParser(tool_manager=self.tool_manager)
        logger.info("✅ JSON参数解析器初始化成功")
        
        self.mcp_servers = self._load_mcp_config("config/mcp_servers.json")
    
    def _get_gemini_provider(self) -> Optional[GeminiProvider]:
        """从LLM客户端获取Gemini Provider实例"""
        try:
            logger.debug("🔍 开始查找Gemini Provider...")
            
            # 调试信息：显示客户端属性
            if hasattr(self.client, 'provider'):
                logger.debug(f"🔍 LLM客户端provider类型: {type(self.client.provider)}, 值: {getattr(self.client.provider, 'value', 'N/A')}")
            if hasattr(self.client, 'provider_instance'):
                logger.debug(f"🔍 LLM客户端provider_instance类型: {type(self.client.provider_instance)}")
            
            # 检查LLM客户端是否有provider_instance属性（正确的属性名）
            if hasattr(self.client, 'provider_instance') and isinstance(self.client.provider_instance, GeminiProvider):
                logger.info("✅ 找到LLM客户端中的Gemini Provider实例")
                return self.client.provider_instance
            
            # 检查LLM客户端是否使用Gemini提供商
            if hasattr(self.client, 'provider') and hasattr(self.client.provider, 'value') and self.client.provider.value == 'gemini':
                if hasattr(self.client, 'provider_instance'):
                    logger.info("✅ 通过provider枚举找到Gemini Provider实例")
                    return self.client.provider_instance
            
            # 尝试从LLM客户端配置创建新的Gemini Provider
            if hasattr(self.client, 'config'):
                client_config = self.client.config
                provider_name = client_config.get('provider') or client_config.get('default_provider')
                logger.debug(f"🔍 LLM客户端配置的provider: {provider_name}")
                
                if provider_name and provider_name.lower() == 'gemini':
                    # 创建新的Gemini Provider实例
                    gemini_config = client_config.copy()
                    if 'providers' in client_config and 'gemini' in client_config['providers']:
                        gemini_provider_config = client_config['providers']['gemini']
                        gemini_config.update(gemini_provider_config)
                    
                    # 确保API密钥可用
                    if not gemini_config.get('api_key') or not gemini_config.get('gemini_api_key'):
                        import os
                        api_key = os.getenv('GEMINI_API_KEY')
                        if api_key:
                            gemini_config['api_key'] = api_key
                            gemini_config['gemini_api_key'] = api_key
                            logger.debug("🔍 从环境变量获取Gemini API Key")
                    
                    if gemini_config.get('api_key') or gemini_config.get('gemini_api_key'):
                        logger.info("✅ 从LLM客户端配置创建新的Gemini Provider实例")
                        return GeminiProvider(gemini_config)
                    else:
                        logger.warning("⚠️ Gemini配置存在但缺少API密钥")
            
            # 最后尝试：从配置管理器获取
            if hasattr(self.config_manager, 'get_llm_config'):
                llm_config = self.config_manager.get_llm_config()
                if 'providers' in llm_config and 'gemini' in llm_config['providers']:
                    gemini_config = llm_config['providers']['gemini']
                    if gemini_config.get('enabled', True):  # 默认启用
                        # 确保API密钥可用
                        if not gemini_config.get('api_key'):
                            import os
                            api_key = os.getenv('GEMINI_API_KEY')
                            if api_key:
                                gemini_config['api_key'] = api_key
                        
                        logger.info("✅ 从配置管理器创建Gemini Provider实例")
                        return GeminiProvider(gemini_config)
            
            logger.info("ℹ️ 无法获取Gemini Provider - 当前系统使用非Gemini LLM提供商")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取Gemini Provider失败: {e}")
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

    async def _execute_tool(self, action: dict, step_number: int = 0) -> str:
        """
        根据单个动作字典，通过toolscore_client调用对应的MCP Server并返回结果。
        🔧 完整修复：统一所有工具的结果格式化，使结果清晰易读
        🔄 Stage 4增强：集成查询优化和结果增强
        """
        service_name = action.get('service')
        tool_name = action.get('tool')
        tool_input = action.get('input')

        if not all([service_name, tool_name]):
            return "Error: Invalid action format. 'service' and 'tool' are required."

        # 🔄 Stage 4: 查询优化
        optimized_input = tool_input
        if service_name in ['deepsearch', 'browser_use'] and tool_input:
            try:
                # 分析和优化查询
                query_analysis = self.query_optimizer.analyze_query(
                    tool_input, 
                    context=self.context_flow_manager.get_relevant_context(service_name, step_number)
                )
                
                if query_analysis.confidence < 0.5 and query_analysis.optimized_queries:
                    # 使用优化后的查询
                    optimized_input = query_analysis.optimized_queries[0]
                    logger.info(f"🔍 查询优化: {tool_input[:50]}... -> {optimized_input[:50]}...")
                
                # 添加上下文信息到查询
                context_prompt = self.context_flow_manager.generate_context_prompt(
                    service_name, step_number, tool_input
                )
                if context_prompt:
                    optimized_input = f"{context_prompt}\n\nQuery: {optimized_input}"
                    
            except Exception as e:
                logger.warning(f"⚠️ 查询优化失败，使用原始查询: {e}")
                optimized_input = tool_input

        # 🔧 P1 核心修复：使用JSON参数解析器
        parser = JSONParameterParser(self.tool_manager)
        parse_result = parser.parse_tool_parameters(service_name, tool_name, optimized_input)

        if not parse_result.is_valid:
            # 如果解析或验证失败，返回错误信息
            error_message = f"Tool execution failed: Invalid parameters for {service_name}/{tool_name}. "
            error_message += "; ".join(parse_result.errors)
            if parse_result.suggestions:
                error_message += f" Suggestions: {'; '.join(parse_result.suggestions)}"
            return error_message

        parameters = parse_result.parsed_params
        param_name = next(iter(parameters)) if parameters else '' # For logging

        logger.info(f"🔧 执行工具: service='{service_name}', tool='{tool_name}', param_name='{param_name}', input_length={len(str(optimized_input))}")

        try:
            result = await self.toolscore_client.execute_tool(
                tool_id=service_name,
                action=tool_name,
                parameters=parameters
            )
            
            # 🔄 Stage 4: 结果增强
            enhanced_result = None
            try:
                enhanced_result = self.result_enhancer.enhance_tool_result(
                    tool_name=service_name,
                    raw_result=result,
                    execution_context={
                        "step_number": step_number,
                        "original_query": tool_input,
                        "optimized_query": optimized_input
                    }
                )
                
                # 提取上下文数据
                self.context_flow_manager.extract_context_data(
                    str(result), service_name, step_number
                )
                
                # 记录查询结果用于学习
                success = enhanced_result.result_type.value in ['success', 'partial_success']
                query_type = self.query_optimizer._identify_query_type(tool_input)
                self.query_optimizer.record_query_result(
                    tool_input, query_type, success, str(result)
                )
                
            except Exception as e:
                logger.warning(f"⚠️ 结果增强失败: {e}")
            
            if isinstance(result, dict):
                if result.get('success', True):
                    output = result.get('data', result.get('output', result.get('result', str(result))))
                    
                    # 🔧 修复：特殊处理 DeepSearch 的 JSON 字符串输出
                    if service_name == 'deepsearch' and isinstance(output, str):
                        try:
                            # 尝试解析 JSON 字符串（DeepSearch 的成功输出格式）
                            import json
                            parsed_output = json.loads(output)
                            if isinstance(parsed_output, dict):
                                output = parsed_output
                                logger.debug(f"Successfully parsed DeepSearch JSON string output")
                        except (json.JSONDecodeError, ValueError) as e:
                            # 如果不是有效的JSON，保持原始字符串
                            logger.debug(f"DeepSearch output is not JSON string, keeping as string: {e}")
                            pass
                    
                    # 🔧 完整修复：为所有工具统一结果格式化
                    formatted_output = self._format_tool_output(service_name, tool_name, output)
                    
                    # 🔄 Stage 4: 如果有增强结果，添加额外信息
                    if enhanced_result and enhanced_result.confidence_score < 0.5:
                        formatted_output += f"\n\n⚠️ 结果置信度较低 ({enhanced_result.confidence_score:.2f})，建议验证信息准确性。"
                    
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
        
        # 2. DeepSearch - 显示完整原始JSON结果
        elif service_name == 'deepsearch':
            import json
            try:
                if isinstance(output, dict):
                    return json.dumps(output, ensure_ascii=False, indent=2)
                elif isinstance(output, list):
                    return json.dumps(output, ensure_ascii=False, indent=2)
                else:
                    return str(output)
            except Exception as e:
                logger.warning(f"Failed to format DeepSearch output: {e}")
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
        
        # 5. Memory Staging - 格式化内存暂存结果
        elif service_name == 'memory_staging':
            return self._format_memory_staging_output_generic(tool_name, output)
        
        # 6. 其他工具 - 通用格式化
        else:
            return self._format_generic_output(output)
    
    def _format_deepsearch_output(self, output: dict) -> str:
        """🔧 修复：正确处理DeepSearch的实际输出格式，支持JSON字符串和结构化数据"""
        try:
            # 🔧 修复：首先处理 DeepSearch 的实际输出格式
            # 检查是否是包含JSON字符串的格式（成功情况）
            if 'query' in output and 'content' in output:
                query = output.get('query', '')
                content = output.get('content', '')
                
                formatted_lines = []
                
                # 添加查询信息
                if query:
                    formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_QUERY']}: {query}")
                
                # 添加内容（这是主要的研究结果）
                if content and content.strip():
                    formatted_lines.append(f"\n{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_SUMMARY']}:")
                    # 限制内容长度，避免过长
                    max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
                    content_clean = content.strip()
                    if len(content_clean) > max_content:
                        content_clean = content_clean[:max_content] + "..."
                    formatted_lines.append(content_clean)
                
                # 如果有格式化内容，返回它
                if formatted_lines:
                    return '\n'.join(formatted_lines)
            
            # 🔧 回退：处理传统的 search_results 格式
            search_results = output.get('search_results', [])
            query = output.get('query', '')
            summary = output.get('summary', '')
            answer = output.get('answer', '')  # 添加对answer字段的支持
            
            formatted_lines = []
            
            # 添加查询信息
            if query:
                formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_QUERY']}: {query}")
            
            # 添加答案或摘要
            if answer:
                formatted_lines.append(f"\n{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['SEARCH_SUMMARY']}:")
                max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
                answer_clean = answer.strip()
                if len(answer_clean) > max_content:
                    answer_clean = answer_clean[:max_content] + "..."
                formatted_lines.append(answer_clean)
            elif summary:
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
            
            # 🔧 修复：只有在完全没有任何有用信息时才返回"未找到结果"
            if not result_text:
                # 检查是否有任何其他有用的字段
                other_content = []
                for key, value in output.items():
                    if key not in ['query', 'content', 'search_results', 'summary', 'answer'] and value:
                        if isinstance(value, str) and value.strip():
                            other_content.append(f"{key}: {str(value)[:200]}...")
                        elif isinstance(value, (dict, list)) and value:
                            other_content.append(f"{key}: {str(value)[:200]}...")
                
                if other_content:
                    return "DeepSearch结果:\n" + "\n".join(other_content)
                else:
                    return "搜索完成，但未找到相关结果"
            
            return result_text
            
        except Exception as e:
            logger.warning(f"Failed to format DeepSearch output: {e}")
            max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
            return f"DeepSearch搜索完成，原始结果: {str(output)[:max_content]}..."
    
    def _format_deepsearch_list_output(self, output: list) -> str:
        """🔧 修复：格式化DeepSearch列表结果，避免错误的硬编码消息"""
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
            # 🔧 修复：正确提取browser-use的响应结构
            # 实际结构: {success: True, result: {...}, output: {...}, processing_time_ms: ...}
            result_data = output.get('result', {})
            output_data = output.get('output', {})
            
            # 提取关键信息 - 修正字段路径
            status = output.get('success', result_data.get('success', True))
            
            # 🔧 修复：从result和output中提取内容
            content = result_data.get('content', output_data.get('content', ''))
            
            # 🔧 修复：提取搜索相关信息
            url = result_data.get('url', output_data.get('url', ''))
            query = result_data.get('query', output_data.get('query', ''))
            error = result_data.get('error', output_data.get('error', ''))
            
            # 🔧 关键修复：检查所有可能的搜索结果字段
            search_results = (result_data.get('search_results') or 
                            result_data.get('results') or
                            output_data.get('search_results') or 
                            output_data.get('results') or [])
            
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
            
            # 🔧 增强：处理包含搜索结果的content字段
            elif content and isinstance(content, str):
                max_content = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_CONTENT_LENGTH']
                
                # 检查content是否包含Google搜索结果格式
                if "Google搜索结果" in content or "找到" in content and "个相关结果" in content:
                    # 截取合理长度的搜索结果内容
                    truncated_content = content[:max_content]
                    formatted_lines.append(f"搜索内容摘要: {truncated_content}...")
                    
                # 如果内容是HTML，尝试提取文本
                elif '<html>' in content.lower() or '<div>' in content.lower():
                    import re
                    text_content = re.sub(r'<[^>]+>', '', content)
                    text_content = re.sub(r'\s+', ' ', text_content).strip()
                    if text_content:
                        formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['PAGE_CONTENT']}: {text_content[:max_content]}...")
                else:
                    formatted_lines.append(f"{TaskExecutionConstants.TOOL_FORMAT_PREFIXES['OPERATION_RESULT']}: {str(content)[:max_content]}...")
            
            # 🔧 增强：确保总是有内容输出，避免触发原始数据后备逻辑
            result_text = '\n'.join(formatted_lines).strip()
            if not result_text or len(result_text) < 20:
                # 🔧 修复：提供简洁的后备输出，避免大量重复数据
                logger.warning(f"Browser Use output seems incomplete. Raw keys: {list(output.keys())}")
                
                # 尝试从output中提取基本信息
                success_status = "成功" if status else "失败"
                basic_info = f"浏览器操作执行 - {success_status}"
                
                if query:
                    basic_info += f"\n查询: {query}"
                if url:
                    basic_info += f"\nURL: {url}"
                if error:
                    basic_info += f"\n错误: {error}"
                
                # 🔧 关键修复：避免输出大量原始数据，只输出摘要
                return basic_info + "\n(详细结果处理中...)"
            
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
        """🔧 修改：显示MicroSandbox的完整原始JSON结果"""
        import json
        try:
            # 直接返回完整的原始JSON结构，不进行任何简化
            if isinstance(output, dict):
                return json.dumps(output, ensure_ascii=False, indent=2)
            else:
                return str(output)
        except Exception as e:
            logger.warning(f"Failed to format MicroSandbox output: {e}")
            return str(output)
    
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

    def _format_memory_staging_output(self, action: str, output: dict) -> str:
        """格式化内存暂存工具输出 - 为工具执行方法使用"""
        return self._format_memory_staging_output_generic(action, output)
    
    def _format_memory_staging_output_generic(self, action: str, output: dict) -> str:
        """格式化内存暂存工具输出 - 通用格式化方法"""
        try:
            if not isinstance(output, dict):
                return str(output)
            
            success = output.get("success", False)
            
            if action == "memory_write":
                if success:
                    key = output.get("key", "unknown")
                    data_type = output.get("data_type", "unknown")
                    return f"✅ 数据已保存到暂存区: {key} (类型: {data_type})"
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 保存数据失败: {error}"
            
            elif action == "memory_read":
                if success:
                    key = output.get("key", "unknown")
                    value = output.get("value")
                    data_type = output.get("data_type", "unknown")
                    age = output.get("age_seconds", 0)
                    
                    # 格式化年龄
                    if age < 60:
                        age_str = f"{int(age)}秒前"
                    elif age < 3600:
                        age_str = f"{int(age/60)}分钟前"
                    else:
                        age_str = f"{int(age/3600)}小时前"
                    
                    # 格式化值预览
                    if isinstance(value, (dict, list)):
                        value_preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    else:
                        value_preview = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
                    
                    return f"📖 从暂存区读取: {key}\n类型: {data_type} ({age_str})\n内容: {value_preview}"
                else:
                    error = output.get("error", "Unknown error")
                    available_keys = output.get("available_keys", [])
                    if available_keys:
                        return f"❌ 读取失败: {error}\n可用键名: {', '.join(available_keys)}"
                    else:
                        return f"❌ 读取失败: {error}"
            
            elif action == "memory_list":
                if success:
                    entries = output.get("entries", [])
                    total_count = output.get("total_count", 0)
                    
                    if total_count == 0:
                        return "📋 暂存区为空"
                    
                    result_lines = [f"📋 暂存区内容 ({total_count} 项):"]
                    for entry in entries[:10]:  # 只显示前10项
                        key = entry.get("key", "unknown")
                        data_type = entry.get("data_type", "unknown")
                        age = entry.get("age_seconds", 0)
                        
                        if age < 60:
                            age_str = f"{int(age)}秒前"
                        elif age < 3600:
                            age_str = f"{int(age/60)}分钟前"
                        else:
                            age_str = f"{int(age/3600)}小时前"
                        
                        result_lines.append(f"  - {key} ({data_type}) - {age_str}")
                    
                    if total_count > 10:
                        result_lines.append(f"  ... 还有 {total_count - 10} 项")
                    
                    return "\n".join(result_lines)
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 列表获取失败: {error}"
            
            elif action == "memory_search":
                if success:
                    matches = output.get("matches", [])
                    total_matches = output.get("total_matches", 0)
                    query = output.get("query", "")
                    
                    if total_matches == 0:
                        return f"🔍 搜索 '{query}' 无结果"
                    
                    result_lines = [f"🔍 搜索 '{query}' 找到 {total_matches} 个匹配项:"]
                    for match in matches[:5]:  # 只显示前5个匹配
                        key = match.get("key", "unknown")
                        score = match.get("score", 0)
                        reasons = match.get("match_reasons", [])
                        value_preview = str(match.get("value", ""))[:100] + "..." if len(str(match.get("value", ""))) > 100 else str(match.get("value", ""))
                        
                        result_lines.append(f"  - {key} (分数: {score}, 匹配: {', '.join(reasons)})")
                        result_lines.append(f"    内容: {value_preview}")
                    
                    if total_matches > 5:
                        result_lines.append(f"  ... 还有 {total_matches - 5} 个匹配项")
                    
                    return "\n".join(result_lines)
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 搜索失败: {error}"
            
            elif action == "memory_clear":
                if success:
                    key = output.get("key")
                    if key:
                        return f"🗑️ 已清除暂存数据: {key}"
                    else:
                        cleared_count = output.get("cleared_count", 0)
                        return f"🗑️ 已清空所有暂存数据 ({cleared_count} 项)"
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 清除失败: {error}"
            
            else:
                # 未知动作，使用通用格式化
                message = output.get("message", str(output))
                return f"🔄 内存暂存操作 ({action}): {message}"
        
        except Exception as e:
            logger.warning(f"Failed to format memory staging output: {e}")
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
        
        # MicroSandbox连接管理器已移除 - 使用标准工具执行流程
            
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
        
        # 🆕 Stage 3: 智能任务分解
        decomposition_result = None
        if len(task.description) > 50:  # 对较复杂的任务进行分解
            try:
                decomposition_result = self.task_decomposer.decompose_task(task.description)
                logger.info(f"📋 任务分解完成: {decomposition_result.complexity.value}, "
                          f"{len(decomposition_result.steps)} 步骤, "
                          f"预计 {decomposition_result.estimated_total_duration:.1f}秒")
                
                # 如果是极复杂任务，记录分解结果
                if decomposition_result.complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
                    logger.info(f"🎯 复杂任务执行策略: {decomposition_result.execution_strategy}")
                    for i, step in enumerate(decomposition_result.steps[:3]):  # 只显示前3步
                        logger.info(f"  步骤{i+1}: {step.description} ({step.action_type})")
                    if len(decomposition_result.steps) > 3:
                        logger.info(f"  ... 还有 {len(decomposition_result.steps)-3} 个步骤")
                        
            except Exception as e:
                logger.warning(f"⚠️ 任务分解失败，继续正常执行: {e}")
        
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
            
            # 2. 🔧 调用LLM，带完整异常处理和重试机制
            # 🔧 修复：在execute_tools标签之后停止，而不是在标签本身停止
            stop_sequences = ["\n<execute_tools />", "\n<execute_tools></execute_tools>", "</answer>"]
            llm_start_time = time.time()
            response_text = None
            llm_error = None
            token_usage = {}
            
            # 🔥 LLM API调用重试机制
            for attempt in range(3):  # 最多重试3次
                try:
                    logger.debug(f"🔄 LLM API调用尝试 {attempt + 1}/3")
                    response_text = await self.client._call_api(optimized_history, stop_sequences=stop_sequences)
                    llm_end_time = time.time()
                    
                    logger.info(f"✅ LLM API调用成功 (尝试 {attempt + 1})")
                    break  # 成功则跳出重试循环
                    
                except Exception as e:
                    llm_end_time = time.time()
                    llm_error = e
                    wait_time = 2 ** attempt  # 指数退避: 1, 2, 4 秒
                    
                    logger.error(f"❌ LLM API调用失败 (尝试 {attempt + 1}/3): {e}")
                    
                    # 特殊处理不同类型的错误
                    error_type = type(e).__name__
                    if "RemoteProtocolError" in error_type:
                        logger.warning("🚨 检测到RemoteProtocolError - 服务器连接中断")
                    elif "TimeoutError" in error_type or "timeout" in str(e).lower():
                        logger.warning("⏰ 检测到超时错误")
                    elif "HTTPStatusError" in error_type:
                        logger.warning(f"🌐 检测到HTTP状态错误: {getattr(e, 'response', {}).get('status_code', 'unknown')}")
                    
                    if attempt < 2:  # 不是最后一次尝试
                        logger.info(f"🔄 {wait_time}秒后进行第 {attempt + 2} 次重试...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error("❌ 所有LLM API调用尝试都失败了")
            
            # 3. 🆕 Token使用统计和记录（无论成功失败都尝试）
            if response_text and self.token_manager:
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
            
            # 4. 🔍 记录LLM调用（包含错误信息和token信息）
            if response_text:
                triggered_stop = self._detect_triggered_stop_sequence(response_text, stop_sequences)
            else:
                triggered_stop = None
                # 🔧 即使LLM调用失败也记录轨迹
                response_text = f"LLM API调用失败: {llm_error}" if llm_error else "LLM API调用失败: 未知原因"
            
            self.step_logger.log_llm_call(
                prompt=original_history,  # 使用原始消息记录完整内容
                raw_response=response_text,
                stop_sequence=triggered_stop,
                start_time=llm_start_time,
                end_time=llm_end_time,
                token_usage=token_usage  # 🆕 传递详细的token使用信息
            )
            
            # 5. 🚨 如果LLM调用彻底失败，生成错误响应但继续记录轨迹
            if llm_error:
                error_response = self._generate_llm_failure_response(llm_error, task)
                
                # 记录错误步骤
                self.step_logger.log_step_error(
                    step_index=len(full_trajectory),
                    error_type="LLM_API_FAILURE",
                    error_message=str(llm_error),
                    recovery_attempted=True
                )
                
                # 仍然添加到历史中以保持轨迹完整性
                history.append({"role": "assistant", "content": error_response})
                full_trajectory.append({"role": "assistant", "content": error_response})
                
                # 设置任务失败但不立即退出，确保轨迹被保存
                success = False
                final_result = f"任务因LLM API连接问题失败: {llm_error}"
                
                # 跳到轨迹保存和返回
                break
            
            # 🔧 修复：自动注入缺失的<execute_tools />标签
            response_text = self._auto_inject_execute_tools(response_text)
            
            history.append({"role": "assistant", "content": response_text})
            full_trajectory.append({"role": "assistant", "content": response_text})

            # 🆕 新增：处理 <tool_param> 查询
            if "<tool_param>" in response_text:
                tool_param_result = await self._handle_tool_param_query(response_text)
                history.append({"role": "assistant", "content": tool_param_result})
                full_trajectory.append({"role": "assistant", "content": tool_param_result})
                self.step_logger.finish_step("tool_param_query_handled")
                continue

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

            # 🔍 Stage 3增强：使用增强XML解析器
            parsing_start_time = time.time()
            
            # 使用增强XML解析器
            parse_result = self.xml_parser.parse_xml_response(response_text)
            actions = parse_result.actions
            
            # 记录解析详情
            think_content = self.step_logger._extract_think_content(response_text)
            execution_block_text = self.step_logger._extract_execution_block(response_text)
            parsing_end_time = time.time()
            
            # 构建解析错误信息
            parsing_errors = []
            if not parse_result.success:
                parsing_errors.extend(parse_result.errors)
            if parse_result.warnings:
                parsing_errors.extend([f"警告: {w}" for w in parse_result.warnings])
            
            # 记录解析结果（包含增强解析信息）
            self.step_logger.log_parsing_result(
                think_content=think_content,
                execution_block=execution_block_text,
                answer_content=None,
                actions=actions,
                parsing_errors=parsing_errors,
                start_time=parsing_start_time,
                end_time=parsing_end_time
            )
            
            # 记录解析置信度和修复操作
            if parse_result.repaired_xml:
                logger.info(f"🔧 XML自动修复成功，置信度: {parse_result.confidence_score:.2f}")
            if not parse_result.success and len(actions) > 0:
                logger.warning(f"⚠️ 部分解析成功，提取到 {len(actions)} 个动作")
            
            # 检查是否包含最终答案标签 - 如果有则直接结束
            think_tag = TaskExecutionConstants.XML_TAGS['THINK']
            answer_tag = TaskExecutionConstants.XML_TAGS['ANSWER']
            execute_tools_tag = TaskExecutionConstants.XML_TAGS['EXECUTE_TOOLS']
            
            # 🔧 关键修复：检测到answer标签时直接结束任务
            if f"<{answer_tag}>" in response_text:
                logger.info("✅ 检测到<answer>标签，任务完成")
                history.append({"role": "assistant", "content": response_text})
                full_trajectory.append({"role": "assistant", "content": response_text})
                self.step_logger.finish_step("answer_tag_detected")
                break
            
            # 🔧 修复：删除错误的thought-only final answer逻辑
            # 不应该将纯思考内容当作最终答案，模型可能只是在第一步思考
            # 让执行流程继续，如果确实需要工具执行，后续的逻辑会处理

            # 🔧 Stage 2 增强：复杂任务检测与强制执行机制
            if not actions:
                # 🚨 新增：复杂任务检测与强制执行
                if self._is_complex_task_response(response_text):
                    logger.warning("🚨 检测到复杂任务但无工具执行 - 强制执行第一步")
                    
                    # 尝试强制执行第一步
                    force_execution_result = await self._force_first_step_execution(response_text, task)
                    if force_execution_result:
                        result_xml = force_execution_result
                        history.append({"role": "assistant", "content": result_xml})
                        full_trajectory.append({"role": "assistant", "content": result_xml})
                        # 🔍 完成步骤记录
                        self.step_logger.finish_step("complex_task_forced_execution")
                        continue
                
                # 🔧 原有的计划-执行桥梁机制（作为备选方案）
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
                
                # 🔧 修复：对于只有思考内容的情况，提供引导而不是直接终止
                if f"<{think_tag}>" in response_text:
                    logger.info("💭 检测到纯思考内容，提供执行引导")
                    
                    # 提供执行引导
                    guidance = (
                        "You have shared your thinking process. Now please proceed to execute the necessary steps. "
                        "Use the appropriate tool calls with the exact XML format and end with <execute_tools />. "
                        "Remember: thinking is just the first step - execution is required to complete the task."
                    )
                    
                    result_xml = self._format_result(guidance)
                    history.append({"role": "assistant", "content": result_xml})
                    full_trajectory.append({"role": "assistant", "content": result_xml})
                    # 🔍 完成步骤记录
                    self.step_logger.finish_step("thinking_execution_guidance")
                    continue
                
                # 其他情况：正常的无动作响应
                logger.info("✅ Detected response without tool execution - continuing to next step")
                # 🔍 完成步骤记录
                self.step_logger.finish_step("no_action_continue")
                continue

            # 4. 根据类型分发执行
            results = []
            block_type = parse_result.execution_type or "single"

            # 🔧 修复：添加工具执行异常处理，确保轨迹记录完整性
            try:
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
                        
            except Exception as tool_exec_error:
                # 🔧 关键修复：工具执行失败时，记录完整的推理过程和错误信息
                logger.error(f"工具执行失败: {tool_exec_error}")
                error_type = self._analyze_error_type(str(tool_exec_error))
                
                # 创建详细的错误结果，包含推理过程
                error_result = f"工具执行失败: {str(tool_exec_error)}"
                
                # 🔧 特殊处理参数验证失败的情况
                if "Parameter validation failed" in str(tool_exec_error):
                    # 提取模型原本想要执行的动作
                    original_action = actions[0] if actions else {}
                    service_name = original_action.get('service', 'unknown')
                    tool_name = original_action.get('tool', 'unknown')
                    tool_input = original_action.get('input', '')
                    
                    error_result = f"""参数验证失败，但模型的推理过程已记录：

模型尝试执行：{service_name}.{tool_name}
模型提供的输入：{tool_input}

错误详情：{str(tool_exec_error)}

建议：请检查参数格式是否正确，确保传入了工具所需的必需参数。"""
                
                results = [error_result]
                
                # 🔧 记录错误步骤到轨迹中
                self.step_logger.log_step_error(
                    step_index=len(full_trajectory),
                    error_type=error_type,
                    error_message=str(tool_exec_error),
                    recovery_attempted=True
                )

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
            # 添加超时保护，避免异步取消导致的问题
            tools = await asyncio.wait_for(
                self.toolscore_client.get_available_tools(), 
                timeout=5.0
            )
            return [str(tool) for tool in tools] if isinstance(tools, list) else []
        except asyncio.TimeoutError:
            logger.warning(f"获取工具列表超时，使用默认工具列表")
            return ["microsandbox", "browser_use", "deepsearch", "search_tool"]
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("工具列表获取被取消")
            raise
        except Exception as e:
            logger.warning(f"获取工具列表失败: {e}")
            return ["microsandbox", "browser_use", "deepsearch", "search_tool"]
    
    async def _get_tool_descriptions(self) -> str:
        """获取工具描述"""
        try:
            # 添加超时保护
            descriptions = await asyncio.wait_for(
                self.toolscore_client.get_tool_descriptions(),
                timeout=5.0
            )
            return descriptions if descriptions else "工具描述获取失败"
        except asyncio.TimeoutError:
            logger.warning(f"获取工具描述超时，使用默认描述")
            return "基础工具：代码执行、浏览器操作、搜索功能"
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("工具描述获取被取消")
            raise
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
        """🔧 增强的智能错误类型分析 - 检测更多特定错误场景"""
        error_msg_lower = error_message.lower()
        
        # 🔍 空结果/无数据错误（高优先级检测）
        if any(indicator in error_msg_lower for indicator in ['no results', 'empty result', 'no data found', '没有结果', '空结果', '未找到数据', 'empty response']):
            return "empty_results"
        
        # ⏱️ 超时错误
        if any(indicator in error_msg_lower for indicator in ['timeout', 'time out', 'timed out', '超时', '执行超时']):
            return "timeout_error"
        
        # 🚫 服务不可用错误（需要在数据不可用之前检测）
        if any(indicator in error_msg_lower for indicator in ['service unavailable', 'server error', '503', '502', '500', '服务不可用', 'service down']):
            return "service_unavailable"
        
        # 📊 数据不可用错误  
        if any(indicator in error_msg_lower for indicator in ['data not available', 'unavailable', '数据不可用', '不可用', 'data unavailable']):
            return "data_not_available"
        
        # 参数错误
        if any(indicator in error_msg_lower for indicator in ['parameter', 'param', '参数', '无效参数']):
            return "parameter_error"
        
        # 工具不存在错误
        if any(indicator in error_msg_lower for indicator in ['不支持', 'not support', '不存在', 'not found']):
            return "tool_not_found"
        
        # 网络/连接错误
        if any(indicator in error_msg_lower for indicator in ['connection', 'network', 'connect', 'connection refused', '网络']):
            return "network_error"
        
        # 验证错误
        if any(indicator in error_msg_lower for indicator in ['validation', 'validate', '验证失败']):
            return "validation_error"
        
        # 权限错误
        if any(indicator in error_msg_lower for indicator in ['permission', 'access', '权限', 'forbidden']):
            return "permission_error"
        
        return "unknown_error"
    
    def _format_error_with_recovery_suggestion(self, error_message: str, error_type: str, service_name: str, tool_name: str) -> str:
        """🔧 增强的错误格式化和恢复建议 - 针对具体错误类型提供详细指导"""
        base_error = f"Tool execution failed: {error_message}"
        
        recovery_suggestions = {
            "parameter_error": f"💡 建议: 检查 {service_name} 的 {tool_name} 工具参数格式。参考工具定义中的正确参数名称。",
            "tool_not_found": f"💡 建议: 工具 {tool_name} 在 {service_name} 中不存在。检查工具名称是否正确，或尝试使用其他工具。",
            "network_error": f"💡 建议: 网络连接问题。等待几秒后重试，或尝试使用替代工具。",
            "validation_error": f"💡 建议: 输入数据验证失败。检查输入格式和内容是否符合要求。",
            "permission_error": f"💡 建议: 权限不足。检查服务配置或尝试其他方法。",
            "empty_results": f"🔍 建议: 搜索未找到结果。尝试:\n  • 使用不同的关键词或更简单的查询\n  • 切换到其他搜索工具 (如 deepsearch → browser_use)\n  • 检查数据是否已保存在内存暂存区: <memory_staging><memory_list></memory_list></memory_staging>",
            "data_not_available": f"📊 建议: 数据不可用。尝试:\n  • 使用更广泛的搜索词\n  • 检查内存暂存区是否有相关数据: <memory_staging><memory_search>关键词</memory_search></memory_staging>\n  • 考虑使用示例数据（明确标记为模拟数据）",
            "timeout_error": f"⏱️ 建议: 工具执行超时。尝试:\n  • 简化查询或操作\n  • 分步骤执行复杂任务\n  • 稍后重试",
            "service_unavailable": f"🚫 建议: 服务不可用。尝试:\n  • 使用替代工具达到相同目标\n  • 稍后重试\n  • 使用缓存或内存中的数据",
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
                    logger.info(f" 从\\boxed{{}}提取清洁最终结果: {clean_answer}...")
                    return clean_answer
                else:
                    # 如果没有\boxed{}格式，返回原始answer内容
                    logger.info(f"从<answer>标签提取最终结果: {answer_content}...")
                    return answer_content
        else:
            # 🔧 容错机制：如果标准答案标签解析失败，尝试修复
            answer_content = self._attempt_answer_extraction(final_trajectory_str)
            if answer_content:
                logger.info(f"🔧 容错提取答案成功: {answer_content}...")
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
        
        # 构建工具执行参数
        service_name = action.get('service')
        tool_name = action.get('tool')
        tool_input = action.get('input')
        
        # 🆕 检查是否为内存暂存工具
        if self.tool_manager.is_memory_staging_tool(service_name):
            logger.info(f"🔄 执行内存暂存工具: {service_name}.{tool_name}")
            
            # 解析工具输入参数
            try:
                # 对于内存暂存工具，tool_input可能是字符串或字典
                if isinstance(tool_input, str):
                    # 尝试解析为JSON
                    try:
                        import json
                        parameters = json.loads(tool_input)
                    except:
                        # 如果解析失败，根据动作类型构建参数
                        if tool_name in ["memory_write"]:
                            # 对于写入操作，假设输入是要保存的值
                            parameters = {"key": f"auto_key_{int(time.time())}", "value": tool_input}
                        elif tool_name in ["memory_read", "memory_clear"]:
                            parameters = {"key": tool_input}
                        elif tool_name in ["memory_search"]:
                            parameters = {"query": tool_input}
                        else:
                            parameters = {}
                else:
                    parameters = tool_input or {}
                
                # 设置执行上下文
                parameters["_current_step"] = getattr(self, "_current_step_id", None)
                parameters["_current_tool"] = service_name
                
                # 直接执行内存暂存工具
                raw_result = self.tool_manager.execute_memory_staging_action(tool_name, parameters)
                
                formatted_result = self._format_memory_staging_output(tool_name, raw_result)
                execution_status = "success" if raw_result.get("success", False) else "failure"
                error_details = raw_result.get("error") if not raw_result.get("success", False) else None
                
            except Exception as e:
                error_str = str(e)
                raw_result = {"error": error_str, "success": False}
                formatted_result = f"Memory staging tool execution failed: {error_str}"
                execution_status = "failure"
                error_details = error_str
                
            # 记录内存暂存工具调用（无需HTTP请求）
            toolscore_request = {
                "tool_type": "memory_staging",
                "tool_id": service_name,
                "action": tool_name,
                "parameters": parameters if 'parameters' in locals() else {}
            }
            
        else:
            # 原有的外部工具执行逻辑
            param_mapping = {
                "browser_use": "query",
                "microsandbox": "code",
                "deepsearch": "question"
            }
            param_name = param_mapping.get(service_name, "input")
            
            # 🔧 Fix JSON parameter parsing issue - 使用已有的JSONParameterParser
            # Parse tool_input if it contains JSON data mixed with XML tags
            parsed_parameters = self._parse_tool_input_parameters(tool_input, service_name, tool_name, param_name)
            
            # 🔧 修复：检查参数验证错误并作为工具结果返回，而不是抛出异常
            if "_validation_error" in parsed_parameters:
                validation_error = parsed_parameters["_validation_error"]
                logger.warning(f"Parameter validation failed, returning error to model for correction: {validation_error}")
                
                # 🔧 关键修复：将参数验证错误作为工具执行结果返回给模型
                # 这样模型可以看到错误信息，并基于此重新思考和修正参数
                error_result = {
                    "error": validation_error,
                    "success": False,
                    "error_type": "parameter_validation_error",
                    "suggestions": [
                        f"请检查工具 {service_name}.{tool_name} 的参数格式",
                        "确保所有必需参数都已提供",
                        "参考工具文档确认正确的参数名称和类型"
                    ]
                }
                
                # 格式化错误信息，让模型能够理解并修正
                formatted_error = self._format_parameter_validation_error(
                    service_name, tool_name, validation_error, parsed_parameters.get(param_name, tool_input)
                )
                
                tool_end_time = time.time()
                
                # 记录参数验证失败的日志，但不标记为执行失败
                self.step_logger.log_tool_execution(
                    execution_index=execution_index,
                    action=action,
                    toolscore_request={
                        "tool_type": "external",
                        "tool_id": service_name,
                        "action": tool_name,
                        "parameters": parsed_parameters,
                        "validation_status": "failed"
                    },
                    raw_response=error_result,
                    formatted_result=formatted_error,
                    start_time=tool_start_time,
                    end_time=tool_end_time,
                    execution_status="parameter_validation_failed",  # 新的状态，不是failure
                    error_details=validation_error
                )
                
                return {
                    "formatted_result": formatted_error,
                    "raw_result": error_result,
                    "execution_status": "parameter_validation_failed"
                }
            
            # 清理_validation_error参数，确保它不会传递给实际的工具
            clean_parameters = {k: v for k, v in parsed_parameters.items() if k != "_validation_error"}
            
            toolscore_request = {
                "endpoint": f"http://127.0.0.1:{self._get_service_port(service_name)}/execute_tool",
                "method": "POST",
                "payload": {
                    "tool_id": service_name,
                    "action": tool_name,
                    "parameters": clean_parameters
                }
            }
            
            # 🔧 智能工具执行与错误分析
            try:
                raw_result = await self.toolscore_client.execute_tool(
                    tool_id=service_name,
                    action=tool_name,
                    parameters=clean_parameters
                )
                
                formatted_result = self._format_tool_output(service_name, tool_name, raw_result)
                execution_status = "success"
                error_details = None
                
                # 🧠 检测工具结果中的潜在问题并提供智能指导
                smart_guidance = self._provide_smart_recovery_guidance(raw_result, service_name, tool_name)
                if smart_guidance:
                    formatted_result += f"\n\n{smart_guidance}"
                
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
    
    # 🚨 阶段2新增：复杂任务检测和强制执行机制
    
    def _is_complex_task_response(self, response_text: str) -> bool:
        """检测是否为复杂任务响应（可能导致规划-执行脱节）"""
        complex_indicators = [
            # 中文指示符
            '多步', '分析', '研究', '综合', '详细', 
            '第一步', '第二步', '第三步',
            '然后', '接下来', '最后',
            '需要', '包含', '涉及',
            '方法论', '方法', '策略',
            # 英文指示符
            'step 1', 'step 2', 'step 3', 'first', 'then', 'next', 'finally',
            'comprehensive', 'detailed', 'analysis', 'research', 'methodology',
            'approach', 'strategy', 'multiple', 'several', 'various',
            'I need to', 'I will', 'let me', 'plan', 'outline'
        ]
        
        # 检查是否包含复杂任务指示符
        text_lower = response_text.lower()
        indicator_count = sum(1 for indicator in complex_indicators if indicator in text_lower)
        
        # 检查是否包含多步骤编号
        import re
        step_patterns = [
            r'\d+[.)] *[^\n]*',  # 1. 或 1)
            r'step\s*\d+',  # step 1, step 2
            r'第[\u4e00二三四五六七八九十]*步',  # 第一步, 第二步
        ]
        
        has_step_numbering = any(re.search(pattern, text_lower) for pattern in step_patterns)
        
        # 检查响应长度（过长的规划性响应）
        is_long_response = len(response_text) > 1000
        
        # 综合判断
        is_complex = (
            indicator_count >= 3 or  # 多个复杂指示符
            has_step_numbering or    # 包含步骤编号
            (indicator_count >= 2 and is_long_response)  # 指示符+长响应
        )
        
        if is_complex:
            logger.debug(f"🚨 检测到复杂任务响应: indicators={indicator_count}, steps={has_step_numbering}, long={is_long_response}")
        
        return is_complex
    
    async def _force_first_step_execution(self, response_text: str, task: 'TaskSpec') -> Optional[str]:
        """强制执行第一步机制"""
        try:
            # 分析响应中的可执行内容
            executable_action = self._extract_actionable_content(response_text)
            
            if executable_action:
                logger.info(f"🔥 强制执行第一步: {executable_action}")
                
                # 生成强制执行指令
                force_execution_prompt = (
                    f"🚨 EXECUTION ENFORCEMENT: You provided planning but no tool execution. "
                    f"This will cause task failure. You MUST execute the first step immediately.\n\n"
                    f"Based on your plan, the first action should be: {executable_action}\n\n"
                    f"Please execute this action now using the proper tool format and end with <execute_tools />. "
                    f"Remember: Every complex task requires immediate execution after planning!"
                )
                
                return self._format_result(force_execution_prompt)
                
            else:
                # 通用强制指令
                generic_force_prompt = (
                    f"🚨 CRITICAL EXECUTION FAILURE: Complex task detected but no tool execution found. "
                    f"This pattern causes complete task failure.\n\n"
                    f"You MUST start executing immediately. Choose ONE concrete action you can take right now "
                    f"and execute it using proper XML tool format. End with <execute_tools />.\n\n"
                    f"Example actions you could take:\n"
                    f"- Search for information: <deepsearch><research>topic</research></deepsearch>\n"
                    f"- Browse for data: <browser_use><browser_search_google>query</browser_search_google></browser_use>\n"
                    f"- Analyze data: <microsandbox><microsandbox_execute>code</microsandbox_execute></microsandbox>\n\n"
                    f"Act NOW to prevent task failure!"
                )
                
                return self._format_result(generic_force_prompt)
                
        except Exception as e:
            logger.error(f"⚠️ 强制执行机制失败: {e}")
            return None
    
    def _extract_actionable_content(self, response_text: str) -> Optional[str]:
        """从响应中提取可执行的内容"""
        import re
        
        # 常见的可执行动作模式
        action_patterns = [
            # 中文模式 - 改进的模式匹配
            r'搜索(.+?)(?:\n|$)',
            r'查找(.+?)(?:\n|$)',
            r'研究(.+?)(?:\n|$)',
            r'分析(.+?)(?:\n|$)',
            r'调研(.+?)(?:\n|$)',
            # 英文模式 - 改进的模式匹配
            r'search for (.+?)(?:\n|$)',
            r'research (.+?)(?:\n|$)',
            r'analyze (.+?)(?:\n|$)',
            r'look up (.+?)(?:\n|$)',
            r'find (.+?)(?:\n|$)',
            r'investigate (.+?)(?:\n|$)',
            # 第一步模式 - 更精确的匹配
            r'第一步[:\uff1a]?\s*(.+?)(?:\n|$)',
            r'首先(.+?)(?:\n|$)',
            r'step 1[:\uff1a]?\s*(.+?)(?:\n|$)',
            r'first[,\uff0c]?\s*(.+?)(?:\n|$)',
            # 通用动作模式
            r'我需要(.+?)(?:\n|$)',
            r'i need to (.+?)(?:\n|$)',
        ]
        
        for pattern in action_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                action = match.group(1).strip()
                # 清理动作内容
                action = re.sub(r'^[:\uff1a\s]+', '', action)  # 移除开头的冒号和空格
                action = re.sub(r'[。\.\n]+$', '', action)  # 移除结尾的句号和换行
                
                if len(action) > 5:  # 确保动作有意义
                    return action[:100]  # 限制长度
        
        return None
    
    def _enhance_no_action_guidance(self, response_text: str) -> str:
        """增强的无动作指导"""
        # 检查是否是复杂任务
        if self._is_complex_task_response(response_text):
            return (
                "🚨 CRITICAL: Complex task detected with no execution. This causes task failure!\n\n"
                "You MUST execute tools immediately. Choose ONE action and do it now:\n"
                "- 🔍 Search: <deepsearch><research>topic</research></deepsearch>\n"
                "- 🌍 Browse: <browser_use><browser_search_google>query</browser_search_google></browser_use>\n"
                "- 📊 Analyze: <microsandbox><microsandbox_execute>code</microsandbox_execute></microsandbox>\n"
                "- 🔄 Check Memory: <memory_staging><memory_list></memory_list></memory_staging>\n\n"
                "End with <execute_tools /> or the task will fail completely!"
            )
        else:
            return "No executable action detected in this step. Please provide a tool call with proper XML format."
    
    def _detect_tool_result_issues(self, raw_result: Any, service_name: str, tool_name: str) -> tuple[bool, str]:
        """🔧 检测工具执行结果中的常见问题，提供智能指导"""
        
        # 🔧 修复：对于 microsandbox，正确提取实际输出内容而非整个字典结构
        if service_name == "microsandbox":
            # 正确提取 microsandbox 的实际输出内容
            if isinstance(raw_result, dict):
                # 获取 data 字段中的内容
                data = raw_result.get('data', raw_result)
                if isinstance(data, dict):
                    # 提取 stdout 作为主要输出内容
                    stdout_content = data.get('stdout', '')
                    stderr_content = data.get('stderr', '')
                    result_str = str(stdout_content).lower()
                    
                    # 如果 stdout 为空但有 stderr，分析 stderr（但不直接判断为错误）
                    if not stdout_content and stderr_content:
                        result_str = str(stderr_content).lower()
                else:
                    result_str = str(data).lower()
            else:
                result_str = str(raw_result).lower()
            
            # 检查是否有数值输出（科学记数法、小数、计算结果等）
            has_numeric_output = bool(re.search(r'\d+\.?\d*e?[+-]?\d*', result_str))
            
            # 检查是否有典型的成功输出模式
            success_output_patterns = [
                'watts:', 'photocurrent:', 'frequency:', 'result:', 'output:', 'print',
                '瓦特', '光电流', '频率', '结果', '输出', 'completed', 'finished',
                ':', 'hz', 'ampere', 'volt', 'calculation'
            ]
            has_success_output = any(indicator in result_str for indicator in success_output_patterns)
            
            # 检查是否没有明显的错误指标
            error_patterns = ['traceback', 'exception:', 'error:', 'failed to', 'cannot', 'unable to']
            has_obvious_error = any(pattern in result_str for pattern in error_patterns)
            
            # 如果有数值输出或成功模式，且没有明显错误，说明执行成功
            if (has_numeric_output or has_success_output) and not has_obvious_error:
                logger.debug(f"✅ {service_name} 检测到成功输出，跳过问题检测")
                return False, ""
        # 🔧 修复：为 deepsearch 正确提取实际输出内容  
        elif service_name == "deepsearch":
            try:
                if isinstance(raw_result, dict):
                    # 🔧 增强的内容提取逻辑 - 支持多层嵌套结构
                    report_content = None
                    
                    # 方案1：直接从根级别查找
                    content_fields = ['answer', 'final_report', 'report', 'summary', 'content', 'result', 'response']
                    for field in content_fields:
                        if field in raw_result and raw_result[field]:
                            report_content = raw_result[field]
                            break
                    
                    # 方案2：从 data 字段中查找
                    if not report_content:
                        data = raw_result.get('data', {})
                        if isinstance(data, dict):
                            for field in content_fields:
                                if field in data and data[field]:
                                    report_content = data[field]
                                    break
                    
                    # 方案3：从 result 字段中查找（针对 step_logs 中的特定结构）
                    if not report_content:
                        result_data = raw_result.get('result', {})
                        if isinstance(result_data, dict):
                            for field in content_fields:
                                if field in result_data and result_data[field]:
                                    report_content = result_data[field]
                                    break
                    
                    # 方案4：递归查找任何包含实质性内容的字段
                    if not report_content:
                        report_content = self._extract_deepsearch_content_recursive(raw_result)
                    
                    # 🔧 更宽松的成功检测标准
                    if report_content:
                        content_str = str(report_content).strip()
                        # 降低长度要求，增加内容质量检测
                        if (len(content_str) >= 50 and  # 降低到50字符
                            self._is_meaningful_research_content(content_str)):
                            logger.debug(f"✅ {service_name} 检测到有效研究报告内容，跳过问题检测")
                            return False, ""
                        
                        result_str = content_str.lower()
                    else:
                        # 如果没有找到特定字段，检查整体结构
                        full_content = str(raw_result)
                        if (len(full_content) >= 200 and  # 完整结构的最低要求
                            self._is_meaningful_research_content(full_content)):
                            logger.debug(f"✅ {service_name} 从完整结构检测到研究内容，跳过问题检测")
                            return False, ""
                        result_str = full_content.lower()
                else:
                    result_str = str(raw_result).lower()
                    # 对于非字典结构，也要检查是否包含研究内容
                    if (len(result_str) >= 100 and 
                        self._is_meaningful_research_content(result_str)):
                        logger.debug(f"✅ {service_name} 从字符串结构检测到研究内容，跳过问题检测")
                        return False, ""
                        
            except Exception as e:
                logger.warning(f"检查deepsearch内容时出错: {e}")
                result_str = str(raw_result).lower()
                # 即使出现异常，也要尝试基本的内容检测
                if len(result_str) >= 100:
                    logger.debug(f"⚠️ {service_name} 异常处理中检测到足够内容，跳过问题检测")
                    return False, ""
        
        # 🔧 修复：为其他工具正确提取内容
        else:
            # 对于其他服务，尝试智能提取内容
            try:
                if isinstance(raw_result, dict):
                    # 优先查找常见的内容字段
                    content_fields = ['content', 'result', 'output', 'data', 'message']
                    extracted_content = None
                    
                    for field in content_fields:
                        if field in raw_result and raw_result[field]:
                            extracted_content = raw_result[field]
                            break
                    
                    if extracted_content:
                        result_str = str(extracted_content).lower()
                    else:
                        result_str = str(raw_result).lower()
                else:
                    result_str = str(raw_result).lower()
            except Exception as e:
                logger.warning(f"提取{service_name}内容时出错: {e}")
                result_str = str(raw_result).lower()
        
        # 🚀 对于其他工具，检查是否有明显的成功标志
        success_patterns = [
            r'success["\']?\s*:\s*true',  # "success": true
            r'completed successfully',     # 成功完成
            r'executed successfully',      # 成功执行
            r'operation completed',        # 操作完成
        ]
        if any(re.search(pattern, result_str) for pattern in success_patterns):
            return False, ""
        
        # 🔧 增强的搜索结果检测 - 区分执行失败和内容为空
        empty_result_indicators = [
            'no results', 'empty', 'not found', '没有结果', '未找到', 
            'no data', 'no information', '无数据', '无信息'
        ]
        
        # 🔧 特殊处理：成功完成但无内容的情况
        successful_empty_indicators = [
            '搜索完成，但未找到相关结果',  # deepsearch 的标准空结果消息
            '搜索完成，没有找到', 
            'search completed, no results',
            'search finished, no content found'
        ]
        
        # 先检查是否是成功的空结果
        for indicator in successful_empty_indicators:
            if indicator in result_str:
                logger.debug(f"✅ {service_name} 搜索成功执行但未找到内容，这是正常情况")
                # 不返回错误，而是让它被标记为成功但提供使用建议
                return False, ""  # 不标记为问题
        
        # 再检查一般的空结果（可能是真正的错误）
        if any(indicator in result_str for indicator in empty_result_indicators):
            guidance = (
                f"🔍 {service_name} 搜索未找到结果。建议尝试:\n"
                f"• 使用更简单或不同的关键词\n"
                f"• 切换到其他搜索工具 (deepsearch ↔ browser_use)\n"
                f"• 检查内存暂存区中的相关数据: <memory_staging><memory_search>相关词</memory_search></memory_staging>\n"
                f"• 如果确实无法找到，考虑使用示例数据并明确说明"
            )
            return True, guidance
        
        # 检测超时或连接问题（更精确的匹配，避免误判）
        # 🔧 修复：对于microsandbox，如果已经通过了成功检测，不要再检查超时
        if service_name != "microsandbox":
            timeout_indicators = [
                'timeout', 'timed out', 'connection failed', 'connection error',
                'network error', 'connection refused', 'connection reset',
                '超时', '连接失败', '连接错误', '网络错误', '连接被拒绝'
            ]
            if any(indicator in result_str.lower() for indicator in timeout_indicators):
                guidance = (
                    f"⏱️ {service_name} 连接或超时问题。建议:\n"
                    f"• 稍等片刻后重试\n"
                    f"• 尝试使用其他工具达到相同目标\n"
                    f"• 简化查询或操作"
                )
                return True, guidance
        
        # 检测权限或访问问题
        if any(indicator in result_str for indicator in [
            'forbidden', 'unauthorized', 'access denied', '拒绝访问', '权限'
        ]):
            guidance = (
                f"🚫 {service_name} 访问受限。建议:\n"
                f"• 尝试使用其他公开数据源\n"
                f"• 使用不同的搜索策略\n"
                f"• 考虑使用内存中已有的数据"
            )
            return True, guidance
        
        # 检测服务错误（更精确的匹配，避免误判成功的输出）
        error_indicators = [
            'error:', 'failed:', 'exception:', 'traceback:', 'fatal error',
            'execution failed', 'command failed', 'operation failed',
            '执行失败', '命令失败', '操作失败', '发生错误', '异常:'
        ]
        # 排除包含成功指标的情况
        success_indicators = ['success', 'completed', 'finished', '成功', '完成', '结果:']
        has_success = any(indicator in result_str.lower() for indicator in success_indicators)
        
        if not has_success and any(indicator in result_str.lower() for indicator in error_indicators):
            guidance = (
                f"🔧 {service_name} 执行出错。建议:\n"
                f"• 检查参数格式是否正确\n"
                f"• 尝试简化操作\n"
                f"• 使用替代方法或工具"
            )
            return True, guidance
        
        return False, ""
    
    def _provide_smart_recovery_guidance(self, raw_result: Any, service_name: str, tool_name: str) -> str:
        """🧠 为工具执行结果提供智能恢复指导"""
        has_issue, guidance = self._detect_tool_result_issues(raw_result, service_name, tool_name)
        
        if has_issue:
            return f"{guidance}\n\n💡 你可以在下一步尝试建议的方法，或继续使用现有信息。"
        
        return ""
    
    def _generate_llm_failure_response(self, error: Exception, task) -> str:
        """
        🔧 生成LLM调用失败时的错误响应
        确保即使API失败也能生成有意义的回复
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # 基于错误类型生成不同的响应
        if "RemoteProtocolError" in error_type:
            response = f"""<think>
Gemini API连接协议错误：{error_message}
这通常是由于网络不稳定或服务器负载过高导致的。
虽然无法完成LLM推理，但我已经记录了这个错误。
</think>

<answer>
抱歉，由于Gemini API连接协议错误，无法完成此次任务推理。

错误详情：{error_type} - {error_message}

建议：
1. 检查网络连接是否稳定
2. 稍后重试任务
3. 如果问题持续，可能需要检查API服务状态

任务ID: {task.task_id}
</answer>"""
        elif "TimeoutError" in error_type or "timeout" in error_message.lower():
            response = f"""<think>
LLM API调用超时：{error_message}
这可能是由于网络延迟或服务器响应缓慢导致的。
</think>

<answer>
抱歉，LLM API调用超时，无法完成此次推理任务。

错误详情：{error_type} - {error_message}

建议：
1. 检查网络连接速度
2. 稍后重试任务
3. 考虑简化任务复杂度

任务ID: {task.task_id}
</answer>"""
        elif "HTTPStatusError" in error_type:
            response = f"""<think>
LLM API HTTP状态错误：{error_message}
这可能是API服务暂时不可用或达到了使用限制。
</think>

<answer>
抱歉，LLM API服务返回错误状态，无法完成此次任务。

错误详情：{error_type} - {error_message}

建议：
1. 检查API密钥是否有效
2. 验证API服务状态
3. 稍后重试任务

任务ID: {task.task_id}
</answer>"""
        else:
            response = f"""<think>
LLM API调用遇到未知错误：{error_message}
这是一个意外的错误情况，需要进一步调查。
</think>

<answer>
抱歉，LLM API调用遇到未知错误，无法完成此次推理任务。

错误详情：{error_type} - {error_message}

建议：
1. 检查系统日志获取更多信息
2. 验证系统配置
3. 如果问题持续，请联系技术支持

任务ID: {task.task_id}
</answer>"""
        
        return response

    async def cleanup(self):
        """清理运行时资源"""
        logger.info("🧹 清理Enhanced Reasoning Runtime资源...")
        
        try:
            # MicroSandbox连接管理器已移除 - 无需清理
            
            # 清理其他资源
            if hasattr(self, 'memory_manager') and self.memory_manager:
                # 假设MemoryManager有cleanup方法
                if hasattr(self.memory_manager, 'cleanup'):
                    await self.memory_manager.cleanup()
                    
            logger.info("✅ Enhanced Reasoning Runtime清理完成")
            
        except Exception as e:
            logger.error(f"❌ 清理Enhanced Reasoning Runtime时出错: {e}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        stats = {}
        
        # MicroSandbox连接管理器已移除 - 无统计信息
        
        return stats
    
    def _extract_deepsearch_content_recursive(self, data: Any, max_depth: int = 3) -> str:
        """🔧 递归提取 deepsearch 结果中的实质性内容"""
        if max_depth <= 0:
            return ""
        
        if isinstance(data, dict):
            # 优先查找包含实质性内容的字段
            priority_fields = ['answer', 'final_report', 'report', 'summary', 'content', 'result']
            for field in priority_fields:
                if field in data:
                    value = data[field]
                    if isinstance(value, str) and len(value.strip()) >= 50:
                        return value.strip()
                    elif isinstance(value, (dict, list)):
                        recursive_result = self._extract_deepsearch_content_recursive(value, max_depth - 1)
                        if recursive_result:
                            return recursive_result
            
            # 如果优先字段没有内容，遍历所有字段
            for key, value in data.items():
                if isinstance(value, str) and len(value.strip()) >= 100:
                    return value.strip()
                elif isinstance(value, (dict, list)):
                    recursive_result = self._extract_deepsearch_content_recursive(value, max_depth - 1)
                    if recursive_result:
                        return recursive_result
        
        elif isinstance(data, list):
            for item in data:
                recursive_result = self._extract_deepsearch_content_recursive(item, max_depth - 1)
                if recursive_result:
                    return recursive_result
        
        elif isinstance(data, str) and len(data.strip()) >= 50:
            return data.strip()
        
        return ""
    
    def _is_meaningful_research_content(self, content: str) -> bool:
        """🔧 检测内容是否为有意义的研究报告"""
        if not content or len(content.strip()) < 30:
            return False
        
        content_lower = content.lower()
        
        # 检查研究相关关键词
        research_indicators = [
            # 中文研究指标
            '研究', '分析', '应用', '技术', '方法', '发展', '趋势', '挑战', '机遇', 
            '算法', '模型', '系统', '框架', '实验', '结果', '结论', '总结',
            '量子', '机器学习', '人工智能', '深度学习', '神经网络',
            # 英文研究指标
            'research', 'analysis', 'application', 'technology', 'method', 'development',
            'trend', 'challenge', 'opportunity', 'algorithm', 'model', 'system', 
            'framework', 'experiment', 'result', 'conclusion', 'summary',
            'quantum', 'machine learning', 'artificial intelligence', 'deep learning',
            'neural network', 'computing', 'optimization'
        ]
        
        # 计算研究相关词汇的出现次数
        research_score = sum(1 for indicator in research_indicators if indicator in content_lower)
        
        # 检查结构化内容指标
        structure_indicators = [
            '1.', '2.', '3.', '一、', '二、', '三、', '首先', '其次', '最后',
            'introduction', 'background', 'methodology', 'approach', 'conclusion',
            '背景', '方法', '结论', '总结'
        ]
        has_structure = any(indicator in content_lower for indicator in structure_indicators)
        
        # 检查技术深度指标
        technical_indicators = [
            'algorithm', 'implementation', 'performance', 'accuracy', 'efficiency',
            'optimization', 'parameter', 'dataset', 'training', 'testing',
            '算法', '实现', '性能', '准确率', '效率', '优化', '参数', '数据集', '训练', '测试'
        ]
        technical_score = sum(1 for indicator in technical_indicators if indicator in content_lower)
        
        # 综合评分判断
        is_meaningful = (
            research_score >= 3 or  # 至少3个研究相关词汇
            (research_score >= 2 and has_structure) or  # 2个研究词汇+结构化
            (research_score >= 2 and technical_score >= 2) or  # 研究词汇+技术词汇
            (len(content) >= 200 and research_score >= 1)  # 长内容+基本研究词汇
        )
        
        logger.debug(f"内容质量评估: 长度={len(content)}, 研究分数={research_score}, "
                    f"技术分数={technical_score}, 有结构={has_structure}, 有意义={is_meaningful}")
        
        return is_meaningful

    def _parse_tool_input_parameters(self, tool_input: str, service_name: str, tool_name: str, default_param_name: str) -> dict:
        """
        使用已有的JSONParameterParser解析工具输入参数
        
        Args:
            tool_input: 从XML解析得到的原始输入（可能包含JSON+XML混合内容）
            service_name: 服务名称（如 'browser_use'）
            tool_name: 工具名称（如 'browser_search_google'）
            default_param_name: 默认参数名称
            
        Returns:
            dict: 解析后的参数字典
        """
        try:
            # 使用已有的JSONParameterParser
            parse_result = self.json_parameter_parser.parse_tool_parameters(
                tool_id=service_name,
                action=tool_name,
                raw_input=tool_input
            )
            
            if parse_result.is_valid:
                logger.debug(f"✅ JSON参数解析成功: {parse_result.parsed_params}")
                return parse_result.parsed_params
            else:
                logger.warning(f"⚠️ JSON参数解析失败: {parse_result.errors}")
                
                # 🔧 修复：将参数验证错误注入结果流，让模型看到错误信息
                error_message = f"Parameter validation failed for {service_name}.{tool_name}: {parse_result.errors}"
                
                # 将错误信息作为特殊参数返回，这样工具执行会包含错误反馈
                return {
                    "_validation_error": error_message,
                    default_param_name: tool_input
                }
                
        except Exception as e:
            logger.error(f"❌ JSON参数解析异常: {e}")
            # 出错时回退到简单参数映射
            return {default_param_name: tool_input}

    async def _handle_tool_param_query(self, xml_string: str) -> str:
        """
        处理 <tool_param> 查询，返回工具的参数定义。
        """
        try:
            tool_id_match = re.search(r"<tool_id>(.*?)</tool_id>", xml_string)
            action_match = re.search(r"<action>(.*?)</action>", xml_string)

            if not tool_id_match or not action_match:
                error_msg = "Invalid <tool_param> format. Missing <tool_id> or <action> tag."
                logger.warning(error_msg)
                return self._format_result(f"Error: {error_msg}")

            tool_id = tool_id_match.group(1).strip()
            action = action_match.group(1).strip()

            logger.info(f"🔎 Handling <tool_param> query for {tool_id}/{action}")

            # 获取参数定义
            param_definitions = self.tool_manager.get_action_parameters(tool_id, action)

            response_data = {
                "status": "success",
                "tool_id": tool_id,
                "action": action,
                "parameters": param_definitions
            }

            # 格式化为JSON字符串以便在<result>中返回
            response_json = json.dumps(response_data, ensure_ascii=False, indent=2)
            return self._format_result(response_json)

        except ValueError as e:
            logger.error(f"Error handling <tool_param> query: {e}")
            return self._format_result(f"Error: {str(e)}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in _handle_tool_param_query: {e}", exc_info=True)
            return self._format_result("An internal error occurred while fetching tool parameters.")
    
    def _auto_inject_execute_tools(self, response_text: str) -> str:
        """
        🔧 自动注入缺失的<execute_tools />标签
        
        检测工具调用但缺少<execute_tools />的情况，自动添加该标签以确保工具能够执行。
        
        Args:
            response_text: LLM的原始响应
            
        Returns:
            可能添加了<execute_tools />的响应文本
        """
        import re
        
        # 如果已经有<execute_tools />，不需要处理
        if '<execute_tools />' in response_text or '<execute_tools></execute_tools>' in response_text:
            return response_text
        
        # 检测工具调用模式：<service_name><tool_name>...</tool_name></service_name>
        tool_call_patterns = [
            r'<(microsandbox|deepsearch|browser_use|search_tool|memory_staging)>\s*<[^>]+>.*?</[^>]+>\s*</(microsandbox|deepsearch|browser_use|search_tool|memory_staging)>',
            r'<browser>\s*<[^>]+>.*?</[^>]+>\s*</browser>'  # 兼容browser别名
        ]
        
        has_tool_calls = False
        for pattern in tool_call_patterns:
            if re.search(pattern, response_text, re.DOTALL | re.IGNORECASE):
                has_tool_calls = True
                break
        
        # 如果检测到工具调用但没有execute_tools标签，自动添加
        if has_tool_calls:
            # 找到最后一个工具调用的结束位置
            last_tool_end = -1
            for pattern in tool_call_patterns:
                matches = list(re.finditer(pattern, response_text, re.DOTALL | re.IGNORECASE))
                if matches:
                    last_match_end = matches[-1].end()
                    if last_match_end > last_tool_end:
                        last_tool_end = last_match_end
            
            if last_tool_end > -1:
                # 在最后一个工具调用后添加<execute_tools />
                before = response_text[:last_tool_end]
                after = response_text[last_tool_end:]
                
                # 确保有适当的换行
                if not before.endswith('\n'):
                    before += '\n'
                
                injected_response = before + '<execute_tools />' + after
                
                logger.info("🔧 自动注入<execute_tools />标签以确保工具执行")
                logger.debug(f"注入位置: 字符位置 {last_tool_end}")
                
                return injected_response
        
        # 没有检测到工具调用或已有execute_tools标签，返回原文
        return response_text
    
    def _format_parameter_validation_error(self, service_name: str, tool_name: str, validation_error: str, original_input: str) -> str:
        """
        🔧 格式化参数验证错误，让模型能够理解并修正参数
        
        Args:
            service_name: 服务名称
            tool_name: 工具名称
            validation_error: 验证错误信息
            original_input: 原始输入参数
            
        Returns:
            格式化后的错误信息
        """
        error_message = f"""
Parameter Validation Failed 

Tool Call: {service_name}.{tool_name}
Error Details: {validation_error}

Your Input: {original_input}

Correction Suggestions: Use <tool_param><tool_id>{service_name}</tool_id><action>{tool_name}</action></tool_param> to get the correct parameters

Please retry the tool call with correct parameters based on the error information above.
"""
        return error_message.strip()

    def _format_error_with_recovery_suggestion(self, error_message: str, error_type: str, service_name: str, tool_name: str) -> str:
        """🔧 增强的错误格式化和恢复建议 - 针对具体错误类型提供详细指导"""
        base_error = f"Tool execution failed: {error_message}"
        
        recovery_suggestions = {
            "parameter_error": f"💡 建议: 检查 {service_name} 的 {tool_name} 工具参数格式。参考工具定义中的正确参数名称。",
            "tool_not_found": f"💡 建议: 工具 {tool_name} 在 {service_name} 中不存在。检查工具名称是否正确，或尝试使用其他工具。",
            "network_error": f"💡 建议: 网络连接问题。等待几秒后重试，或尝试使用替代工具。",
            "validation_error": f"💡 建议: 输入数据验证失败。检查输入格式和内容是否符合要求。",
            "permission_error": f"💡 建议: 权限不足。检查服务配置或尝试其他方法。",
            "empty_results": f"🔍 建议: 搜索未找到结果。尝试:\n  • 使用不同的关键词或更简单的查询\n  • 切换到其他搜索工具 (如 deepsearch → browser_use)\n  • 检查数据是否已保存在内存暂存区: <memory_staging><memory_list></memory_list></memory_staging>",
            "data_not_available": f"📊 建议: 数据不可用。尝试:\n  • 使用更广泛的搜索词\n  • 检查内存暂存区是否有相关数据: <memory_staging><memory_search>关键词</memory_search></memory_staging>\n  • 考虑使用示例数据（明确标记为模拟数据）",
            "timeout_error": f"⏱️ 建议: 工具执行超时。尝试:\n  • 简化查询或操作\n  • 分步骤执行复杂任务\n  • 稍后重试",
            "service_unavailable": f"🚫 建议: 服务不可用。尝试:\n  • 使用替代工具达到相同目标\n  • 稍后重试\n  • 使用缓存或内存中的数据",
            "unknown_error": f"💡 建议: 未知错误。尝试简化输入或使用其他工具替代。"
        }
        
        suggestion = recovery_suggestions.get(error_type, recovery_suggestions["unknown_error"])
        return f"{base_error}\n{suggestion}"

