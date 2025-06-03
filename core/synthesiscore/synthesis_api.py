#!/usr/bin/env python3
"""
Synthesis HTTP API
简单的HTTP接口，用于触发synthesis操作
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Optional, List, Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os

logger = logging.getLogger(__name__)

# 配置
DB_PATH = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")

# API模型
class SynthesisRequest(BaseModel):
    action: str
    target: Optional[str] = None
    count: Optional[int] = 3

class CommandResponse(BaseModel):
    success: bool
    message: str
    timestamp: str

class DatabaseView(BaseModel):
    essences: List[Dict]
    generated_tasks: List[Dict]
    statistics: Dict

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
            "GET /health": "健康检查",
            "POST /init-db": "初始化数据库",
            "GET /view": "查看数据库内容",
            "GET /db/tasks": "获取数据库中的所有任务",
            "GET /db/export": "导出任务数据",
            "POST /db/clear": "清空数据库",
            "GET /db/stats": "获取数据库统计信息"
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

@app.post("/init-db", summary="初始化数据库")
async def init_database():
    """初始化synthesis数据库"""
    try:
        from .init_synthesis_db import init_synthesis_database
        init_synthesis_database()
        return {
            "success": True,
            "message": "Database initialized successfully",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize database: {e}")

@app.get("/view", summary="查看数据库内容")
async def view_database():
    """查看数据库内容"""
    try:
        import os
        db_path = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")
        
        if not os.path.exists(db_path):
            raise HTTPException(status_code=404, detail="Database file not found")
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取任务本质
        cursor.execute("SELECT * FROM task_essences")
        essences = [dict(zip([col[0] for col in cursor.description], row)) 
                   for row in cursor.fetchall()]
        
        # 获取生成的任务
        cursor.execute("SELECT * FROM generated_tasks")
        generated_tasks = [dict(zip([col[0] for col in cursor.description], row)) 
                         for row in cursor.fetchall()]
        
        # 获取统计信息
        cursor.execute("SELECT COUNT(*) as total_essences FROM task_essences")
        total_essences = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) as total_tasks FROM generated_tasks")
        total_tasks = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT task_type, COUNT(*) as count 
            FROM task_essences 
            GROUP BY task_type
        """)
        essence_distribution = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            "success": True,
            "data": {
                "essences": essences,
                "generated_tasks": generated_tasks,
                "statistics": {
                    "total_essences": total_essences,
                    "total_tasks": total_tasks,
                    "essence_distribution": essence_distribution
                }
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to view database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to view database: {e}")

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

@app.get("/db/tasks", summary="获取数据库中的所有任务")
async def get_all_tasks():
    """获取数据库中的所有任务"""
    try:
        db_path = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取任务本质
        cursor.execute('SELECT * FROM task_essences')
        essences = cursor.fetchall()
        
        # 获取生成的任务
        cursor.execute('SELECT * FROM generated_tasks')
        tasks = cursor.fetchall()
        
        conn.close()
        
        # 格式化结果
        formatted_essences = []
        for essence in essences:
            formatted_essences.append({
                "id": essence[0],
                "task_type": essence[1],
                "tool_category": essence[2],
                "description": essence[3],
                "created_at": essence[4]
            })
        
        formatted_tasks = []
        for task in tasks:
            try:
                task_content = json.loads(task[2])
            except json.JSONDecodeError:
                task_content = {"error": "Failed to parse task content"}
            
            formatted_tasks.append({
                "task_id": task[0],
                "essence_id": task[1],
                "task_content": task_content,
                "created_at": task[3]
            })
        
        return {
            "success": True,
            "summary": {
                "total_essences": len(essences),
                "total_tasks": len(tasks)
            },
            "task_essences": formatted_essences,
            "generated_tasks": formatted_tasks
        }
        
    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/db/export", summary="导出任务数据")
async def export_tasks(format: str = "jsonl"):
    """导出任务数据"""
    try:
        db_path = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM generated_tasks')
        tasks = cursor.fetchall()
        conn.close()
        
        if format == "jsonl":
            # 导出为TaskSpec格式的JSONL
            export_data = []
            for task in tasks:
                try:
                    task_content = json.loads(task[2])
                    export_data.append(task_content)
                except json.JSONDecodeError:
                    continue
            
            return {
                "success": True,
                "format": "jsonl",
                "count": len(export_data),
                "data": export_data
            }
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")
            
    except Exception as e:
        logger.error(f"Failed to export tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")

@app.post("/db/clear", summary="清空数据库")
async def clear_database():
    """清空数据库"""
    try:
        db_path = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM generated_tasks')
        cursor.execute('DELETE FROM task_essences')
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Database cleared successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to clear database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/db/stats", summary="获取数据库统计信息")
async def get_db_stats():
    """获取数据库统计"""
    try:
        db_path = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")
        
        with sqlite3.connect(db_path) as conn:
            # 统计task_essences表
            cursor = conn.execute("SELECT COUNT(*) FROM task_essences")
            essence_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT task_type, COUNT(*) FROM task_essences GROUP BY task_type")
            essence_by_type = dict(cursor.fetchall())
            
            cursor = conn.execute("SELECT domain, COUNT(*) FROM task_essences GROUP BY domain")
            essence_by_domain = dict(cursor.fetchall())
            
            # 统计generated_tasks表
            cursor = conn.execute("SELECT COUNT(*) FROM generated_tasks")
            generated_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM generated_tasks WHERE executed = 1")
            executed_count = cursor.fetchone()[0]
            
            return {
                "essences": {
                    "total": essence_count,
                    "by_type": essence_by_type,
                    "by_domain": essence_by_domain
                },
                "generated_tasks": {
                    "total": generated_count,
                    "executed": executed_count,
                    "pending": generated_count - executed_count
                }
            }
            
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("API_PORT", 8080))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"Starting Synthesis API on {host}:{port}")
    uvicorn.run(app, host=host, port=port) 