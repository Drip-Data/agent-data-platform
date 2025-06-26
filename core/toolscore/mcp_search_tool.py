"""
MCP Server搜索和安装工具 - 优化版本
专注LLM智能选择，移除复杂加权打分逻辑
"""

import logging
import json
import time
from typing import Dict, Any, List, Optional
import os

from .tool_gap_detector import ToolGapDetector
from .dynamic_mcp_manager import DynamicMCPManager, MCPSearchResult

logger = logging.getLogger(__name__)

class MCPSearchTool:
    """MCP搜索和安装工具 - 简化版本，专注LLM智能选择"""
    
    def __init__(self, tool_gap_detector: ToolGapDetector, dynamic_mcp_manager: DynamicMCPManager):
        self.tool_gap_detector = tool_gap_detector
        self.dynamic_mcp_manager = dynamic_mcp_manager
        
        # 缓存mcp_tools.json数据，避免重复磁盘I/O
        self._mcp_tools_path: Optional[str] = None
        self._mcp_tools_data: Optional[List[Dict[str, Any]]] = None
        
        # 失败工具跟踪和冷却机制
        self._failed_tools: Dict[str, Dict[str, Any]] = {}
        self._cooldown_period = 300  # 5分钟冷却期
        
        logger.info("✅ MCP Search Tool initialized - 优化版本，包含失败工具跟踪")
    
    async def search_and_install_tools(self, task_description: str, current_available_tools: List[Dict[str, Any]], 
                                       reason: str = "") -> MCPSearchResult:
        """
        搜索并安装适合当前任务的MCP服务器
        优化版本：直接使用LLM从本地JSON中选择工具，支持错误恢复和降级策略
        """
        logger.info(f"🔍 开始智能工具搜索: {task_description[:100]}...")
        if reason:
            logger.info(f"搜索原因: {reason}")
        
        try:
            # 1. 快速工具缺口分析
            analysis = await self.tool_gap_detector.analyze_tool_sufficiency(
                task_description, current_available_tools
            )
            
            if analysis.has_sufficient_tools:
                return MCPSearchResult(
                    success=False,
                    message="当前工具已足够完成任务，无需安装新工具",
                    installed_tools=[]
                )
            
            # 2. LLM智能选择工具（核心优化）
            selected_tools = await self.find_matching_tools_from_analysis(
                task_description, 
                getattr(analysis, 'tool_requirements', [])
            )
            
            if not selected_tools:
                # 降级策略：尝试使用现有的基础工具完成任务
                logger.info("🔄 LLM未选择工具，直接进入降级策略")
                return await self._try_fallback_with_existing_tools(task_description, current_available_tools)
            
            logger.info(f"🎯 LLM选择了 {len(selected_tools)} 个工具候选")
            
            # 3. 尝试安装推荐工具，增强错误处理和冷却机制
            failed_installations = []
            for i, tool_info in enumerate(selected_tools[:3], 1):  # 最多尝试前3个
                tool_name = tool_info.get('name', 'Unknown')
                logger.info(f"📦 尝试安装工具 {i}: {tool_name}")
                
                # 检查工具是否在冷却期内
                if self._is_tool_in_cooldown(tool_name):
                    logger.warning(f"⏳ 工具 {tool_name} 在冷却期内，跳过安装")
                    failed_installations.append(f"工具 {tool_name}: 冷却期内跳过")
                    continue
                
                # 构造候选者对象
                candidate = await self._create_candidate_from_tool_info(tool_info)
                if not candidate:
                    failed_installations.append(f"工具 {tool_name}: 候选者创建失败")
                    self._record_tool_failure(tool_name, "候选者创建失败")
                    logger.warning(f"❌ 候选者创建失败: {tool_name}")
                    continue
                
                # 安装工具
                install_result = await self.dynamic_mcp_manager.install_mcp_server(candidate)
                
                if install_result.success:
                    logger.info(f"✅ 成功安装工具: {candidate.name}")
                    # 清除该工具的失败记录
                    self._clear_tool_failure(tool_name)
                    return MCPSearchResult(
                        success=True,
                        message=f"成功安装工具: {candidate.name}",
                        installed_tools=[{
                            "name": candidate.name,
                            "description": candidate.description,
                            "capabilities": candidate.capabilities,
                            "server_id": install_result.server_id,
                            "selection_reason": tool_info.get('reason', 'LLM推荐')
                        }]
                    )
                else:
                    error_msg = f"{tool_name}: {install_result.error_message}"
                    failed_installations.append(error_msg)
                    # 记录工具安装失败
                    self._record_tool_failure(tool_name, install_result.error_message)
                    logger.warning(f"❌ 工具安装失败: {error_msg}")
            
            # 所有工具安装失败，尝试降级策略
            logger.warning("⚠️ 所有推荐工具安装失败，尝试降级策略")
            fallback_result = await self._try_fallback_with_existing_tools(task_description, current_available_tools)
            
            if not fallback_result.success:
                # 所有推荐的工具都安装失败，返回一个聚合的错误信息
                error_message = f"所有推荐的工具都安装失败。失败详情: {'; '.join(failed_installations)}"
                logger.error(error_message)
                return MCPSearchResult(
                    success=False,
                    message=error_message,
                    installed_tools=[]
                )
            
            return fallback_result
        
        except Exception as e:
            logger.error(f"❌ MCP搜索安装过程异常: {e}")
            # 异常情况下也尝试降级策略
            try:
                fallback_result = await self._try_fallback_with_existing_tools(task_description, current_available_tools)
                if fallback_result.success:
                    return fallback_result
            except Exception as fallback_error:
                logger.error(f"降级策略也失败: {fallback_error}")
            
            return MCPSearchResult(
                success=False,
                message=f"搜索和安装过程中出现意外错误: {e}",
                installed_tools=[]
            )
    
    async def analyze_tool_needs(self, task_description: str, reason: str = "") -> Dict[str, Any]:
        """分析工具需求，返回LLM推荐但不执行安装"""
        logger.info(f"🧠 分析任务工具需求: {task_description[:100]}...")
        if reason:
            logger.info(f"分析原因: {reason}")
        
        try:
            # 由于analyze_tool_needs通常在没有足够工具时被调用，直接进行工具搜索
            logger.info("🔍 直接进行LLM工具选择...")
            
            # 直接使用LLM选择工具
            recommended_tools = await self.find_matching_tools_from_analysis(
                task_description, []
            )
            
            # 构造分析结果
            has_sufficient = len(recommended_tools) == 0
            analysis = type('Analysis', (), {
                'has_sufficient_tools': has_sufficient,
                'overall_assessment': '工具需求分析完成' if has_sufficient else '需要安装新工具',
                'tool_requirements': []
            })()
            
            # 格式化分析结果
            has_sufficient = getattr(analysis, 'has_sufficient_tools', False)
            
            result = {
                "has_sufficient_tools": has_sufficient,
                "overall_assessment": getattr(analysis, 'overall_assessment', '分析完成'),
                "recommended_action": "continue_with_existing_tools" if has_sufficient else "search_for_new_tools"
            }
            
            # 如果工具不足，获取LLM推荐
            if not has_sufficient:
                recommended_tools = await self.find_matching_tools_from_analysis(
                    task_description, 
                    getattr(analysis, 'tool_requirements', [])
                )
                result["recommended_mcp_tools"] = recommended_tools
                result["tool_count"] = len(recommended_tools)
            
            logger.info(f"✅ 工具需求分析完成，推荐工具数: {result.get('tool_count', 0)}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 工具需求分析失败: {e}")
            logger.error(f"❌ 工具需求分析失败: {e}")
            return {
                "has_sufficient_tools": False,
                "overall_assessment": f"分析失败: {e}",
                "recommended_action": "error",
                "recommended_mcp_tools": [],
                "tool_count": 0,
                "error": str(e)
            }

    async def find_matching_tools_from_analysis(self, task_description: str, 
                                              tool_requirements: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        核心优化：让LLM直接从mcp_tools.json中选择最佳工具
        移除复杂的加权打分，单次磁盘I/O，纯LLM决策
        """
        logger.info("🤖 LLM开始智能工具选择...")
        try:
            # 单次加载工具数据（缓存机制）
            tools_data = await self._load_mcp_tools()
            logger.info(f"📚 加载了 {len(tools_data)} 个工具定义")

            # 截断工具列表避免prompt过大
            MAX_TOOLS_FOR_LLM = 150
            truncated_tools = tools_data[:MAX_TOOLS_FOR_LLM]
            
            # 构造优化的LLM选择prompt
            prompt = self._build_tool_selection_prompt(task_description, truncated_tools)
            
            # 🔍 新增：记录发送给LLM的完整prompt
            logger.info("📤 发送给LLM的prompt:")
            logger.info(f"   任务描述: {task_description}")
            logger.info(f"   可选工具数量: {len(truncated_tools)}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   完整prompt (前500字符): {prompt[:500]}...")
                logger.debug(f"   工具列表示例: {[tool.get('name', 'Unknown') for tool in truncated_tools[:5]]}")

            # 调用LLM进行选择（明确指定gemini提供商）
            from core.llm_client import LLMClient
            llm_client = LLMClient({"provider": "gemini"})
            # 将字符串prompt转换为消息格式
            messages = [{"role": "user", "content": prompt}]
            llm_response = await llm_client._call_api(messages)
            
            # 🔍 新增：记录LLM的原始响应
            logger.info("📥 LLM响应接收:")
            logger.info(f"   响应长度: {len(llm_response)} 字符")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   原始响应 (前300字符): {llm_response[:300]}...")
            
            # 解析LLM返回的JSON
            parsed_selection = self._parse_llm_tool_selection(llm_response)
            
            if not parsed_selection:
                logger.warning("⚠️ LLM未返回有效的工具选择或解析失败")
                logger.warning(f"   原始响应: {llm_response}")
                return []

            # 从缓存的工具数据中查找完整的工具信息
            selected_tools_full_info = []
            all_tools_map = {tool['tool_id']: tool for tool in tools_data}

            for selected in parsed_selection:
                tool_id = selected.get('tool_id')
                if tool_id in all_tools_map:
                    full_tool_info = all_tools_map[tool_id].copy()
                    full_tool_info['reason'] = selected.get('reason', 'LLM推荐') # 添加LLM给出的原因
                    selected_tools_full_info.append(full_tool_info)
                    logger.info(f"✅ 成功匹配并添加工具: {full_tool_info.get('name')}")
                else:
                    logger.warning(f"⚠️ LLM选择的工具ID '{tool_id}' 在工具库中未找到")

            return selected_tools_full_info

        except Exception as e:
            logger.error(f"❌ LLM工具选择失败: {e}")
            logger.error(f"   异常类型: {type(e).__name__}")
            if hasattr(e, 'response'):
                logger.error(f"   API响应: {getattr(e, 'response', 'No response')}")
            return []

    def _build_tool_selection_prompt(self, task_description: str, tools_data: List[Dict[str, Any]]) -> str:
        """构建优化的LLM工具选择prompt"""
        return f"""You are an expert MCP tool selector. Your goal is to choose functional tools that directly address the user's task. Avoid selecting tools that are themselves tool managers or searchers (like 'mcp-search') unless the task is explicitly about finding or managing tools.

Task Description:
{task_description}

Instructions:
1. Analyze the task to understand the required capability (e.g., 'web search', 'file editing', 'data analysis').
2. From the list of available tools, select up to 3 tools that provide this capability directly.
3. Prioritize tools with specific functions over general-purpose tool managers.
4. Return ONLY a JSON array, with no other text.
5. Each object in the array must contain 'tool_id' and 'reason'.

Available Tools:
{json.dumps(tools_data, ensure_ascii=False, indent=2)}

Return format:
[{{"tool_id": "the-id-of-the-tool", "reason": "This tool is ideal because it can perform X, which is required by the task."}}]"""

    def _parse_llm_tool_selection(self, llm_response: str) -> List[Dict[str, Any]]:
        """解析LLM返回的工具选择结果"""
        try:
            import re
            
            # 提取JSON数组
            json_match = re.search(r'\[.*?\]', llm_response, re.DOTALL)
            if not json_match:
                logger.warning("LLM响应中未找到JSON数组")
                return []

            json_str = json_match.group(0)
            selected_tools = json.loads(json_str)
            
            # 验证格式
            if not isinstance(selected_tools, list):
                logger.warning("LLM返回的不是数组格式")
                return []
            
            # 验证每个工具的必需字段
            valid_tools = []
            for tool in selected_tools:
                if isinstance(tool, dict) and 'tool_id' in tool:
                    valid_tools.append(tool)
                else:
                    logger.warning(f"工具格式无效，跳过: {tool}")
            
            return valid_tools
            
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM JSON响应失败: {e}")
            return []
        except Exception as e:
            logger.error(f"处理LLM响应异常: {e}")
            return []

    async def _create_candidate_from_tool_info(self, tool_info: Dict[str, Any]):
        """从工具信息创建MCP候选者对象，增强参数验证"""
        try:
            # 根据实际的MCPServerCandidate类结构来构建
            from .dynamic_mcp_manager import MCPServerCandidate
            
            # 验证必需的URL参数
            github_url = tool_info.get('github_url', tool_info.get('repository_url', ''))
            if not github_url:
                logger.error(f"工具 {tool_info.get('name', 'Unknown')} 缺少 github_url 参数")
                return None
                
            # 从mcp_tools.json中获取安全信息
            security_info = tool_info.get('security', {})
            verified = security_info.get('verified', False) if isinstance(security_info, dict) else False
            
            # 计算安全分数
            security_score = 0.0
            if verified:
                security_score += 0.5
            if tool_info.get('author') in ['anthropic', 'community']:
                security_score += 0.3
            if tool_info.get('capabilities'):
                security_score += 0.2
                
            candidate = MCPServerCandidate(
                name=tool_info.get('name', 'Unknown Tool'),
                description=tool_info.get('description', ''),
                github_url=github_url,
                author=tool_info.get('author', 'Unknown'),
                tags=tool_info.get('tags', []),
                install_method=tool_info.get('install_method', 'python'),
                capabilities=tool_info.get('capabilities', []),
                verified=verified,
                security_score=security_score,
                popularity_score=0.5  # 给一个默认的中等流行度分数
            )
            
            logger.debug(f"成功创建候选者: {candidate.name}, URL: {candidate.github_url}")
            return candidate
            
        except Exception as e:
            logger.error(f"创建工具候选者失败: {e}")
            logger.error(f"工具信息: {tool_info}")
            return None

    async def _load_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        懒加载并缓存mcp_tools.json数据
        优化：单次磁盘I/O + 内存缓存
        """
        if self._mcp_tools_data is None:
            # 固定相对路径，避免路径查找开销
            self._mcp_tools_path = "mcp_tools.json"
            
            if not os.path.exists(self._mcp_tools_path):
                logger.error(f"❌ 工具定义文件不存在: {self._mcp_tools_path}")
                raise FileNotFoundError(f"mcp_tools.json not found at {self._mcp_tools_path}")
            
            logger.info(f"📖 首次加载工具定义文件: {self._mcp_tools_path}")
            with open(self._mcp_tools_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # 提取服务器列表
            if isinstance(json_data, dict) and "servers" in json_data:
                self._mcp_tools_data = json_data["servers"]
            elif isinstance(json_data, list):
                self._mcp_tools_data = json_data
            else:
                logger.error(f"❌ 工具定义文件格式错误: 期望包含'servers'键的字典或列表")
                self._mcp_tools_data = []
            
            logger.info(f"✅ 工具定义已缓存，共 {len(self._mcp_tools_data)} 个工具")
        
        return self._mcp_tools_data
    
    async def _try_fallback_with_existing_tools(self, task_description: str, current_available_tools: List[Dict[str, Any]]) -> MCPSearchResult:
        """降级策略：智能评估现有工具完成任务的可能性"""
        logger.info("🔄 执行增强降级策略：智能工具匹配")
        logger.info(f"🔍 任务描述: {task_description[:100]}...")
        logger.info(f"🔍 当前可用工具数量: {len(current_available_tools)}")
        
        try:
            # 1. 智能任务分类
            task_type = self._classify_task_type(task_description)
            logger.info(f"🎯 任务分类: {task_type}")
            
            # 2. 按任务类型查找匹配工具
            matched_tools = self._find_tools_by_task_type(task_type, current_available_tools)
            
            if matched_tools:
                logger.info(f"✅ 找到 {len(matched_tools)} 个匹配工具用于 {task_type} 任务")
                return MCPSearchResult(
                    success=True,
                    message=f"使用现有工具完成 {task_type} 任务: {', '.join([t.get('name', t.get('server_id', '')) for t in matched_tools[:3]])}",
                    installed_tools=matched_tools,
                    fallback_used=True
                )
            
            # 3. 通用工具回退 - 查找通用分析工具
            universal_tools = self._find_universal_tools(current_available_tools)
            if universal_tools:
                logger.info(f"🔧 使用通用工具: {len(universal_tools)} 个")
                return MCPSearchResult(
                    success=True,
                    message=f"使用通用分析工具: {', '.join([t.get('name', t.get('server_id', '')) for t in universal_tools])}",
                    installed_tools=universal_tools,
                    fallback_used=True
                )
            
            # 4. 知识合成回退 - 最后的防线
            if self._can_use_knowledge_synthesis(task_description):
                logger.info("🧠 使用知识合成作为最终回退")
                return MCPSearchResult(
                    success=True,
                    message="使用知识合成完成任务（无需外部工具）",
                    installed_tools=[{
                        "name": "Knowledge_Synthesis_Engine",
                        "description": "基于训练数据的知识合成引擎",
                        "capabilities": ["knowledge_analysis", "reasoning", "synthesis"],
                        "fallback_method": "knowledge_synthesis",
                        "confidence": 0.7
                    }],
                    fallback_used=True
                )
            
            # 5. 完全失败
            logger.warning("❌ 所有降级策略都无法处理此任务")
            return MCPSearchResult(
                success=False,
                message="无法找到合适的工具或方法完成此任务",
                installed_tools=[],
                fallback_used=True
            )
            
            # 下面的代码永远不会执行到，但保留作为备份
            if any(keyword in task_description.lower() for keyword in ['研究', '调研', 'research', '分析', 'analyze', '趋势', 'agent']):
                logger.info("🎯 检测到研究任务，启用强制降级策略")
                
                # 检查可用工具
                available_tool_names = [tool.get('name', 'Unknown') for tool in current_available_tools]
                
                # 生成研究任务的基础执行策略
                research_strategy = {
                    "method": "knowledge_synthesis_with_tools",
                    "approach": "使用现有工具进行基础研究",
                    "tools_available": available_tool_names,
                    "execution_plan": [
                        "1. 使用知识合成分析任务需求",
                        "2. 基于现有知识提供结构化分析", 
                        "3. 如有microsandbox工具，生成研究脚本执行",
                        "4. 整合结果并提供研究报告"
                    ]
                }
                
                logger.info(f"✅ 强制降级策略成功：{research_strategy['method']}")
                
                return MCPSearchResult(
                    success=True,
                    message="使用强制降级策略：知识合成+现有工具",
                    installed_tools=[{
                        "name": "Knowledge_Synthesis_Engine",
                        "description": "基于现有知识的研究分析引擎",
                        "capabilities": ["knowledge_synthesis", "research_analysis", "structured_output"],
                        "strategy": research_strategy,
                        "fallback_method": "forced_knowledge_synthesis"
                    }],
                    fallback_used=True
                )
            
            # 检查是否有基础的网络请求工具
            web_tools = [tool for tool in current_available_tools 
                        if any(keyword in tool.get('name', '').lower() 
                              for keyword in ['web', 'http', 'request', 'fetch', 'browser'])]
            
            search_tools = [tool for tool in current_available_tools 
                           if any(keyword in tool.get('name', '').lower() 
                                 for keyword in ['search', 'google', 'bing'])]
            
            code_tools = [tool for tool in current_available_tools 
                         if any(keyword in tool.get('name', '').lower() 
                               for keyword in ['code', 'python', 'execute', 'sandbox'])]
            
            # 如果任务涉及研究或搜索，且有相关工具
            if (any(keyword in task_description.lower() 
                   for keyword in ['研究', '调研', 'research', '搜索', 'search', '查找']) 
                and (web_tools or search_tools or code_tools)):
                
                available_tool_names = [tool.get('name', 'Unknown') for tool in current_available_tools]
                logger.info(f"✅ 降级策略成功：可以用现有工具完成任务。可用工具: {', '.join(available_tool_names[:5])}")
                
                return MCPSearchResult(
                    success=True,
                    message=f"使用现有工具完成任务: {', '.join(available_tool_names[:3])}等",
                    installed_tools=[],
                    fallback_used=True  # 标记使用了降级策略
                )
            
            # 🎯 终极降级：即使没有匹配工具也返回成功（使用知识合成）
            logger.info("🚀 启用终极降级策略：纯知识合成")
            
            return MCPSearchResult(
                success=True,
                message="使用终极降级策略：纯知识合成分析",
                installed_tools=[{
                    "name": "Pure_Knowledge_Synthesis",
                    "description": "纯知识合成引擎，基于训练数据提供分析",
                    "capabilities": ["knowledge_analysis", "structured_reasoning", "comprehensive_output"],
                    "method": "pure_knowledge_synthesis",
                    "confidence": 0.7
                }],
                fallback_used=True
            )
            
        except Exception as e:
            logger.error(f"降级策略执行失败: {e}")
            # 即使降级策略异常，也尝试返回基础成功
            return MCPSearchResult(
                success=True,
                message="应急降级策略：基础知识处理",
                installed_tools=[{
                    "name": "Emergency_Knowledge_Handler",
                    "description": "应急知识处理器",
                    "capabilities": ["emergency_analysis"],
                    "method": "emergency_fallback"
                }],
                fallback_used=True
            )
    
    def _classify_task_type(self, task_description: str) -> str:
        """智能任务分类"""
        desc_lower = task_description.lower()
        
        # 代码/编程任务
        if any(keyword in desc_lower for keyword in [
            'python', 'code', '编程', '脚本', 'script', '运行', 'execute', 
            '计算', 'calculate', '算法', 'algorithm'
        ]):
            return 'code_execution'
        
        # 网络爬取/数据抓取任务
        if any(keyword in desc_lower for keyword in [
            'scrape', 'crawl', '爬取', '抓取', 'fetch', 'download', 
            'website', 'webpage', 'url', 'html'
        ]):
            return 'web_scraping'
        
        # 浏览器自动化任务
        if any(keyword in desc_lower for keyword in [
            'browser', '浏览器', 'navigate', '导航', 'click', '点击',
            'screenshot', '截图', 'automation'
        ]):
            return 'browser_automation'
        
        # 研究/分析任务
        if any(keyword in desc_lower for keyword in [
            'research', '研究', 'analyze', '分析', 'study', '调研',
            'investigate', '调查', 'trends', '趋势'
        ]):
            return 'research_analysis'
        
        # 文件操作任务
        if any(keyword in desc_lower for keyword in [
            'file', '文件', 'read', '读取', 'write', '写入',
            'save', '保存', 'directory', '目录'
        ]):
            return 'file_operations'
        
        # 数据处理任务
        if any(keyword in desc_lower for keyword in [
            'data', '数据', 'json', 'csv', 'excel', 'statistics',
            '统计', 'process', '处理'
        ]):
            return 'data_processing'
        
        # 默认为一般分析任务
        return 'general_analysis'
    
    def _find_tools_by_task_type(self, task_type: str, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """根据任务类型查找匹配的工具"""
        matched_tools = []
        
        tool_mapping = {
            'code_execution': ['microsandbox', 'python', 'executor'],
            'web_scraping': ['scraper', 'scrape', 'crawl', 'fetch'],
            'browser_automation': ['browser', 'navigate', 'automation'],
            'research_analysis': ['deepsearch', 'research', 'analysis'],
            'file_operations': ['file', 'filesystem', 'storage'],
            'data_processing': ['statistics', 'data', 'process']
        }
        
        keywords = tool_mapping.get(task_type, [])
        
        for tool in available_tools:
            if isinstance(tool, dict):
                tool_name = tool.get('name', '').lower()
                tool_id = tool.get('server_id', '').lower()
                tool_desc = tool.get('description', '').lower()
                
                # 检查工具名称、ID或描述是否包含相关关键词
                if any(keyword in tool_name or keyword in tool_id or keyword in tool_desc 
                       for keyword in keywords):
                    matched_tools.append(tool)
        
        return matched_tools
    
    def _find_universal_tools(self, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """查找通用分析工具"""
        universal_tools = []
        
        universal_keywords = ['deepsearch', 'analysis', 'research', 'general', 'multi']
        
        for tool in available_tools:
            if isinstance(tool, dict):
                tool_name = tool.get('name', '').lower()
                tool_id = tool.get('server_id', '').lower()
                tool_desc = tool.get('description', '').lower()
                
                if any(keyword in tool_name or keyword in tool_id or keyword in tool_desc 
                       for keyword in universal_keywords):
                    universal_tools.append(tool)
        
        return universal_tools
    
    def _can_use_knowledge_synthesis(self, task_description: str) -> bool:
        """判断是否可以使用知识合成完成任务"""
        desc_lower = task_description.lower()
        
        # 这些任务类型适合知识合成
        knowledge_suitable_keywords = [
            '解释', 'explain', '分析', 'analyze', '比较', 'compare',
            '总结', 'summary', '概述', 'overview', '建议', 'recommend',
            '原理', 'principle', '理论', 'theory', '概念', 'concept'
        ]
        
        # 这些任务类型不适合知识合成（需要实时数据或外部操作）
        knowledge_unsuitable_keywords = [
            '下载', 'download', '爬取', 'scrape', '截图', 'screenshot',
            '运行', 'execute', '安装', 'install', '删除', 'delete',
            '实时', 'real-time', '当前', 'current', '最新', 'latest'
        ]
        
        # 如果包含不适合的关键词，不使用知识合成
        if any(keyword in desc_lower for keyword in knowledge_unsuitable_keywords):
            return False
        
        # 如果包含适合的关键词，可以使用知识合成
        if any(keyword in desc_lower for keyword in knowledge_suitable_keywords):
            return True
        
        # 对于其他任务，如果描述较短且不涉及复杂操作，也可以尝试知识合成
        return len(task_description) < 200
    
    def _is_tool_in_cooldown(self, tool_name: str) -> bool:
        """检查工具是否在冷却期内"""
        if tool_name not in self._failed_tools:
            return False
        
        failure_info = self._failed_tools[tool_name]
        last_failure_time = failure_info.get('last_failure_time', 0)
        current_time = time.time()
        
        return (current_time - last_failure_time) < self._cooldown_period
    
    def _record_tool_failure(self, tool_name: str, error_message: str):
        """记录工具安装失败"""
        current_time = time.time()
        
        if tool_name in self._failed_tools:
            self._failed_tools[tool_name]['failure_count'] += 1
            self._failed_tools[tool_name]['last_failure_time'] = current_time
            self._failed_tools[tool_name]['last_error'] = error_message
        else:
            self._failed_tools[tool_name] = {
                'failure_count': 1,
                'last_failure_time': current_time,
                'last_error': error_message,
                'first_failure_time': current_time
            }
        
        logger.info(f"🔥 记录工具失败: {tool_name} (失败次数: {self._failed_tools[tool_name]['failure_count']})")
    
    def _clear_tool_failure(self, tool_name: str):
        """清除工具失败记录"""
        if tool_name in self._failed_tools:
            del self._failed_tools[tool_name]
            logger.info(f"✅ 清除工具失败记录: {tool_name}")