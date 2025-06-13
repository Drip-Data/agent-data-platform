#!/usr/bin/env python3
"""
Task API - 统一任务接入接口
提供HTTP API接收用户任务，分发到Enhanced Reasoning Runtime处理
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional, Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# API模型
class TaskRequest(BaseModel):
    task_type: str = "reasoning"  # 修复：默认使用reasoning类型，避免"general"不存在的错误
    input: str
    priority: Optional[str] = "medium"
    context: Optional[Dict[str, Any]] = None

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    timestamp: str
    result: Optional[Any] = None

app = FastAPI(
    title="Agent Data Platform - Task API",
    description="智能任务处理平台统一API入口",
    version="1.0.0"
)

# Redis连接
redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = redis.from_url(redis_url)
    logger.info(f"Connected to Redis: {redis_url}")

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        await redis_client.aclose()

@app.get("/", summary="API信息")
async def root():
    """API根端点"""
    return {
        "name": "Agent Data Platform - Task API",
        "version": "1.0.0",
        "description": "智能任务处理平台统一API入口",
        "endpoints": {
            "POST /api/v1/tasks": "提交新任务",
            "GET /api/v1/tasks/{task_id}": "查询任务状态",
            "GET /health": "健康检查",
            "GET /status": "系统状态"
        },
        "components": {
            "dispatcher": "任务分发器 (内部)",
            "enhanced_runtime": "增强推理运行时",
            "toolscore": "工具管理平台",
            "synthesis": "任务学习引擎"
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

@app.get("/status", summary="系统状态")
async def get_system_status():
    """获取系统状态"""
    try:
        # 检查各个组件状态
        redis_status = "connected" if await redis_client.ping() else "disconnected"
        
        # 检查队列长度 (Redis Stream)
        task_queue_length = await redis_client.xlen("tasks:reasoning")
        
        return {
            "status": "operational",
            "components": {
                "redis": redis_status,
                "task_queue_length": task_queue_length
            },
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {e}")

@app.post("/api/v1/tasks", summary="提交新任务", response_model=TaskResponse)
async def submit_task(request: TaskRequest):
    """提交新任务到Enhanced Reasoning Runtime"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 构建任务数据
        task_data = {
            "task_id": task_id,
            "task_type": request.task_type,
            "description": request.input,
            "priority": request.priority,
            "constraints": request.context or {},
        }
        
        # 发送到Redis Stream (enhanced reasoning runtime会监听这个队列)
        await redis_client.xadd("tasks:reasoning", {"task": json.dumps(task_data)})
        
        # 存储任务状态
        await redis_client.setex(f"task_status:{task_id}", 3600, json.dumps({
            "task_id": task_id,
            "status": "queued",
            "timestamp": datetime.now().isoformat()
        }))
        
        logger.info(f"Task {task_id} submitted successfully")
        
        return TaskResponse(
            task_id=task_id,
            status="queued",
            message="Task submitted successfully",
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to submit task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {e}")

@app.get("/api/v1/tasks/{task_id}", summary="查询任务状态", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """查询任务状态"""
    try:
        # 从Redis获取任务状态
        status_data = await redis_client.get(f"task_status:{task_id}")
        
        if not status_data:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        status_info = json.loads(status_data)
        
        # 检查是否有结果
        result_data = await redis_client.get(f"task_result:{task_id}")
        result = json.loads(result_data) if result_data else None
        
        return TaskResponse(
            task_id=task_id,
            status=status_info.get("status", "unknown"),
            message=status_info.get("message", ""),
            timestamp=status_info.get("timestamp", ""),
            result=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {e}")

@app.post("/api/v1/tools/list", summary="获取可用工具列表")
async def list_available_tools():
    """获取ToolScore中可用的工具列表"""
    try:
        # 发送工具列表请求到ToolScore
        await redis_client.lpush("toolscore:commands", json.dumps({
            "command": "list_tools",
        }))
        
        return {
            "message": "Tool list request sent to ToolScore",
        }
        
    except Exception as e:
        logger.error(f"Failed to request tool list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to request tool list: {e}")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"Starting Task API on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    ) 