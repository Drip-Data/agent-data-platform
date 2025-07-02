# -*- coding: utf-8 -*-
"""
Orchestrator
负责解析LLM生成的单个指令块，并调度执行。
支持单指令、并行指令和串行指令。
"""

import asyncio
import logging
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
import re

from core.unified_tool_manager import UnifiedToolManager
from core.llm_client import LLMClient
from core.redis_manager import RedisManager
from core.metrics import EnhancedMetrics
from core.tool_output_processors import ToolOutputProcessor

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    解析LLM的单个指令块 (<parallel>, <sequential>, 或独立工具调用),
    通过UnifiedToolManager调度任务，并返回格式化的结果。
    """
    def __init__(self, 
                 tool_manager: UnifiedToolManager, 
                 llm_client: LLMClient, 
                 redis_manager: RedisManager, 
                 metrics_manager: EnhancedMetrics):
        """
        初始化 Orchestrator。
        
        Args:
            tool_manager: 统一工具管理器，用于实际执行工具��用。
            llm_client: LLM客户端，可能用于未来的复杂任务。
            redis_manager: Redis管理器。
            metrics_manager: 指标管理器。
        """
        self.tool_manager = tool_manager
        self.llm_client = llm_client
        self.redis_manager = redis_manager
        self.metrics = metrics_manager
        self.output_processor = ToolOutputProcessor()

    async def execute_instruction(self, instruction_xml: str) -> str:
        """
        执行单个指令块的公共入口。

        Args:
            instruction_xml: 包含指令的XML字符串。

        Returns:
            一个包含一个或多个 <result> 标签的XML字符串。
        """
        logger.info(f"Orchestrator received instruction:\n{instruction_xml}")
        try:
            root_text = instruction_xml.strip()
            if not root_text.startswith('<'):
                return f'<result index="0">Error: Invalid XML format. Expected a tool call, but received plain text.</result>'

            root = ET.fromstring(root_text)
            
            instruction_type = root.tag
            
            if instruction_type in ['parallel', 'sequential']:
                tool_calls_to_execute = self._parse_tool_calls_from_block(root)
            else:
                tool_calls_to_execute = self._parse_single_tool_call(root)

            if not tool_calls_to_execute:
                logger.warning("No valid tool calls found in the instruction.")
                return '<result index="0">Error: No valid tool calls found in the instruction block.</result>'

            if instruction_type == 'parallel':
                results = await self._execute_parallel(tool_calls_to_execute)
            else:
                results = await self._execute_sequential(tool_calls_to_execute)

            return self._format_results(results)

        except ET.ParseError as e:
            logger.error(f"XML Parse Error: {e}\nInstruction: {instruction_xml}")
            return f'<result index="0">Error: Invalid XML format. Details: {e}</result>'
        except Exception as e:
            logger.error(f"Error during orchestration: {e}", exc_info=True)
            return f'<result index="0">Error: Orchestration failed. {e}</result>'

    def _parse_single_tool_call(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        解析V4格式的单工具调用: <server_name><tool_name>query</tool_name></server_name>
        """
        server_name = root.tag
        if not list(root):
            logger.warning(f"V4单工具调用格式错误: '{server_name}' 缺少工具子元素")
            return []
        
        tool_element = list(root)[0]
        tool_name = tool_element.tag
        query = tool_element.text or ""
        
        logger.debug(f"V4 single tool parsed: {server_name}.{tool_name}")
        
        return [{
            "index": 0,
            "server": server_name,
            "tool": tool_name,
            "query": query.strip()
        }]

    def _parse_tool_calls_from_block(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        解析V4格式的 <parallel> 或 <sequential> 块中的工具调用列表
        每个调用格式: <server_name><tool_name>query</tool_name></server_name>
        """
        parsed_calls = []
        
        for index, server_element in enumerate(root):
            server_name = server_element.tag
            
            if not list(server_element):
                logger.warning(f"V4 format error: '{server_name}' is missing a tool child element in a block.")
                continue
            
            tool_element = list(server_element)[0]
            tool_name = tool_element.tag
            query = tool_element.text or ""
            
            logger.debug(f"V4 block parsed [{index}]: {server_name}.{tool_name}")
            
            parsed_calls.append({
                "index": index,
                "server": server_name,
                "tool": tool_name,
                "query": query.strip()
            })
            
        logger.info(f"V4 block parsed successfully: {len(parsed_calls)} tool calls.")
        return parsed_calls

    async def _execute_parallel(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并发执行所有工具调用。"""
        logger.info(f"Executing {len(calls)} calls in parallel.")
        
        tasks = [
            self.tool_manager.execute_tool(call['server'], call['tool'], call['query'])
            for call in calls
        ]
        
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [{"index": call['index'], "server": call['server'], "tool": call['tool'], "result": res} for call, res in zip(calls, raw_results)]

    async def _execute_sequential(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """串行执行工具调用，并支持结果引用。"""
        logger.info(f"Executing {len(calls)} calls sequentially.")
        
        results_so_far = []
        clean_outputs_so_far = []
        final_results = []
        
        for call in calls:
            query = self._resolve_placeholders(call['query'], clean_outputs_so_far)
            
            result = await self.tool_manager.execute_tool(call['server'], call['tool'], query)
            
            # 暂存原始结果和处理后的干净结果
            results_so_far.append(result)
            clean_output = self.output_processor.process_output(call['server'], call['tool'], result)
            clean_outputs_so_far.append(clean_output)

            final_results.append({"index": call['index'], "server": call['server'], "tool": call['tool'], "result": result})
            
            # 如果步骤失败，则停止执行
            if isinstance(result, Exception) or (isinstance(result, dict) and not result.get('success', True)):
                logger.warning(f"Sequential execution failed at step {call['index']} ({call['tool']}). Stopping.")
                break
                
        return final_results

    def _resolve_placeholders(self, query: str, clean_outputs: List[str]) -> str:
        """
        解析并替换查询字符串中的占位符, 如 {results[0]}。
        使用处理后的干净输出进行替换。
        """
        if not re.search(r'\{results\[\d+\]\}', query):
            return query

        def replacer(match):
            try:
                index = int(match.group(1))
                if 0 <= index < len(clean_outputs):
                    return clean_outputs[index]
                else:
                    logger.warning(f"Placeholder index {index} is out of bounds.")
                    return match.group(0)
            except (ValueError, IndexError) as e:
                logger.error(f"Error resolving placeholder: {e}")
                return match.group(0)

        logger.info(f"Resolving placeholders in query: {query}")
        resolved_query = re.sub(r'\{results\[(\d+)\]\}', replacer, query)
        logger.info(f"Resolved query: {resolved_query}")
        return resolved_query

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """将执行结果格式化为<result> XML字符串。"""
        if not results:
            return ""
            
        result_tags = []
        for res_item in results:
            index = res_item['index']
            server = res_item['server']
            tool = res_item['tool']
            result_obj = res_item['result']
            
            # 使用ToolOutputProcessor来获取干净、规范的输出
            processed_output = self.output_processor.process_output(server, tool, result_obj)
            
            # XML转义
            escaped_output = self.output_processor.escape_xml_content(processed_output)
            
            result_tags.append(f'<result index="{index}">{escaped_output}</result>')
            
        return "\n".join(result_tags)



