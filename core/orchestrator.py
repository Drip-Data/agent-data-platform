# -*- coding: utf-8 -*-
"""
Orchestrator
负责解析LLM生成的单个指令块，并调度执行。
"""

import asyncio
import logging
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

# 假设 EnhancedDispatcher 位于 core 目录
# from core.dispatcher_enhanced import EnhancedDispatcher

# 为了让此文件可独立运行测试，我们创建一个 Mock Dispatcher
class MockDispatcher:
    async def dispatch(self, server: str, tool: str, query: str) -> Any:
        print(f"--> [Dispatching] Server: {server}, Tool: {tool}, Query: '{query}'")
        await asyncio.sleep(0.1)
        if "fail" in query:
            return {"error": "Failed as requested."}
        # 模拟占位符被替换后的调用
        if "53" in query:
             return {"output": "In 10 years, he will be 63"}
        return {"output": f"Result for {tool}('{query}')"}

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    解析LLM的单个指令块 (<parallel>, <sequential>, 或独立工具调用),
    通过Dispatcher调度任务，并返回格式化的结果。
    """
    def __init__(self, dispatcher):
        """
        初始化 Orchestrator。
        
        Args:
            dispatcher: 一个兼容的 Dispatcher 实例，用于实际执行工具调用。
        """
        self.dispatcher = dispatcher

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
            # 使用一个虚拟的根标签来包裹，以便能正确解析单个工具调用
            root = ET.fromstring(f"<root>{instruction_xml}</root>")[0]
            
            instruction_type = root.tag
            
            if instruction_type in ['parallel', 'sequential']:
                tool_calls_to_execute = self._parse_tool_calls_from_block(root)
            else: # 独立工具调用
                tool_calls_to_execute = self._parse_single_tool_call(root)

            if not tool_calls_to_execute:
                logger.warning("No valid tool calls found in the instruction.")
                return ""

            if instruction_type == 'parallel':
                results = await self._execute_parallel(tool_calls_to_execute)
            else: # sequential 或 独立工具调用
                results = await self._execute_sequential(tool_calls_to_execute)

            return self._format_results(results)

        except ET.ParseError as e:
            logger.error(f"XML Parse Error: {e}\nInstruction: {instruction_xml}")
            return f'<result index="0">Error: Invalid XML format.</result>'
        except Exception as e:
            logger.error(f"Error during orchestration: {e}", exc_info=True)
            return f'<result index="0">Error: Orchestration failed. {e}</result>'

    def _parse_single_tool_call(self, root: ET.Element) -> List[Dict[str, Any]]:
        """从一个独立的工具调用元素中解析。"""
        server_name = root.tag
        if not root:
            logger.warning(f"Server element '{server_name}' has no tool child.")
            return []
        
        tool_element = root[0]
        tool_name = tool_element.tag
        query = tool_element.text or ""
        
        return [{
            "index": 0,
            "server": server_name,
            "tool": tool_name,
            "query": query.strip()
        }]

    def _parse_tool_calls_from_block(self, root: ET.Element) -> List[Dict[str, Any]]:
        """从 <parallel> 或 <sequential> 块中解析出工具调用列表。"""
        parsed_calls = []
        for index, server_element in enumerate(root):
            server_name = server_element.tag
            if not server_element:
                logger.warning(f"Server element '{server_name}' has no tool child.")
                continue
            
            tool_element = server_element[0]
            tool_name = tool_element.tag
            query = tool_element.text or ""
            
            parsed_calls.append({
                "index": index,
                "server": server_name,
                "tool": tool_name,
                "query": query.strip()
            })
        return parsed_calls

    async def _execute_parallel(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并发执行所有工具调用。"""
        logger.info(f"Executing {len(calls)} calls in parallel.")
        
        tasks = [
            self.dispatcher.dispatch(call['server'], call['tool'], call['query'])
            for call in calls
        ]
        
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [{"index": call['index'], "result": res} for call, res in zip(calls, raw_results)]

    async def _execute_sequential(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """串行执行工具调用。"""
        logger.info(f"Executing {len(calls)} calls sequentially.")
        
        results_so_far = []
        final_results = []
        
        for call in calls:
            query = self._resolve_placeholders(call['query'], results_so_far)
            
            result = await self.dispatcher.dispatch(call['server'], call['tool'], query)
            results_so_far.append(result)
            final_results.append({"index": call['index'], "result": result})
            
            if isinstance(result, Exception) or (isinstance(result, dict) and 'error' in result):
                logger.warning(f"Sequential execution failed at step {call['index']}. Stopping.")
                break
                
        return final_results

    def _resolve_placeholders(self, query: str, results_so_far: List[Any]) -> str:
        """解析并替换查询字符串中的占位符。"""
        # 简单的占位符替换，未来可以扩展为支持更复杂的JSONPath
        import re
        def replacer(match):
            try:
                index = int(match.group(1))
                if index < 0 or index >= len(results_so_far):
                    return match.group(0) # or raise an error
                
                result_obj = results_so_far[index]
                
                # 提取核心数据
                if isinstance(result_obj, dict) and 'output' in result_obj:
                    data = result_obj['output']
                else:
                    data = str(result_obj)
                
                return str(data)
            except (ValueError, IndexError):
                return match.group(0) # 无法解析则返回原样

        # 匹配 {results[index].data} 格式
        return re.sub(r'\{results\[(\d+)\]\.data\}', replacer, query)

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """将执行结果格式化为<result> XML字符串。"""
        if not results:
            return ""
            
        result_tags = []
        for res_item in results:
            index = res_item['index']
            result_obj = res_item['result']
            
            if isinstance(result_obj, Exception):
                processed_output = f"Error: {str(result_obj)}"
            elif isinstance(result_obj, dict) and 'error' in result_obj:
                processed_output = f"Error: {result_obj['error']}"
            elif isinstance(result_obj, dict) and 'output' in result_obj:
                 processed_output = str(result_obj['output'])
            else:
                processed_output = str(result_obj)

            # XML转义
            processed_output = processed_output.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            result_tags.append(f'<result index="{index}">{processed_output}</result>')
            
        return "\n".join(result_tags)

async def main():
    """一个完整的测试用例，覆盖所有场景"""
    orchestrator = Orchestrator(dispatcher=MockDispatcher())
    
    print("--- [1] Testing Single Tool Call (Dynamic Observation) ---")
    single_tool_plan = """<microsandbox_server><execute_python>print('hello world')</execute_python></microsandbox_server>"""
    single_tool_results = await orchestrator.execute_instruction(single_tool_plan)
    print(f"<-- Results:\n{single_tool_results}\n")

    print("--- [2] Testing Parallel Execution ---")
    parallel_plan = """<parallel>
    <microsandbox_server><execute_python>print(1+1)</execute_python></microsandbox_server>
    <deepsearch_server><search>What is FastAPI?</search></deepsearch_server>
</parallel>"""
    parallel_results = await orchestrator.execute_instruction(parallel_plan)
    print(f"<-- Results:\n{parallel_results}\n")
    
    print("--- [3] Testing Sequential Execution (One-shot Planning with Placeholder) ---")
    sequential_plan = """<sequential>
    <deepsearch_server><search>How old is Elon Musk</search></deepsearch_server>
    <microsandbox_server><execute_python>age = {results[0].data}; print(f"age is {age}")</execute_python></microsandbox_server>
</sequential>"""
    sequential_plan_results = await orchestrator.execute_instruction(sequential_plan)
    print(f"<-- Results:\n{sequential_plan_results}\n")

    print("--- [4] Testing Error Handling ---")
    error_plan = """<microsandbox_server><execute_python>print("fail")</execute_python></microsandbox_server>"""
    error_results = await orchestrator.execute_instruction(error_plan)
    print(f"<-- Results:\n{error_results}\n")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
