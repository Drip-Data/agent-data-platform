#!/usr/bin/env python3
"""
简化种子任务生成器
绕过LLM API调用，直接从轨迹生成种子任务
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class SimpleSeedGenerator:
    """简化的种子任务生成器"""
    
    def __init__(self, trajectories_file: str, seed_tasks_file: str, processed_file: str):
        self.trajectories_file = trajectories_file
        self.seed_tasks_file = seed_tasks_file
        self.processed_file = processed_file
        
        # 加载已处理记录
        self.processed_trajectories = self._load_processed_trajectories()
    
    def _load_processed_trajectories(self) -> set:
        """加载已处理轨迹记录"""
        try:
            if os.path.exists(self.processed_file):
                with open(self.processed_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('processed', []))
            return set()
        except Exception as e:
            logger.error(f"❌ 加载已处理记录失败: {e}")
            return set()
    
    def _save_processed_trajectories(self):
        """保存已处理轨迹记录"""
        try:
            data = {
                "processed": list(self.processed_trajectories),
                "last_updated": datetime.now().isoformat(),
                "total_count": len(self.processed_trajectories)
            }
            
            with open(self.processed_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"❌ 保存已处理记录失败: {e}")
    
    def process_trajectories(self) -> Dict[str, Any]:
        """处理轨迹并生成种子任务"""
        logger.info(f"🔄 开始处理轨迹文件: {self.trajectories_file}")
        
        try:
            # 读取轨迹文件
            with open(self.trajectories_file, 'r', encoding='utf-8') as f:
                trajectories = json.load(f)
            
            if not isinstance(trajectories, list):
                trajectories = trajectories.get('trajectories', [])
            
            # 筛选新轨迹
            new_trajectories = [
                traj for traj in trajectories 
                if traj.get('task_id') not in self.processed_trajectories
            ]
            
            logger.info(f"📊 总轨迹: {len(trajectories)}, 新轨迹: {len(new_trajectories)}")
            
            if not new_trajectories:
                return {"success": True, "new_tasks": 0, "message": "无新轨迹需要处理"}
            
            # 生成种子任务
            seed_tasks = []
            for trajectory in new_trajectories:
                seed_task = self._generate_seed_task_from_trajectory(trajectory)
                if seed_task:
                    seed_tasks.append(seed_task)
                    
                # 标记为已处理
                self.processed_trajectories.add(trajectory.get('task_id'))
            
            # 保存种子任务
            if seed_tasks:
                self._append_seed_tasks(seed_tasks)
            
            # 保存已处理记录
            self._save_processed_trajectories()
            
            result = {
                "success": True,
                "new_tasks": len(seed_tasks),
                "processed_trajectories": len(new_trajectories),
                "total_seed_tasks": self._count_total_seed_tasks()
            }
            
            logger.info(f"✅ 处理完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 处理轨迹失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_seed_task_from_trajectory(self, trajectory: Dict) -> Optional[Dict]:
        """从轨迹生成种子任务（简化版本，不依赖LLM）"""
        try:
            task_id = trajectory.get('task_id', f'unknown_{int(time.time())}')
            description = trajectory.get('task_description', '').strip()
            success = trajectory.get('success', False)
            
            # 处理成功的轨迹或有步骤的轨迹
            steps = trajectory.get('steps', [])
            if not description:
                logger.debug(f"⏩ 跳过轨迹 {task_id}: 无描述")
                return None
            
            # 如果轨迹不成功但有步骤，也可以处理
            if not success and len(steps) == 0:
                logger.debug(f"⏩ 跳过轨迹 {task_id}: 不成功且无步骤")
                return None
            
            # 从步骤中推断工具使用
            tools_used = self._extract_tools_from_steps(steps)
            
            # 推断任务类型
            task_type = self._infer_task_type(description, tools_used)
            
            # 估算最大步数
            max_steps = max(len(steps), 3)
            
            # 生成种子任务
            seed_task = {
                "task_id": f"seed_simple_{task_id}",
                "task_type": task_type,
                "description": description,
                "expected_tools": tools_used,
                "max_steps": max_steps,
                "success_criteria": {
                    "requires_completion": True,
                    "accuracy_threshold": 0.8
                },
                "metadata": {
                    "source": "simple_generator",
                    "original_task_id": task_id,
                    "original_success": success,
                    "steps_count": len(steps),
                    "created_at": datetime.now().isoformat(),
                    "generation_method": "pattern_based"
                }
            }
            
            logger.info(f"✅ 生成种子任务: {seed_task['task_id']} ({task_type})")
            return seed_task
            
        except Exception as e:
            logger.error(f"❌ 生成种子任务失败: {e}")
            return None
    
    def _extract_tools_from_steps(self, steps: List[Dict]) -> List[str]:
        """从步骤中提取使用的工具"""
        tools = set()
        
        for step in steps:
            # 检查tool_input字段
            tool_input = step.get('tool_input', {})
            if isinstance(tool_input, dict):
                # 从tools_snapshot中提取
                snapshot = tool_input.get('tools_snapshot', '')
                if 'microsandbox' in snapshot:
                    tools.add('python_executor')
                if 'search' in snapshot or 'research' in snapshot:
                    tools.add('deepsearch') 
                if 'browser' in snapshot:
                    tools.add('browser_navigator')
            
            # 检查action_params字段
            action_params = step.get('action_params', {})
            if isinstance(action_params, dict):
                tool_id = action_params.get('tool_id', '')
                if tool_id:
                    tools.add(tool_id)
        
        return list(tools) if tools else ['reasoning']
    
    def _infer_task_type(self, description: str, tools: List[str]) -> str:
        """推断任务类型"""
        desc_lower = description.lower()
        
        # 检查工具
        if 'python' in tools or 'microsandbox' in str(tools):
            return 'code'
        elif 'browser' in str(tools) or 'navigate' in str(tools):
            return 'web'
        elif 'search' in str(tools) or 'research' in str(tools):
            return 'research'
        
        # 检查描述关键词
        if any(keyword in desc_lower for keyword in ['编程', '代码', '算法', 'python', 'code']):
            return 'code'
        elif any(keyword in desc_lower for keyword in ['搜索', '查询', '调研', '研究', 'search', 'research']):
            return 'research'
        elif any(keyword in desc_lower for keyword in ['网页', '浏览', '访问', 'web', 'browser']):
            return 'web'
        else:
            return 'reasoning'
    
    def _append_seed_tasks(self, seed_tasks: List[Dict]):
        """追加种子任务到文件"""
        try:
            os.makedirs(os.path.dirname(self.seed_tasks_file), exist_ok=True)
            
            with open(self.seed_tasks_file, 'a', encoding='utf-8') as f:
                for task in seed_tasks:
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
            
            logger.info(f"📝 已保存 {len(seed_tasks)} 个种子任务到文件")
            
        except Exception as e:
            logger.error(f"❌ 保存种子任务失败: {e}")
    
    def _count_total_seed_tasks(self) -> int:
        """统计总种子任务数"""
        try:
            if not os.path.exists(self.seed_tasks_file):
                return 0
            
            with open(self.seed_tasks_file, 'r', encoding='utf-8') as f:
                return len([line for line in f if line.strip()])
        except:
            return 0


def run_simple_generation():
    """运行简化的种子任务生成"""
    from core.utils.path_utils import get_output_dir
    
    trajectories_file = str(get_output_dir("trajectories") / "trajectories_collection.json")
    seed_tasks_file = str(get_output_dir() / "seed_tasks.jsonl")
    processed_file = str(get_output_dir() / "processed_trajectories.json")
    
    generator = SimpleSeedGenerator(trajectories_file, seed_tasks_file, processed_file)
    result = generator.process_trajectories()
    
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 简化种子任务生成器")
    print("=" * 40)
    
    result = run_simple_generation()
    
    print("\n📊 生成结果:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    print("\n💡 这个生成器绕过了LLM API调用，直接基于轨迹模式生成种子任务")