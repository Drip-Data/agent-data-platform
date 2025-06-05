"""
Research Tracker for Deep Research module
深度研究模块的轨迹记录器
"""

import json
import time
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


# LoopTrace dataclass is no longer needed as we'll manage dicts directly.
# Remove or comment out:
# @dataclass
# class LoopTrace:
#     """单个循环的轨迹记录"""
#     loop_number: int
#     timestamp: str
#     is_sufficient: bool
#     queries_generated: int # This will become follow_up_queries_generated
#     sources_found: int     # This will be total_sources_this_loop
#     knowledge_gap: str
#     execution_time: float
#     search_queries: List[str] = field(default_factory=list) # This will be executed_searches (list of dicts)

class ResearchTracker:
    """研究轨迹记录器"""
    
    def __init__(self, research_topic: str = ""):
        self.start_time = time.time()
        self.trace = {
            "research_id": f"research_{int(self.start_time)}",
            "start_time": datetime.now().isoformat(),
            "research_topic": research_topic,
            "config": {},
            "loops": [],  # List of loop detail dictionaries
            # Keep counters consistent with summary field names
            "total_queries": 0,  # Overall count of queries executed
            "sources_count": 0,   # Overall count of sources found
            "forced_exit": False,
            "exit_reason": "",
            "status": "running"
        }
    
    def set_config(self, config: Dict[str, Any]):
        """设置研究配置"""
        self.trace["config"] = {
            "max_research_loops": config.get("max_research_loops", 3),
            "initial_search_query_count": config.get("initial_search_query_count", 3),
            "reasoning_model": config.get("reasoning_model", "gemini-2.0-flash-exp")
        }
    
    def record_loop_start(self, loop_num: int) -> float:
        """记录循环开始，并为该循环初始化结构"""
        loop_start_time = time.time()
        # 确保loops列表足够长
        while len(self.trace["loops"]) < loop_num:
            self.trace["loops"].append({}) # 添加空字典，稍后填充
        
        # 初始化或重置当前循环的数据
        current_loop_index = loop_num - 1
        self.trace["loops"][current_loop_index] = {
            "loop_number": loop_num,
            "timestamp_start": datetime.now().isoformat(),
            "executed_searches": [], # [{"query": str, "num_sources": int}]
            "total_sources_this_loop": 0,
            # Fields to be filled by record_loop_end
            "timestamp_end": None,
            "execution_time": 0.0,
            "is_sufficient": False,
            "knowledge_gap": "",
            "follow_up_queries_generated": []
        }
        return loop_start_time

    def record_search_executed(self, loop_num: int, query_str: str, num_sources: int):
        """记录在特定循环中执行的单个搜索及其结果"""
        if loop_num > 0 and loop_num <= len(self.trace["loops"]):
            current_loop_index = loop_num - 1
            loop_data = self.trace["loops"][current_loop_index]
            
            loop_data["executed_searches"].append({
                "query": query_str,
                "num_sources": num_sources
            })
            loop_data["total_sources_this_loop"] += num_sources
            
            # Update global counters
            self.trace["total_queries"] += 1
            self.trace["sources_count"] += num_sources
        else:
            # 这通常不应该发生，如果发生了，说明循环编号管理有问题
            print(f"警告: 尝试为无效的循环编号 {loop_num} 记录搜索结果。轨迹可能不准确。")

    def record_loop_end(self,
                       loop_num: int,
                       loop_start_time: float,
                       is_sufficient: bool,
                       follow_up_queries: List[str], # Queries generated for the *next* loop
                       knowledge_gap: str = ""):
        """记录循环结束，更新循环的最终信息"""
        if loop_num > 0 and loop_num <= len(self.trace["loops"]):
            current_loop_index = loop_num - 1
            loop_data = self.trace["loops"][current_loop_index]
            
            loop_data.update({
                "timestamp_end": datetime.now().isoformat(),
                "execution_time": time.time() - loop_start_time,
                "is_sufficient": is_sufficient,
                "knowledge_gap": knowledge_gap,
                "follow_up_queries_generated": follow_up_queries
            })
        else:
            # 这通常不应该发生
            print(f"警告: 尝试为无效的循环编号 {loop_num} 记录循环结束。轨迹可能不准确。")
        
        # total_queries 和 sources_count 在 record_search_executed 中累加
        # 此处无需额外更新全局 total_queries 和 sources_count
    
    def record_forced_exit(self, reason: str):
        """记录强制退出"""
        self.trace["forced_exit"] = True
        self.trace["exit_reason"] = reason
        self.trace["status"] = "forced_exit"
    
    def record_normal_exit(self, reason: str):
        """记录正常退出"""
        self.trace["forced_exit"] = False
        self.trace["exit_reason"] = reason
        self.trace["status"] = "completed"
    
    def record_error(self, error: str):
        """记录错误"""
        self.trace["status"] = "error"
        self.trace["error"] = error
        self.trace["exit_reason"] = f"Error: {error}"
    
    def get_trace_summary(self) -> Dict[str, Any]:
        """获取轨迹摘要"""
        return {
            "research_id": self.trace["research_id"],
            "total_duration": time.time() - self.start_time,
            "total_loops": len(self.trace["loops"]),
            "total_queries": self.trace["total_queries"],
            "sources_count": self.trace["sources_count"],
            "status": self.trace["status"],
            "exit_reason": self.trace["exit_reason"]
        }
    
    def get_trace_data(self) -> Dict[str, Any]:
        """
        获取完整的轨迹数据（不写入文件）
        由 runtime.py 统一处理轨迹保存，避免双重写入冲突
        """
        # 完成轨迹记录
        self.trace["end_time"] = datetime.now().isoformat()
        self.trace["total_duration"] = time.time() - self.start_time

        # 如果仍处于 running 状态，根据已有记录判断研究是否完成
        if self.trace.get("status") == "running":
            if self.trace.get("loops"):
                self.trace["status"] = "completed"

        # 返回轨迹数据副本，让 runtime.py 处理保存
        return self.trace.copy()
    
    def save_trace_to_file(self, filepath: Optional[str] = None) -> str:
        """
        直接保存轨迹到文件（仅在独立使用时调用）
        ⚠️ 警告：在 runtime.py 集成环境中不应调用此方法，避免轨迹冲突
        """
        # 完成轨迹记录
        self.trace["end_time"] = datetime.now().isoformat()
        self.trace["total_duration"] = time.time() - self.start_time
        
        if not filepath:
            # 使用默认文件名（避免与 runtime.py 冲突）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"deep_research_individual_trace_{timestamp}_{self.trace['research_id'][:8]}.json"
            
            # 确定保存目录
            output_dir = os.getenv('OUTPUT_DIR', '/app/output/trajectories')
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.trace, f, ensure_ascii=False, indent=2)
            
            print(f"研究轨迹已保存到: {filepath}")
            return filepath
            
        except Exception as e:
            print(f"保存轨迹文件失败: {e}")
            return ""
    
    def _calculate_query_success_rate(self) -> float:
        """计算查询成功率"""
        total_queries = sum(len(loop.get("search_queries", [])) for loop in self.trace["loops"])
        if total_queries == 0:
            return 0.0
        
        successful_queries = sum(
            loop.get("sources_found", 0) > 0 and len(loop.get("search_queries", [])) > 0
            for loop in self.trace["loops"]
        )
        return successful_queries / len(self.trace["loops"]) if self.trace["loops"] else 0.0
    
    def get_final_status(self) -> str:
        """获取最终状态"""
        return self.trace.get("status", "running")
    
    def log_progress(self):
        """输出进度日志"""
        summary = self.get_trace_summary()
        print(f"[研究进度] 循环: {summary['total_loops']}, "
              f"查询: {summary['total_queries']}, "
              f"来源: {summary['sources_count']}, "
              f"状态: {summary['status']}")


def create_tracker(research_topic: str) -> ResearchTracker:
    """创建研究轨迹记录器"""
    return ResearchTracker(research_topic)


def load_trace(filepath: str) -> Optional[Dict[str, Any]]:
    """加载研究轨迹"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载轨迹文件失败: {e}")
        return None


def analyze_traces(traces_dir: str = "Tool_Use_Train/agent-data-platform/traces") -> Dict[str, Any]:
    """分析多个研究轨迹"""
    if not os.path.exists(traces_dir):
        return {"error": "轨迹目录不存在"}
    
    analysis = {
        "total_traces": 0,
        "completed": 0,
        "forced_exit": 0,
        "errors": 0,
        "avg_duration": 0,
        "avg_loops": 0,
        "avg_queries": 0
    }
    
    durations = []
    loops = []
    queries = []
    
    for filename in os.listdir(traces_dir):
        if filename.endswith('.json'):
            trace = load_trace(os.path.join(traces_dir, filename))
            if trace:
                analysis["total_traces"] += 1
                
                if trace["status"] == "completed":
                    analysis["completed"] += 1
                elif trace["status"] == "forced_exit":
                    analysis["forced_exit"] += 1
                elif trace["status"] == "error":
                    analysis["errors"] += 1
                
                if "total_duration" in trace:
                    durations.append(trace["total_duration"])
                
                loops.append(len(trace.get("loops", [])))
                queries.append(trace.get("total_queries", 0))
    
    if durations:
        analysis["avg_duration"] = sum(durations) / len(durations)
    if loops:
        analysis["avg_loops"] = sum(loops) / len(loops)
    if queries:
        analysis["avg_queries"] = sum(queries) / len(queries)
    
    return analysis