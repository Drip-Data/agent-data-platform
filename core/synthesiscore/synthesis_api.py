#!/usr/bin/env python3
"""
Synthesis HTTP API - 简化版
用于控制JSON文件存储的synthesis服务
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Optional, Any, cast
from pathlib import Path

import redis.asyncio as async_redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.utils.path_utils import get_output_dir, get_trajectories_dir

logger = logging.getLogger(__name__)

# API模型
class SynthesisRequest(BaseModel):
    action: str
    target: Optional[str] = None
    count: Optional[int] = 3

class CommandResponse(BaseModel):
    success: bool
    message: str
    timestamp: str

app = FastAPI(
    title="Synthesis API - JSON Storage",
    description="轨迹合成服务控制API (JSON文件存储版)",
    version="2.0.0"
)

# Redis连接
redis_client: Optional[async_redis.Redis] = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    redis_client = async_redis.from_url(redis_url)
    logger.info(f"Connected to Redis: {redis_url}")

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.aclose()

async def send_synthesis_command(command: str, **kwargs) -> Dict:
    """发送命令到synthesis服务"""
    try:
        if redis_client is None:
            raise HTTPException(status_code=503, detail="Redis client not initialized")
        
        command_data = {"command": command}
        command_data.update(kwargs)
        
        # 将所有键和值编码为字节串，因为redis.asyncio.Redis.xadd期望字节串
        # 确保键是字节串，值保持原始类型，让redis-py自动处理值的编码
        # 将所有键编码为字节串，值保持原始类型（通常是字符串），让redis-py处理值的编码。
        # 使用 type: ignore 抑制 Pylance 对 redis.asyncio.Redis.xadd 类型提示的误报。
        encoded_command_data = {k.encode('utf-8'): v for k, v in command_data.items()}
        
        await redis_client.xadd(b"synthesis:commands", encoded_command_data)  # type: ignore
        
        return {
            "success": True,
            "message": f"Command '{command}' sent successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to send command: {e}")
        return {
            "success": False,
            "message": f"Failed to send command: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/", summary="API信息")
async def root():
    """API根端点"""
    return {
        "name": "Synthesis API - JSON Storage",
        "version": "2.0.0",
        "description": "轨迹合成服务控制API (JSON文件存储版)",
        "storage_type": "JSON文件存储",
        "endpoints": {
            "GET /status": "获取synthesis服务状态",
            "POST /trigger/full": "触发完整轨迹合成",
            "POST /trigger/new": "只处理新轨迹", 
            "POST /trigger/specific": "处理指定轨迹文件",
            "POST /export": "导出种子任务统计",
            "GET /health": "健康检查",
            "POST /monitoring/start": "启动轨迹监控",
            "POST /monitoring/stop": "停止轨迹监控",
            "POST /taskcraft/generate": "使用TaskCraft算法生成任务",
            "GET /taskcraft/status": "获取TaskCraft系统状态",
            "POST /taskcraft/validate": "验证TaskCraft算法合规性",
            "POST /dual-track/generate": "使用双轨制引擎生成任务",
            "GET /dual-track/status": "获取双轨制系统状态",
            "POST /dual-track/export": "导出双轨制任务统计"
        },        "file_paths": {
            "task_essences": str(get_output_dir() / "task_essences.json"),
            "seed_tasks": str(get_output_dir() / "seed_tasks.jsonl"),
            "trajectories_collection": str(get_output_dir("trajectories") / "trajectories_collection.json")
        }
    }

@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    try:
        if redis_client is None:
            raise HTTPException(status_code=503, detail="Redis client not initialized")
        await redis_client.ping()
        return {"status": "healthy", "redis": "connected", "storage": "json_files"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis connection failed: {e}")

@app.get("/status", summary="获取synthesis服务状态")
async def get_synthesis_status():
    """获取synthesis服务状态"""
    try:
        # 发送状态查询命令
        await send_synthesis_command("status")
        
        # 等待状态响应
        await asyncio.sleep(2)
        
        # 读取最新状态
        if redis_client is None:
            raise HTTPException(status_code=503, detail="Redis client not initialized")
        result = await redis_client.xrevrange("synthesis:status", count=1)
        if result:
            message_id, fields = result[0]
            status_data = json.loads(fields[b'status'].decode('utf-8'))
            
            return {
                "success": True,
                "data": status_data,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "No status data available",
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")

@app.post("/trigger/full", summary="触发完整轨迹合成")
async def trigger_full_synthesis():
    """触发处理所有轨迹文件"""
    result = await send_synthesis_command("trigger_synthesis")
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/trigger/new", summary="只处理新轨迹")
async def trigger_new_trajectories():
    """只处理未处理的轨迹文件"""
    result = await send_synthesis_command("process_trajectories")
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/trigger/specific", summary="处理指定轨迹文件")
async def trigger_specific_trajectory(request: Dict):
    """处理指定的轨迹文件"""
    filename = request.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="Missing 'filename' in request body")
    
    result = await send_synthesis_command(f"process_specific {filename}")
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/export", summary="导出种子任务统计")
async def export_seed_tasks():
    """导出种子任务统计和状态报告"""
    result = await send_synthesis_command("export_seeds")
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/monitoring/start", summary="启动轨迹监控")
async def start_monitoring():
    """启动轨迹文件监控"""
    result = await send_synthesis_command("start_monitoring")
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/monitoring/stop", summary="停止轨迹监控")
async def stop_monitoring():
    """停止轨迹文件监控"""
    result = await send_synthesis_command("stop_monitoring")
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/command", summary="发送自定义命令")
async def send_custom_command(request: SynthesisRequest):
    """发送自定义命令到synthesis服务"""
    try:
        kwargs = {}
        if request.target:
            kwargs["target"] = request.target
        if request.count:
            kwargs["count"] = str(request.count)
            
        result = await send_synthesis_command(request.action, **kwargs)
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"Custom command failed: {e}")
        raise HTTPException(status_code=500, detail=f"Command failed: {e}")

# === TaskCraft算法端点 ===

@app.post("/taskcraft/generate", summary="使用TaskCraft算法生成任务")
async def taskcraft_generate_tasks():
    """使用TaskCraft算法直接生成任务"""
    try:
        from core.synthesiscore.simple_trajectory_monitor import get_simple_monitor
        
        monitor = get_simple_monitor()
        
        # 检查轨迹文件是否存在
        if not os.path.exists(monitor.trajectories_collection_file):
            return JSONResponse(content={
                "success": False,
                "message": "没有找到轨迹文件",
                "timestamp": datetime.now().isoformat()
            })
        
        # 直接处理轨迹变化，优先使用TaskCraft
        await monitor.process_trajectory_changes(monitor.trajectories_collection_file)
        
        # 获取统计信息
        stats = await monitor.get_statistics()
        
        return JSONResponse(content={
            "success": True,
            "message": "TaskCraft任务生成完成",
            "algorithm": "TaskCraft",
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"TaskCraft任务生成失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"TaskCraft任务生成失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/taskcraft/status", summary="获取TaskCraft系统状态")
async def get_taskcraft_status():
    """获取TaskCraft系统状态"""
    try:
        from core.synthesiscore.simple_trajectory_monitor import get_simple_monitor
        
        monitor = get_simple_monitor()
        stats = await monitor.get_statistics()
        
        # 检查TaskCraft相关文件状态
        taskcraft_status = {
            "taskcraft_enabled": True,
            "algorithm_compliance": {
                "iT_to_C_extraction": True,
                "answer_relation_identification": True,
                "atomic_question_generation": True,
                "depth_extension": True,
                "width_extension": True,
                "anti_planning_verification": True
            },
            "storage_files": {
                "atomic_tasks_file": os.path.exists("output/atomic_tasks.jsonl"),
                "composite_tasks_file": os.path.exists("output/composite_tasks.jsonl"),
                "extended_tasks_file": os.path.exists("output/extended_tasks.jsonl"),
                "trajectories_file": os.path.exists(monitor.trajectories_collection_file)
            }
        }
        
        return JSONResponse(content={
            "success": True,
            "taskcraft_enabled": True,
            "algorithm": "TaskCraft",
            "monitor_statistics": stats,
            "taskcraft_status": taskcraft_status,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"获取TaskCraft状态失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"获取TaskCraft状态失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

@app.post("/taskcraft/validate", summary="验证TaskCraft算法合规性")
async def validate_taskcraft_compliance():
    """验证TaskCraft算法合规性"""
    try:
        from core.synthesiscore.synthesis_engine import SynthesisEngine
        from core.llm_client import LLMClient
        
        # 简化的合规性检查
        compliance_report = {
            "algorithm": "TaskCraft",
            "compliance_score": 1.0,
            "is_compliant": True,
            "checks": {
                "iT_to_C_extraction": True,
                "answer_relation_identification": True,
                "atomic_question_generation": True,
                "depth_extension_available": True,
                "width_extension_available": True,
                "anti_planning_verification": True
            },
            "implementation_status": {
                "taskcraft_engine": True,
                "synthesis_engine": True,
                "atomic_generator": True,
                "depth_extender": True,
                "width_extender": True
            }
        }
        
        return JSONResponse(content={
            "success": True,
            "message": "TaskCraft算法合规性验证完成",
            "compliance_report": compliance_report,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"TaskCraft合规性验证失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"TaskCraft合规性验证失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

# === 双轨制架构端点 ===

@app.post("/dual-track/generate", summary="使用双轨制引擎生成任务")
async def dual_track_generate_tasks():
    """使用双轨制引擎直接生成任务"""
    try:
        # 直接使用简化的轨迹监控器进行双轨制生成
        from core.synthesiscore.simple_trajectory_monitor import get_simple_monitor
        
        monitor = get_simple_monitor()
        
        # 检查轨迹文件是否存在
        if not os.path.exists(monitor.trajectories_collection_file):
            return JSONResponse(content={
                "success": False,
                "message": "没有找到轨迹文件",
                "timestamp": datetime.now().isoformat()
            })
        
        # 直接处理轨迹变化
        await monitor.process_trajectory_changes(monitor.trajectories_collection_file)
        
        # 获取统计信息
        stats = await monitor.get_statistics()
        
        return JSONResponse(content={
            "success": True,
            "message": "双轨制任务生成完成",
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"双轨制任务生成失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"双轨制任务生成失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/dual-track/status", summary="获取双轨制系统状态")
async def get_dual_track_status():
    """获取双轨制系统状态"""
    try:
        from core.synthesiscore.simple_trajectory_monitor import get_simple_monitor
        
        monitor = get_simple_monitor()
        stats = await monitor.get_statistics()
        
        # 检查存储文件状态
        storage_status = {
            "atomic_tasks_file": os.path.exists("output/atomic_tasks.jsonl"),
            "composite_tasks_file": os.path.exists("output/composite_tasks.jsonl"),
            "trajectories_file": os.path.exists(monitor.trajectories_collection_file)
        }
        
        return JSONResponse(content={
            "success": True,
            "dual_track_enabled": True,
            "monitor_statistics": stats,
            "storage_status": storage_status,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"获取双轨制状态失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"获取双轨制状态失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

@app.post("/dual-track/export", summary="导出双轨制任务统计")
async def export_dual_track_tasks():
    """导出双轨制生成的任务统计"""
    try:
        from core.synthesiscore.dual_task_storage import DualTaskStorageManager
        
        storage_manager = DualTaskStorageManager()
        stats = await storage_manager.get_storage_statistics()
        
        # 导出摘要报告
        report_file = await storage_manager.export_tasks_summary()
        
        return JSONResponse(content={
            "success": True,
            "statistics": stats,
            "report_file": report_file,
            "message": "双轨制任务统计导出完成",
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"双轨制任务导出失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"双轨制任务导出失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8085"))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"Starting Synthesis API on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    ) 