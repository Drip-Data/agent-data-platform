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
        """XML Streaming执行模式 - 实现真正的停等执行防止幻觉"""
        logger.info(f"🎯 XML Streaming模式 - 任务: {task.description}")
        start_time = time.time()
        session_id = f"session_{task.task_id}_{int(start_time)}"
        raw_llm_response = ""
        final_response = ""

        try:
            # 1. 从MemoryManager获取上下文
            logger.info(f"🧠 正在为任务 {task.task_id} 检索记忆上下文...")
            memory_context = await self.memory_manager.generate_context_summary(session_id)
            
            # 2. 获取工具信息
            available_tools = await self._get_available_tools()
            tool_descriptions = await self._get_tool_descriptions()
            
            # 3. 实现真正的停等执行机制
            logger.info("🔄 开始迭代停等执行...")
            execution_result = await self._execute_iterative_stop_and_wait(
                task_description=task.description,
                available_tools=available_tools,
                tool_descriptions=tool_descriptions,
                memory_context=memory_context,
                max_steps=task.max_steps or 20,
                session_id=session_id
            )
            success = execution_result.get('success', False)
            final_response = execution_result.get('final_response', raw_llm_response)
            
            # 构建包含原始响应的metadata
            metadata = execution_result.copy()
            metadata.update({
                'raw_response': final_response,
                'response_length': len(final_response),
                'initial_llm_response': raw_llm_response
            })

        except Exception as e:
            logger.error(f"任务执行过程中发生顶层异常: {e}", exc_info=True)
            success = False
            # 如果在sequential执行之前发生异常，使用原始LLM响应
            if not final_response:
                final_response = raw_llm_response
            metadata = {'error': str(e), 'raw_llm_response': raw_llm_response, 'raw_response': final_response, 'response_length': len(final_response)}

        # 4. 直接输出XML格式数据
        total_duration = time.time() - start_time
        
        # 构建XML输出数据格式
        xml_output = {
            "timestamp": datetime.now().isoformat(),
            "task_id": task.task_id,
            "task_description": task.description,
            "duration": total_duration,
            "success": success,
            "final_result": "任务执行完成，已输出原始XML轨迹格式",
            "raw_response": final_response,
            "response_length": len(final_response)
        }
        
        # 输出到控制台
        print(json.dumps(xml_output, ensure_ascii=False, indent=2))
        
        # 保存到文件
        await self._save_xml_output(xml_output)
        
        # 构建简单的返回对象
        from core.interfaces import TrajectoryResult
        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=task.task_id, 
            task_description=task.description,
            runtime_id=self._runtime_id,
            steps=[],  
            success=success,
            final_result="任务执行完成，已输出原始XML轨迹格式",
            total_duration=total_duration,
            metadata=metadata
        )
        
        return trajectory
    
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
    
    async def _execute_iterative_stop_and_wait(self, task_description: str, available_tools: List[str], 
                                              tool_descriptions: str, memory_context: str, 
                                              max_steps: int, session_id: str) -> dict:
        """
        实现真正的迭代停等执行机制 - 防止LLM幻觉
        LLM生成一个工具调用后立即停止，等待真实执行结果，然后继续
        """
        logger.info("🎯 启动迭代停等执行机制")
        
        # 构建初始历史记录
        conversation_history = []
        step_count = 0
        success = False
        
        # 构建初始提示
        initial_messages = self.prompt_builder.build_prompt(
            task_description=task_description,
            available_tools=available_tools,
            tool_descriptions=tool_descriptions,
            history=conversation_history
        )
        
        while step_count < max_steps:
            step_count += 1
            logger.info(f"🔄 第 {step_count} 轮迭代...")
            
            try:
                # 1. 获取LLM响应 (应该包含思考+一个工具调用)
                if step_count == 1:
                    llm_response = await self.client._call_api(initial_messages)
                else:
                    # 继续对话，传入完整历史
                    continue_messages = self.prompt_builder.build_prompt(
                        task_description=task_description,
                        available_tools=available_tools,
                        tool_descriptions=tool_descriptions,
                        history=conversation_history
                    )
                    llm_response = await self.client._call_api(continue_messages)
                
                logger.info(f"📨 LLM响应长度: {len(llm_response)}")
                
                # 2. 检查是否包含答案 (任务完成)
                if '<answer>' in llm_response.lower():
                    logger.info("✅ 检测到答案标签，任务完成")
                    conversation_history.append(llm_response)
                    success = True
                    break
                
                # 3. 解析工具调用
                tool_call = self._extract_tool_call(llm_response)
                if not tool_call:
                    logger.warning("⚠️ 未检测到工具调用，添加响应到历史并继续")
                    conversation_history.append(llm_response)
                    continue
                
                logger.info(f"🔧 检测到工具调用: {tool_call['tool_name']} - {tool_call['content'][:100]}...")
                
                # 4. 执行真实工具调用
                tool_result = await self._execute_real_tool(tool_call, session_id)
                
                # 5. 构建包含真实结果的历史条目
                history_entry = llm_response + "\n\n<result>\n" + tool_result + "\n</result>"
                conversation_history.append(history_entry)
                
                logger.info(f"✅ 工具执行完成，结果长度: {len(tool_result)}")
                
            except Exception as e:
                logger.error(f"❌ 第 {step_count} 轮执行失败: {e}")
                error_entry = f"<error>执行第 {step_count} 轮时发生错误: {str(e)}</error>"
                conversation_history.append(error_entry)
                continue
        
        # 构建最终响应
        final_response = "\n\n".join(conversation_history)
        
        return {
            'success': success,
            'final_response': final_response,
            'steps_executed': step_count,
            'conversation_history': conversation_history
        }
    
    def _extract_tool_call(self, response: str) -> dict:
        """从LLM响应中提取工具调用"""
        import re
        
        # 支持的工具调用模式
        tool_patterns = [
            r'<(microsandbox|deepsearch|browser_use|search)>(.*?)</\1>',
        ]
        
        for pattern in tool_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                tool_name = match.group(1)
                content = match.group(2).strip()
                return {
                    'tool_name': tool_name,
                    'content': content,
                    'raw_match': match.group(0)
                }
        
        return None
    
    async def _execute_real_tool(self, tool_call: dict, session_id: str) -> str:
        """执行真实的工具调用并返回结果"""
        try:
            tool_name = tool_call['tool_name']
            content = tool_call['content']
            
            # 标准化工具名称
            if tool_name == 'search':
                tool_name = 'deepsearch'
            
            # 处理嵌套动作调用 (例如: "research Python analysis")
            action = self._get_default_action(tool_name)
            instruction = content
            
            # 如果内容以已知动作开头，提取真实指令
            known_actions = ['research', 'quick_research', 'comprehensive_research', 'microsandbox_execute']
            for known_action in known_actions:
                if content.strip().startswith(known_action + ' '):
                    action = known_action
                    instruction = content.strip()[len(known_action):].strip()
                    break
            
            logger.info(f"🔧 执行工具: {tool_name}, 动作: {action}")
            
            # 构建正确的参数格式
            if tool_name == 'deepsearch':
                # deepsearch 需要 question 参数
                parameters = {'question': instruction}
            elif tool_name == 'browser_use':
                # browser_use 需要 query 参数  
                parameters = {'query': instruction}
            elif tool_name == 'microsandbox':
                # microsandbox 需要 code 参数
                parameters = {'code': instruction}
            else:
                # 其他工具使用 instruction 参数
                parameters = {'instruction': instruction}
            
            # 通过toolscore执行工具
            result = await self.toolscore_client.execute_tool(
                tool_id=tool_name,
                action=action,
                parameters=parameters
            )
            
            if isinstance(result, dict):
                if result.get('success', True):
                    output = result.get('output', result.get('result', str(result)))
                    return str(output)
                else:
                    error_msg = result.get('error', 'Unknown error')
                    return f"工具执行失败: {error_msg}"
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"❌ 工具执行异常: {e}")
            return f"工具执行发生异常: {str(e)}"
    
    def _get_default_action(self, tool_name: str) -> str:
        """获取工具的默认动作名称"""
        action_mapping = {
            'microsandbox': 'microsandbox_execute',
            'deepsearch': 'research',  # Fixed: use 'research' instead of 'deepsearch_search'
            'browser_use': 'browser_search_google',
            'search': 'research'  # Fixed: use 'research' for search tool
        }
        return action_mapping.get(tool_name, tool_name)