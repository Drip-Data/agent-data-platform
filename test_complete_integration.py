#!/usr/bin/env python3
"""
完整集成测试脚本
验证阶段3(持久化机制)和阶段4(实时注册机制)的实现
"""

import asyncio
import logging
import json
import websockets
import aiohttp
import time
from typing import Dict, Any

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class IntegrationTester:
    """集成测试器"""
    
    def __init__(self):
        self.toolscore_http_endpoint = "http://localhost:8090"
        self.toolscore_ws_endpoint = "ws://localhost:8091/api/v1/events/tools"
        self.session = None
        self.websocket = None
        
    async def initialize(self):
        """初始化测试环境"""
        self.session = aiohttp.ClientSession()
        logger.info("🚀 集成测试初始化完成")
        
    async def test_http_api_endpoints(self):
        """测试HTTP API端点"""
        logger.info("📡 测试HTTP API端点...")
        
        # 测试1: 获取工具列表
        try:
            async with self.session.get(f"{self.toolscore_http_endpoint}/api/v1/tools/available") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ 获取工具列表成功: {data.get('total_count', 0)} 个工具")
                else:
                    logger.error(f"❌ 获取工具列表失败: {resp.status}")
        except Exception as e:
            logger.error(f"❌ 工具列表API测试失败: {e}")
        
        # 测试2: 工具缺口分析
        try:
            gap_analysis_data = {
                "task_description": "我需要处理Excel文件和生成图片",
                "current_tools": []
            }
            
            async with self.session.post(
                f"{self.toolscore_http_endpoint}/api/v1/tools/analyze-gap",
                json=gap_analysis_data
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ 工具缺口分析成功: {data.get('has_sufficient_tools', 'unknown')}")
                else:
                    logger.error(f"❌ 工具缺口分析失败: {resp.status}")
        except Exception as e:
            logger.error(f"❌ 工具缺口分析API测试失败: {e}")
        
        # 测试3: 本地JSON搜索
        try:
            search_data = {
                "query": "filesystem",
                "max_candidates": 3
            }
            
            async with self.session.post(
                f"{self.toolscore_http_endpoint}/mcp/search",
                json=search_data
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates_count = len(data.get('candidates', []))
                    logger.info(f"✅ MCP搜索成功: 找到 {candidates_count} 个候选者")
                    
                    # 打印前3个结果
                    for i, candidate in enumerate(data.get('candidates', [])[:3]):
                        logger.info(f"  {i+1}. {candidate.get('name')} - {candidate.get('description', '')[:50]}")
                else:
                    logger.error(f"❌ MCP搜索失败: {resp.status}")
        except Exception as e:
            logger.error(f"❌ MCP搜索API测试失败: {e}")
    
    async def test_websocket_connection(self):
        """测试WebSocket实时通知"""
        logger.info("🔌 测试WebSocket实时通知...")
        
        try:
            # 连接到WebSocket
            self.websocket = await websockets.connect(self.toolscore_ws_endpoint)
            logger.info("✅ WebSocket连接成功")
            
            # 发送ping消息
            ping_message = {"type": "ping"}
            await self.websocket.send(json.dumps(ping_message))
            
            # 等待响应
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get("type") == "pong":
                logger.info("✅ WebSocket ping/pong 测试成功")
            else:
                logger.warning(f"⚠️ 收到意外响应: {response_data}")
            
            # 请求工具列表
            tools_request = {"type": "get_tools"}
            await self.websocket.send(json.dumps(tools_request))
            
            # 等待工具列表响应
            tools_response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            tools_data = json.loads(tools_response)
            
            if tools_data.get("type") == "tools_list":
                tools_count = tools_data.get("total_count", 0)
                logger.info(f"✅ WebSocket获取工具列表成功: {tools_count} 个工具")
            else:
                logger.warning(f"⚠️ 工具列表响应异常: {tools_data}")
                
        except asyncio.TimeoutError:
            logger.error("❌ WebSocket测试超时")
        except Exception as e:
            logger.error(f"❌ WebSocket测试失败: {e}")
    
    async def test_tool_capability_request(self):
        """测试工具能力请求(模拟Enhanced Runtime行为)"""
        logger.info("🛠️ 测试工具能力请求...")
        
        try:
            capability_request = {
                "task_description": "我需要生成一张图片",
                "required_capabilities": ["image_generation"],
                "auto_install": False,  # 先只分析，不实际安装
                "security_level": "high"
            }
            
            async with self.session.post(
                f"{self.toolscore_http_endpoint}/api/v1/tools/request-capability",
                json=capability_request
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    action_taken = data.get("action_taken", "unknown")
                    logger.info(f"✅ 工具能力请求成功: {action_taken}")
                    
                    if "analysis" in data:
                        analysis = data["analysis"]
                        sufficient = analysis.get("has_sufficient_tools", False)
                        logger.info(f"  📊 分析结果: 工具充分性 = {sufficient}")
                else:
                    logger.error(f"❌ 工具能力请求失败: {resp.status}")
        except Exception as e:
            logger.error(f"❌ 工具能力请求测试失败: {e}")
    
    async def test_local_json_priority_search(self):
        """测试本地JSON优先搜索机制"""
        logger.info("📁 测试本地JSON优先搜索...")
        
        test_queries = [
            "filesystem",
            "web",
            "database", 
            "email",
            "image"
        ]
        
        for query in test_queries:
            try:
                search_data = {
                    "query": query,
                    "max_candidates": 5
                }
                
                start_time = time.time()
                async with self.session.post(
                    f"{self.toolscore_http_endpoint}/mcp/search",
                    json=search_data
                ) as resp:
                    elapsed_time = int((time.time() - start_time) * 1000)
                    
                    if resp.status == 200:
                        data = await resp.json()
                        candidates_count = len(data.get('candidates', []))
                        
                        # 检查是否来自本地缓存
                        from_cache = "本地" if elapsed_time < 500 else "远程"
                        
                        logger.info(f"  🔍 '{query}': {candidates_count} 个结果 ({elapsed_time}ms, {from_cache})")
                        
                        # 如果找到结果，显示第一个
                        if candidates_count > 0:
                            first_candidate = data['candidates'][0]
                            logger.info(f"    🥇 最佳匹配: {first_candidate.get('name', 'Unknown')}")
                    else:
                        logger.error(f"  ❌ 搜索'{query}'失败: {resp.status}")
                        
            except Exception as e:
                logger.error(f"  ❌ 搜索'{query}'异常: {e}")
    
    async def test_health_and_status(self):
        """测试健康检查和状态"""
        logger.info("🏥 测试健康检查和状态...")
        
        # 健康检查
        try:
            async with self.session.get(f"{self.toolscore_http_endpoint}/health") as resp:
                if resp.status == 200:
                    logger.info("✅ 健康检查通过")
                else:
                    logger.error(f"❌ 健康检查失败: {resp.status}")
        except Exception as e:
            logger.error(f"❌ 健康检查异常: {e}")
        
        # 状态检查
        try:
            async with self.session.get(f"{self.toolscore_http_endpoint}/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data.get("status", "unknown")
                    logger.info(f"✅ 状态检查: {status}")
                else:
                    logger.error(f"❌ 状态检查失败: {resp.status}")
        except Exception as e:
            logger.error(f"❌ 状态检查异常: {e}")
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🧪 开始完整集成测试...")
        
        await self.initialize()
        
        try:
            # 基础测试
            await self.test_health_and_status()
            
            # HTTP API测试
            await self.test_http_api_endpoints()
            
            # 本地JSON搜索测试
            await self.test_local_json_priority_search()
            
            # 工具能力请求测试
            await self.test_tool_capability_request()
            
            # WebSocket测试
            await self.test_websocket_connection()
            
            logger.info("🎉 所有集成测试完成!")
            
        except Exception as e:
            logger.error(f"❌ 集成测试过程中出现异常: {e}")
        
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """清理资源"""
        if self.websocket:
            await self.websocket.close()
        if self.session:
            await self.session.close()
        logger.info("🧹 资源清理完成")

async def main():
    """主函数"""
    logger.info("🎯 启动MCP搜索工具优化完整集成测试")
    
    tester = IntegrationTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 