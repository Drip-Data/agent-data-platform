#!/usr/bin/env python3
"""
Synthesis Service - 基于SynthesisEngine的任务合成服务
使用真正的LLM驱动的TaskCraft算法进行智能任务生成
"""

import logging
import os
import threading
import time
import asyncio
from typing import Dict, Optional
from pathlib import Path

# 导入新的synthesis核心组件
from core.synthesiscore.trajectory_monitor import SimpleTrajectoryMonitor
from core.synthesiscore.synthesis_engine import SynthesisEngine
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient

logger = logging.getLogger(__name__)

# 全局变量
synthesis_engine = None
trajectory_monitor = None
synthesis_thread = None
monitor_task = None
running = False

from core.unified_tool_manager import UnifiedToolManager
from core.utils.path_utils import get_synthesis_task_dir, get_trajectories_dir, get_output_dir

def initialize(config: Optional[Dict] = None, tool_manager: Optional[UnifiedToolManager] = None):
    """初始化合成服务 - 使用SynthesisEngine"""
    global synthesis_engine, trajectory_monitor
    
    if config is None:
        config = {}
    
    logger.info("🚀 初始化基于SynthesisEngine的合成服务...")
    
    # 检查必要的依赖
    if not tool_manager:
        logger.warning("⚠️ 未提供UnifiedToolManager，将使用基础配置")
    
    try:
        # 使用统一的路径管理工具获取目录
        trajectories_dir = get_trajectories_dir()
        seed_tasks_file = str(get_output_dir() / 'seed_tasks.jsonl')
        
        # 目录已由path_utils自动创建，无需手动创建
        
        # 初始化LLM客户端
        llm_client = _initialize_llm_client(config, tool_manager)
        if not llm_client:
            logger.error("❌ LLM客户端初始化失败")
            return False
        
        # 创建SynthesisEngine，使用专门的SynthesisTask目录
        synthesis_engine = SynthesisEngine(
            llm_client=llm_client,
            mcp_client=getattr(tool_manager, 'mcp_client', None) if tool_manager else None,
            storage_dir=get_synthesis_task_dir()
        )
        
        # 创建轨迹监控器
        trajectory_monitor = SimpleTrajectoryMonitor(
            trajectories_dir=trajectories_dir,
            seed_tasks_file=seed_tasks_file
        )
        
        logger.info("✅ SynthesisEngine和轨迹监控器初始化成功")
        logger.info(f"📂 监控目录: {trajectories_dir}")
        logger.info(f"📄 输出文件: {seed_tasks_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 合成服务初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def _initialize_llm_client(config: Dict, tool_manager: Optional[UnifiedToolManager] = None) -> Optional[LLMClient]:
    """初始化LLM客户端"""
    try:
        import yaml
        
        # 优先使用传入的配置
        if 'llm_config' in config:
            llm_config = config['llm_config']
        else:
            # 尝试加载配置文件
            config_path = os.path.join(os.path.dirname(__file__), "..", "config", "llm_config.yaml")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                    
                    # 使用统一的LLM配置格式
                    default_provider = config_data.get('default_provider', 'gemini')
                    provider_config = config_data.get('llm_providers', {}).get(default_provider, {})
                    
                    llm_config = {
                        'provider': default_provider,
                        'model': provider_config.get('model', 'gemini-2.5-flash-lite-preview-06-17'),
                        'api_key': provider_config.get('api_key', ''),
                        'temperature': provider_config.get('temperature', 0.2),
                        'max_tokens': provider_config.get('max_tokens', 8192)
                    }
                    
                    if default_provider == 'gemini' and provider_config.get('api_base'):
                        llm_config['api_base'] = provider_config['api_base']
            else:
                # 使用默认配置
                llm_config = {
                    'provider': 'gemini',
                    'model': 'gemini-2.5-flash-lite-preview-06-17',
                    'temperature': 0.2
                }
        
        # 如果没有tool_manager，创建一个基本的实例
        if tool_manager is None:
            tool_manager = UnifiedToolManager()
        
        client = LLMClient(config=llm_config, tool_manager=tool_manager)
        logger.info(f"✅ LLM客户端初始化成功: {llm_config.get('provider', 'unknown')}")
        return client
        
    except Exception as e:
        logger.error(f"❌ LLM客户端初始化失败: {e}")
        return None

async def start():
    """启动合成服务"""
    global running, monitor_task
    
    if not synthesis_engine or not trajectory_monitor:
        logger.error("❌ 服务未初始化，无法启动")
        return False
    
    try:
        running = True
        
        # 初始化轨迹监控器
        await trajectory_monitor.initialize()
        
        # 启动文件监控
        await trajectory_monitor.start_monitoring()
        
        logger.info("🎉 合成服务启动成功")
        logger.info("="*60)
        logger.info("✅ SynthesisCore (TaskCraft) 组件已激活并正常运行！")
        logger.info("🧠 关系驱动反向推理算法已就绪")
        logger.info("📊 38个增强Prompt模板已加载")
        logger.info("👁️ 轨迹自动监控已启动")
        logger.info("📂 监控目录: output/trajectories/")
        logger.info("📄 输出目录: output/SynthesisTask/")
        logger.info("="*60)
        return True
        
    except Exception as e:
        logger.error("="*60)
        logger.error("❌ SynthesisCore (TaskCraft) 组件启动失败！")
        logger.error(f"错误详情: {e}")
        logger.error("请检查以下可能的问题:")
        logger.error("1. Redis服务是否正常运行")
        logger.error("2. 轨迹目录是否可写: output/trajectories/")
        logger.error("3. 输出目录是否可写: output/SynthesisTask/")
        logger.error("="*60)
        import traceback
        traceback.print_exc()
        running = False
        return False

async def stop():
    """停止合成服务"""
    global running, monitor_task
    
    try:
        running = False
        
        # 停止轨迹监控
        if trajectory_monitor:
            await trajectory_monitor.stop_monitoring()
        
        # 取消异步任务
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 合成服务已停止")
        return True
        
    except Exception as e:
        logger.error(f"❌ 停止合成服务失败: {e}")
        return False

def health_check() -> Dict:
    """健康检查"""
    try:
        status = {
            "service": "synthesis_service",
            "status": "healthy" if running else "stopped",
            "components": {
                "synthesis_engine": synthesis_engine is not None,
                "trajectory_monitor": trajectory_monitor is not None,
                "llm_client": synthesis_engine.llm_client is not None if synthesis_engine else False
            },
            "details": {
                "running": running,
                "algorithm": "TaskCraft_with_LLM",
                "capabilities": [
                    "atomic_task_generation",
                    "depth_extension", 
                    "width_extension",
                    "intelligent_validation"
                ]
            }
        }
        
        # 如果有轨迹监控器，添加统计信息
        if trajectory_monitor:
            try:
                # 使用同步方式获取统计（如果可能）
                stats = {
                    "processed_trajectories": len(trajectory_monitor.processed_trajectories),
                    "trajectories_dir": trajectory_monitor.trajectories_dir,
                    "seed_tasks_file": trajectory_monitor.seed_tasks_file
                }
                status["statistics"] = stats
            except Exception as e:
                logger.debug(f"获取统计信息失败: {e}")
        
        return status
        
    except Exception as e:
        logger.error(f"❌ 健康检查失败: {e}")
        return {
            "service": "synthesis_service",
            "status": "error",
            "error": str(e)
        }

async def get_statistics() -> Dict:
    """获取详细统计信息"""
    try:
        if not trajectory_monitor:
            return {"error": "服务未初始化"}
        
        # 获取轨迹监控器统计
        monitor_stats = await trajectory_monitor.get_statistics()
        
        # 获取SynthesisEngine统计（如果有）
        engine_stats = {}
        if synthesis_engine:
            try:
                engine_stats = await synthesis_engine.get_storage_statistics()
            except Exception as e:
                logger.debug(f"获取引擎统计失败: {e}")
        
        return {
            "service": "synthesis_service",
            "monitor_statistics": monitor_stats,
            "engine_statistics": engine_stats,
            "algorithm": "TaskCraft_with_LLM"
        }
        
    except Exception as e:
        logger.error(f"❌ 获取统计信息失败: {e}")
        return {"error": str(e)}

async def process_trajectories_manually(trajectories_data: list) -> Dict:
    """手动处理轨迹数据（用于API调用）"""
    try:
        if not synthesis_engine:
            return {"error": "SynthesisEngine未初始化"}
        
        logger.info(f"🔄 手动处理 {len(trajectories_data)} 个轨迹")
        
        # 使用SynthesisEngine处理轨迹
        result = await synthesis_engine.synthesize_from_trajectories(
            trajectories_data=trajectories_data,
            generate_depth_extensions=True,
            generate_width_extensions=True,
            max_atomic_tasks=20
        )
        
        if result:
            return {
                "success": True,
                "session_id": result.session_id,
                "total_tasks_generated": result.total_tasks_generated,
                "valid_tasks_count": result.valid_tasks_count,
                "atomic_tasks": len(result.atomic_tasks),
                "depth_extended_tasks": len(result.depth_extended_tasks),
                "width_extended_tasks": len(result.width_extended_tasks),
                "tool_required_count": result.tool_required_count,
                "reasoning_only_count": result.reasoning_only_count
            }
        else:
            return {"error": "任务合成失败"}
            
    except Exception as e:
        logger.error(f"❌ 手动处理轨迹失败: {e}")
        return {"error": str(e)}

# 向后兼容的别名
async def get_synthesis_statistics():
    """向后兼容的统计信息获取"""
    return await get_statistics()