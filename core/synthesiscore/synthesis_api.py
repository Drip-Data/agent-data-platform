#!/usr/bin/env python3
"""
Synthesis HTTP API - 简化版
用于控制JSON文件存储的synthesis服务
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    redis_client = redis.from_url(redis_url)
    logger.info(f"Connected to Redis: {redis_url}")

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.aclose()

async def send_synthesis_command(command: str, **kwargs) -> Dict:
    """发送命令到synthesis服务"""
    try:
        command_data = {"command": command}
        command_data.update(kwargs)
        
        await redis_client.xadd("synthesis:commands", command_data)
        
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
            "POST /monitoring/stop": "停止轨迹监控"
        },
        "file_paths": {
            "task_essences": "/app/output/task_essences.json",
            "seed_tasks": "/app/output/seed_tasks.jsonl",
            "trajectories_collection": "/app/output/trajectories/trajectories_collection.json"
        }
    }

@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    try:
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

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8081"))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"Starting Synthesis API on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    ) 