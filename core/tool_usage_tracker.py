"""
工具使用跟踪器
负责记录任务执行过程中的工具使用情况
"""

import logging
from typing import Dict, Any, List, Set
from dataclasses import dataclass, field
import time

logger = logging.getLogger(__name__)

@dataclass
class ToolUsageRecord:
    """单次工具使用记录"""
    tool_server_id: str          # MCP服务器ID (如 "python-executor-mcp-server")
    tool_server_name: str        # MCP服务器名称 (如 "Python Executor")
    action: str                  # 具体调用的工具/动作 (如 "python_execute")
    parameters: Dict[str, Any]   # 调用参数
    timestamp: float             # 调用时间
    duration: float = 0.0        # 执行时长
    success: bool = True         # 是否成功
    result: str = ""             # 执行结果
    is_meta: bool = False        # 是否为元数据步骤（如工具快照）

class ToolUsageTracker:
    """工具使用跟踪器"""
    
    def __init__(self):
        self.available_tools: List[Dict[str, Any]] = []
        self.used_tools_records: List[ToolUsageRecord] = []
        self.used_tool_servers: Set[str] = set()  # 使用过的MCP服务器ID集合
        
    def set_available_tools(self, available_tools_info: str) -> None:
        """设置任务开始时可用的工具信息"""
        self.available_tools = self._parse_available_tools(available_tools_info)
        logger.info(f"📋 记录可用工具: {len(self.available_tools)} 个MCP服务器")
        
    def record_tool_usage(self, 
                         tool_server_id: str, 
                         action: str, 
                         parameters: Dict[str, Any],
                         result: str = "",
                         success: bool = True,
                         duration: float = 0.0,
                         is_meta: bool = False) -> None:
        """记录工具使用"""
        
        # 查找对应的服务器名称
        tool_server_name = self._get_server_name(tool_server_id)

        record = ToolUsageRecord(
            tool_server_id=tool_server_id,
            tool_server_name=tool_server_name,
            action=action,
            parameters=parameters,
            timestamp=time.time(),
            duration=duration,
            success=success,
            result=result
        )
        
        # 🔧 新增：为记录添加元数据标记
        record.is_meta = is_meta
        
        self.used_tools_records.append(record)
        self.used_tool_servers.add(tool_server_id)
        
        log_type = "📊 记录元数据" if is_meta else "🔧 记录工具使用"
        logger.info(f"{log_type}: {tool_server_id}.{action}")
        
    def get_usage_stats(self) -> Dict[str, Any]:
        """获取工具使用统计信息"""
        stats = {
            "total_usage_count": len(self.used_tools_records),
            "successful_count": sum(1 for r in self.used_tools_records if r.success),
            "failed_count": sum(1 for r in self.used_tools_records if not r.success),
            "unique_tools_used": len(self.used_tool_servers),
            "usage_by_tool": {},
        }

        for record in self.used_tools_records:
            if record.tool_server_id not in stats["usage_by_tool"]:
                stats["usage_by_tool"][record.tool_server_id] = {
                    "count": 0,
                    "actions": {},
                    "total_duration": 0.0,
                }
            
            tool_stats = stats["usage_by_tool"][record.tool_server_id]
            tool_stats["count"] += 1
            tool_stats["total_duration"] += record.duration
            
            if record.action not in tool_stats["actions"]:
                tool_stats["actions"][record.action] = {
                    "count": 0,
                    "total_duration": 0.0,
                }
            
            action_stats = tool_stats["actions"][record.action]
            action_stats["count"] += 1
            action_stats["total_duration"] += record.duration

        return stats
        
    def get_available_tools_summary(self) -> List[Dict[str, Any]]:
        """获取可用工具摘要"""
        return self.available_tools
        
    def get_used_tools_summary(self) -> Dict[str, bool]:
        """获取使用过的工具摘要 - 字典格式，True表示成功，False表示失败"""
        used_tools_dict = {}
        
        for record in self.used_tools_records:
            # 使用 server_id.action 作为key，记录是否成功
            tool_key = f"{record.tool_server_id}.{record.action}"
            
            # 如果同一个工具被多次调用，只要有一次成功就标记为True
            if tool_key in used_tools_dict:
                used_tools_dict[tool_key] = used_tools_dict[tool_key] or record.success
            else:
                used_tools_dict[tool_key] = record.success
                
        logger.info(f"🔧 总结工具使用: {len(used_tools_dict)} 个工具调用记录")
        return used_tools_dict
    
    def get_detailed_tool_calls(self) -> List[Dict[str, Any]]:
        """获取详细的工具调用记录"""
        return [
            {
                "server_id": record.tool_server_id,
                "server_name": record.tool_server_name,
                "action": record.action,
                "parameters": record.parameters,
                "timestamp": record.timestamp,
                "duration": record.duration,
                "success": record.success,
                "result": record.result[:200] + "..." if len(record.result) > 200 else record.result  # 限制结果长度
            }
            for record in self.used_tools_records
        ]
    
    def _parse_available_tools(self, tools_info: str) -> List[Dict[str, Any]]:
        """解析可用工具信息 - 支持多种格式"""
        available_tools = []
        
        if not tools_info or "暂无可用工具" in tools_info:
            return available_tools
        
        try:
            # 解析工具描述文本
            lines = tools_info.split('\n')
            current_tool = None
            
            for line in lines:
                line = line.strip()
                
                # 检测新的结构化工具格式: "- **tool-id** (Tool Name): description"
                if line.startswith('- **') and '**' in line[4:]:
                    # 提取工具ID和描述
                    parts = line[4:].split('**', 1)  # 移除 "- **" 前缀
                    if len(parts) == 2:
                        tool_id = parts[0].strip()
                        rest = parts[1].strip()
                        
                        # 提取工具名称和描述
                        if rest.startswith('(') and '):' in rest:
                            name_end = rest.index('):')
                            tool_name = rest[1:name_end]
                            description = rest[name_end+2:].strip()
                        else:
                            tool_name = self._get_server_name(tool_id)
                            description = rest.lstrip(':').strip()
                        
                        current_tool = {
                            "server_id": tool_id,
                            "server_name": tool_name,
                            "description": description,
                            "available_actions": []
                        }
                        available_tools.append(current_tool)
                
                # 检测操作行: "    • action_name: description" 或 "  📋 可用操作:"
                elif line.startswith('    •') and current_tool is not None:
                    action_part = line[5:].strip()  # 移除 "    •" 前缀
                    if ':' in action_part:
                        action_name = action_part.split(':', 1)[0].strip()
                        current_tool["available_actions"].append(action_name)
                # 新格式支持: "  📋 可用操作:" 后面的操作行
                elif line.startswith('  📋 可用操作:') and current_tool is not None:
                    # 这是操作列表的开始标记，继续读取下面的操作
                    continue
                elif (line.startswith('    • ') or line.startswith('      • ')) and current_tool is not None:
                    # 处理操作行: "    • action_name: description" 或 "      • action_name: description"
                    action_part = line.lstrip(' •').strip()
                    if ':' in action_part:
                        action_name = action_part.split(':', 1)[0].strip()
                        if action_name and action_name not in current_tool["available_actions"]:
                            current_tool["available_actions"].append(action_name)
                
                # 兼容旧格式: "- server-id: 可用工具 (操作: action1, action2, action3)"
                elif line.startswith('- ') and ':' in line and '**' not in line:
                    parts = line[2:].split(':', 1)  # 移除 "- " 前缀
                    if len(parts) == 2:
                        server_id = parts[0].strip()
                        description = parts[1].strip()
                        
                        # 提取操作列表
                        actions = []
                        if '操作:' in description:
                            actions_part = description.split('操作:')[1]
                            if ')' in actions_part:
                                actions_text = actions_part.split(')')[0]
                                actions = [action.strip() for action in actions_text.split(',')]
                        
                        available_tools.append({
                            "server_id": server_id,
                            "server_name": self._get_server_name(server_id),
                            "description": description,
                            "available_actions": actions
                        })
                        current_tool = None  # 重置当前工具，避免后续操作被误加入
                        
        except Exception as e:
            logger.warning(f"解析可用工具信息失败: {e}")
            logger.debug(f"原始工具信息: {tools_info}")
        
        return available_tools
    
    def _get_server_name(self, server_id: str) -> str:
        """根据服务器ID获取友好名称"""
        name_mapping = {
            "python-executor-mcp-server": "Python Executor",
            "browser-navigator-mcp-server": "Browser Navigator", 
            "search-tool-server": "Search Tool",
            "mcp-search-tool": "MCP Search Tool",
            "microsandbox-mcp-server": "MicroSandbox",
            "database-server": "Database Server",
            "file-operations-server": "File Operations",
            "web-scraper-server": "Web Scraper"
        }
        return name_mapping.get(server_id, server_id.replace('-', ' ').title())
    
    def get_usage_statistics(self) -> Dict[str, Any]:
        """获取使用统计信息 - 排除元数据步骤"""
        # 过滤出真实的工具调用（排除元数据步骤）
        real_tool_calls = [record for record in self.used_tools_records if not getattr(record, 'is_meta', False)]
        
        return {
            "available_tools_count": len(self.available_tools),
            "used_servers_count": len(self.used_tool_servers),
            "total_tool_calls": len(real_tool_calls),  # 只计算真实工具调用
            "successful_calls": sum(1 for record in real_tool_calls if record.success),  # 只计算真实成功调用
            "total_execution_time": sum(record.duration for record in real_tool_calls),
            "tool_usage_rate": len(self.used_tool_servers) / max(len(self.available_tools), 1),
            # 🔧 新增：元数据统计
            "meta_steps_count": len(self.used_tools_records) - len(real_tool_calls)
        }