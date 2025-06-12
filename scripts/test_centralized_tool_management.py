#!/usr/bin/env python3
"""
集中式工具管理系统测试脚本
验证工具同步、注册和执行协调功能
"""

import asyncio
import json
import logging
import aiohttp
import redis.asyncio as redis
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CentralizedToolManagementTester:
    """集中式工具管理系统测试器"""
    
    def __init__(self):
        self.toolscore_endpoint = "http://localhost:8090"
        self.redis_url = "redis://localhost:6379"
        self.redis_client = None
        
    async def initialize(self):
        """初始化测试器"""
        self.redis_client = redis.from_url(self.redis_url)
        await self.redis_client.ping()
        logger.info("✅ Redis连接成功")
    
    async def cleanup(self):
        """清理资源"""
        if self.redis_client:
            await self.redis_client.close()
    
    async def test_toolscore_health(self):
        """测试ToolScore健康状态"""
        logger.info("🔍 测试ToolScore健康状态...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.toolscore_endpoint}/health") as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✅ ToolScore健康状态: {result}")
                        return True
                    else:
                        logger.error(f"❌ ToolScore健康检查失败: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ ToolScore连接失败: {e}")
            return False
    
    async def test_tool_registration(self):
        """测试工具注册功能"""
        logger.info("🔧 测试工具注册功能...")
        
        # 创建测试工具规格
        test_tool_spec = {
            "tool_id": "test-centralized-tool",
            "name": "集中式测试工具",
            "description": "用于验证集中式工具管理系统的测试工具",
            "tool_type": "FUNCTION",
            "capabilities": [
                {
                    "name": "test_capability",
                    "description": "测试能力",
                    "parameters": {
                        "message": {
                            "type": "string",
                            "description": "测试消息",
                            "required": True
                        }
                    },
                    "examples": [{
                        "message": "Hello World"
                    }]
                }
            ],
            "enabled": True,
            "tags": ["test", "centralized"],
            "source_service": "test_script"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.toolscore_endpoint}/admin/tools/register",
                    json={"tool_spec": test_tool_spec},
                    headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    
                    if result.get("success"):
                        logger.info(f"✅ 工具注册成功: {result}")
                        return True
                    else:
                        logger.error(f"❌ 工具注册失败: {result}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 工具注册异常: {e}")
            return False
    
    async def test_tool_listing(self):
        """测试工具列表功能"""
        logger.info("📋 测试工具列表功能...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.toolscore_endpoint}/tools") as response:
                    if response.status == 200:
                        result = await response.json()
                        tools = result.get("tools", [])
                        logger.info(f"✅ 获取到 {len(tools)} 个工具:")
                        
                        for tool in tools:
                            logger.info(f"  - {tool.get('tool_id')}: {tool.get('name')}")
                        
                        return True
                    else:
                        logger.error(f"❌ 获取工具列表失败: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 获取工具列表异常: {e}")
            return False
    
    async def test_redis_pubsub(self):
        """测试Redis Pub/Sub事件机制"""
        logger.info("📡 测试Redis Pub/Sub事件机制...")
        
        try:
            # 订阅工具事件
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe('tool_events')
            
            # 发布测试事件
            test_event = {
                "event_type": "test",
                "tool_id": "test-event-tool",
                "tool_spec": {"name": "测试事件工具"},
                "source_service": "test_script",
                "timestamp": datetime.now().timestamp()
            }
            
            await self.redis_client.publish('tool_events', json.dumps(test_event))
            logger.info("📢 已发布测试事件")
            
            # 监听事件
            message = await asyncio.wait_for(
                pubsub.get_message(ignore_subscribe_messages=True),
                timeout=5.0
            )
            
            if message and message['type'] == 'message':
                event_data = json.loads(message['data'])
                logger.info(f"✅ 收到事件: {event_data}")
                await pubsub.close()
                return True
            else:
                logger.error("❌ 未收到预期的事件")
                await pubsub.close()
                return False
                
        except asyncio.TimeoutError:
            logger.error("❌ 事件监听超时")
            return False
        except Exception as e:
            logger.error(f"❌ Redis Pub/Sub测试异常: {e}")
            return False
    
    async def test_tool_lifecycle(self):
        """测试工具生命周期管理"""
        logger.info("🔄 测试工具生命周期管理...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.toolscore_endpoint}/admin/tools/lifecycle") as response:
                    if response.status == 200:
                        result = await response.json()
                        tools = result.get("tools", [])
                        logger.info(f"✅ 获取到 {len(tools)} 个工具的生命周期信息")
                        
                        for tool in tools[:3]:  # 只显示前3个
                            logger.info(f"  - {tool.get('tool_id')}: 启用={tool.get('enabled')}, 使用次数={tool.get('usage_count')}")
                        
                        return True
                    else:
                        logger.error(f"❌ 获取工具生命周期失败: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 工具生命周期测试异常: {e}")
            return False
    
    async def test_tool_unregistration(self):
        """测试工具注销功能"""
        logger.info("🗑️ 测试工具注销功能...")
        
        tool_id = "test-centralized-tool"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(f"{self.toolscore_endpoint}/admin/tools/{tool_id}") as response:
                    result = await response.json()
                    
                    if result.get("success"):
                        logger.info(f"✅ 工具注销成功: {result}")
                        return True
                    else:
                        logger.error(f"❌ 工具注销失败: {result}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 工具注销异常: {e}")
            return False
    
    async def test_enhanced_runtime_integration(self):
        """测试Enhanced Runtime集成"""
        logger.info("🧠 测试Enhanced Runtime集成...")
        
        # 检查心跳信息
        try:
            heartbeat_keys = await self.redis_client.keys("heartbeat:*")
            logger.info(f"🔍 找到 {len(heartbeat_keys)} 个服务心跳")
            
            for key in heartbeat_keys:
                heartbeat_data = await self.redis_client.get(key)
                if heartbeat_data:
                    data = json.loads(heartbeat_data)
                    logger.info(f"  💓 {data.get('service_id')}: 状态={data.get('status')}, 工具数={data.get('cached_tools_count')}")
            
            return len(heartbeat_keys) > 0
            
        except Exception as e:
            logger.error(f"❌ Enhanced Runtime集成测试异常: {e}")
            return False
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始集中式工具管理系统测试")
        
        tests = [
            ("ToolScore健康检查", self.test_toolscore_health),
            ("工具注册", self.test_tool_registration),
            ("工具列表", self.test_tool_listing),
            ("Redis Pub/Sub", self.test_redis_pubsub),
            ("工具生命周期", self.test_tool_lifecycle),
            ("Enhanced Runtime集成", self.test_enhanced_runtime_integration),
            ("工具注销", self.test_tool_unregistration),
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                result = await test_func()
                results.append((test_name, result))
                
                if result:
                    logger.info(f"✅ {test_name} - 通过")
                else:
                    logger.error(f"❌ {test_name} - 失败")
                    
                # 测试间隔
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ {test_name} - 异常: {e}")
                results.append((test_name, False))
        
        # 汇总结果
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        logger.info(f"\n🎯 测试汇总: {passed}/{total} 通过")
        
        for test_name, result in results:
            status = "✅" if result else "❌"
            logger.info(f"  {status} {test_name}")
        
        if passed == total:
            logger.info("🎉 所有测试通过！集中式工具管理系统运行正常")
        else:
            logger.warning(f"⚠️ {total - passed} 个测试失败，请检查系统配置")
        
        return passed == total


async def main():
    """主函数"""
    tester = CentralizedToolManagementTester()
    
    try:
        await tester.initialize()
        success = await tester.run_all_tests()
        
        if success:
            print("\n🎉 集中式工具管理系统测试成功！")
        else:
            print("\n⚠️ 部分测试失败，请检查系统状态")
            
    except Exception as e:
        logger.error(f"❌ 测试过程异常: {e}")
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 