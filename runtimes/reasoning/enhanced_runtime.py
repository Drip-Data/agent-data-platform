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
from typing import List
from enum import Enum

from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult
from core.llm.prompt_builders.reasoning_prompt_builder import ReasoningPromptBuilder
from core.utils.path_utils import get_trajectories_dir
from core.streaming.sequential_executor import SequentialStreamingExecutor
from core.memory_manager import MemoryManager
from core.trajectory_enhancer import TrajectoryEnhancer


logger = logging.getLogger(__name__)


class TrajectoryStorageMode(Enum):
    """轨迹存储模式"""
    INDIVIDUAL_FILES = "individual"
    DAILY_GROUPED = "daily_grouped"
    WEEKLY_GROUPED = "weekly_grouped"
    MONTHLY_GROUPED = "monthly_grouped"


class EnhancedReasoningRuntime(RuntimeInterface):
    """
    增强的推理运行时 - 专注核心功能, 并集成高级模块
    """
    
    def __init__(self, config_manager, llm_client, toolscore_client, redis_manager=None, 
                 toolscore_websocket_endpoint=None, xml_streaming_mode: bool = False, 
                 trajectory_storage_mode: str = "daily_grouped"):
        self._runtime_id = f"enhanced-reasoning-{uuid.uuid4()}"
        self.config_manager = config_manager
        self.client = llm_client
        self.toolscore_client = toolscore_client
        self.xml_streaming_mode = xml_streaming_mode
        self.trajectory_storage_mode = TrajectoryStorageMode(trajectory_storage_mode)
        self.prompt_builder = ReasoningPromptBuilder(streaming_mode=xml_streaming_mode)
        self.is_initialized = False

        # 初始化高级模块
        self.memory_manager = MemoryManager(redis_manager=redis_manager)
        self.trajectory_enhancer = TrajectoryEnhancer()
        self.sequential_executor = SequentialStreamingExecutor(
            llm_client=self.client, 
            tool_executor=self.toolscore_client,
            memory_manager=self.memory_manager
        )
        self.mcp_servers = self._load_mcp_config("config/mcp_servers.json")
    
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
        
        return {"type": block_type, "actions": actions}

    async def _execute_tool(self, action: dict) -> str:
        """
        根据单个动作字典，通过toolscore_client调用对应的MCP Server并返回结果。
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
                    return str(output)
                else:
                    error_msg = result.get('error_message', result.get('error', 'Unknown error'))
                    return f"Tool execution failed: {error_msg}"
            else:
                return str(result)

        except Exception as e:
            logger.error(f"An unexpected error occurred while calling tool '{service_name}/{tool_name}': {e}", exc_info=True)
            return f"An unexpected error occurred while calling {service_name}: {e}"

    async def _execute_parallel(self, actions: list) -> list:
        """并发执行多个动作。"""
        import asyncio
        if not actions:
            return []
        
        tasks = [self._execute_tool(action) for action in actions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理可能发生的异常，确保返回字符串列表
        return [str(res) if not isinstance(res, Exception) else f"Error: {res}" for res in results]

    async def _execute_sequential(self, actions: list) -> list:
        """串行执行多个动作，并处理结果占位符。"""
        step_results = {}
        final_results = []

        for i, action in enumerate(actions):
            step_number = i + 1
            
            # 替换输入中的占位符
            action['input'] = self._replace_placeholders(action['input'], step_results)

            # 执行动作
            result = await self._execute_tool(action)
            
            step_results[step_number] = result
            final_results.append(result)
            
        return final_results

    def _replace_placeholders(self, input_str: str, results: dict) -> str:
        """用之前步骤的结果替换占位符 $result_of_step_N。"""
        import re
        
        # 这个正则表达式查找 $result_of_step_1, $result_of_step_2 等
        def replacer(match):
            step_num = int(match.group(1))
            return str(results.get(step_num, ''))

        return re.sub(r"\$result_of_step_(\d+)", replacer, input_str)
    
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
            
            # 1. 调用LLM，设置动态停止序列
            response_text = await self.client._call_api(
                history,
                stop_sequences=["<execute_tools />", "Final Answer:"]
            )
            history.append({"role": "assistant", "content": response_text})
            full_trajectory.append({"role": "assistant", "content": response_text})

            # 2. 检查是否是最终答案
            if "Final Answer:" in response_text:
                logger.info("✅ Final Answer detected. Task complete.")
                break

            # 3. 解析执行块
            execution_block = self._parse_execution_block(response_text)
            actions = execution_block.get("actions", [])
            
            if not actions:
                logger.warning("No executable actions found in LLM response. Continuing.")
                # 注入一个空结果以避免LLM卡住
                result_xml = self._format_result(["No action was performed."])
                history.append({"role": "assistant", "content": result_xml})
                full_trajectory.append({"role": "assistant", "content": result_xml})
                continue

            # 4. 根据类型分发执行
            results = []
            block_type = execution_block.get("type")
            if block_type == "sequential":
                logger.info(f"Executing sequential block with {len(actions)} actions.")
                results = await self._execute_sequential(actions)
            elif block_type == "parallel":
                logger.info(f"Executing parallel block with {len(actions)} actions.")
                results = await self._execute_parallel(actions)
            else: # single
                logger.info(f"Executing single action.")
                results = [await self._execute_tool(actions[0])]

            # 5. 格式化并注入结果
            result_xml = self._format_result(results)
            history.append({"role": "assistant", "content": result_xml})
            full_trajectory.append({"role": "assistant", "content": result_xml})

        else:
            logger.warning(f"Max steps ({max_steps}) reached. Terminating task.")

        # 任务结束，处理最终结果
        final_trajectory_str = "\n".join(item["content"] for item in full_trajectory)
        total_duration = time.time() - start_time
        success = "Final Answer:" in final_trajectory_str

        xml_output = {
            "timestamp": datetime.now().isoformat(),
            "task_id": task.task_id,
            "task_description": task.description,
            "duration": total_duration,
            "success": success,
            "final_result": "Task execution completed.",
            "raw_response": final_trajectory_str,
        }
        
        await self._save_xml_output(xml_output)

        return TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id, 
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=[],  
            success=success,
            final_result="Task execution completed.",
            total_duration=total_duration,
            metadata={'full_trajectory': full_trajectory}
        )

    def _format_result(self, results: list) -> str:
        """将工具执行结果列表格式化为单个 <result> XML块。"""
        if not results:
            return "<result>No action was performed or no result was returned.</result>"
        
        # 如果有多个结果，将它们组合在一起
        result_content = "\n".join(str(res) for res in results)
        
        return f"<result>{result_content}</result>"
    
    async def _execute_standard(self, task: TaskSpec) -> TrajectoryResult:
        """标准执行模式 (作为备用)"""
        logger.warning("执行标准（ReAct）模式，此模式功能有限。")
        # 简单实现标准模式
        start_time = time.time()
        try:
            # 简单的LLM调用
            messages = self.prompt_builder.build_prompt(
                task_description=task.description,
                available_tools=[],
                tool_descriptions="",
                streaming_mode=False
            )
            response = await self.client._call_api(messages)
            success = True
            final_result = response
        except Exception as e:
            logger.error(f"标准模式执行失败: {e}")
            success = False
            final_result = f"执行失败: {str(e)}"
            response = ""
        
        total_duration = time.time() - start_time
        
        # 构建返回对象
        from core.interfaces import TrajectoryResult
        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id,
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=[],
            success=success,
            final_result=final_result,
            total_duration=total_duration,
            metadata={'mode': 'standard', 'raw_response': response}
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

    def _detect_success(self, response: str) -> bool:
        """检测XML响应是否成功"""
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

    async def cleanup(self):
        """清理资源"""
        logger.info("🧹 清理Enhanced Reasoning Runtime资源")
        if self.toolscore_client and hasattr(self.toolscore_client, 'close'):
            await self.toolscore_client.close()
        self.is_initialized = False
        logger.info("✅ 资源清理完成")
    
