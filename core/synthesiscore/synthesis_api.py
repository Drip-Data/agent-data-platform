#!/usr/bin/env python3
"""
Synthesis HTTP API
简单的HTTP接口，用于触发synthesis操作
"""

import asyncio
import json
import logging
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
    title="Synthesis API",
    description="轨迹合成服务控制API",
    version="1.0.0"
)

# Redis连接
redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    import os
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
        "name": "Synthesis API",
        "version": "1.0.0",
        "description": "轨迹合成服务控制API",
        "endpoints": {
            "GET /status": "获取synthesis服务状态",
            "POST /trigger/full": "触发完整轨迹合成",
            "POST /trigger/new": "只处理新轨迹",
            "POST /trigger/specific": "处理指定轨迹文件",
            "POST /generate": "手动生成任务",
            "GET /health": "健康检查"
        }
    }

@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    try:
        await redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis connection failed: {e}")

@app.get("/status", summary="获取synthesis服务状态")
async def get_synthesis_status():
    """获取synthesis服务状态"""
    try:
        # 发送状态查询命令
        await send_synthesis_command("status")
        
        # 等待状态响应
        await asyncio.sleep(1)
        
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

@app.post("/generate", summary="手动生成任务")
async def generate_tasks(request: Dict):
    """手动生成指定数量的任务"""
    count = request.get("count", 3)
    
    try:
        count = int(count)
        if count <= 0 or count > 20:
            raise ValueError("Count must be between 1 and 20")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid count value: {e}")
    
    result = await send_synthesis_command("generate_tasks", count=str(count))
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

@app.post("/command", summary="发送自定义命令")
async def send_custom_command(request: SynthesisRequest):
    """发送自定义命令到synthesis服务"""
    command_kwargs = {}
    
    if request.target:
        command_kwargs["target"] = request.target
    if request.count:
        command_kwargs["count"] = str(request.count)
    
    result = await send_synthesis_command(request.action, **command_kwargs)
    if result["success"]:
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result["message"])

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("API_PORT", 8080))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"Starting Synthesis API on {host}:{port}")
    uvicorn.run(app, host=host, port=port) 