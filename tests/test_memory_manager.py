"""
记忆管理器测试
Tests for MemoryManager functionality
"""

import asyncio
import pytest
import pytest_asyncio

from core.memory_manager import MemoryManager, ConversationStep


class TestMemoryManager:
    """MemoryManager测试类"""
    
    @pytest_asyncio.fixture
    async def memory_manager(self):
        """创建测试用的MemoryManager实例"""
        # 使用内存模式（不需要Redis）
        return MemoryManager(redis_manager=None, max_memory_entries=100)
    
    @pytest.mark.asyncio
    async def test_store_conversation_step(self, memory_manager):
        """测试存储会话步骤"""
        # 存储会话步骤
        step_id = await memory_manager.store_conversation_step(
            task_id="test_task_1",
            session_id="test_session_1",
            user_input="计算 2+2",
            agent_output="2+2=4",
            thinking_summary="简单的数学计算",
            tools_used=["python-executor"],
            success=True,
            metadata={"calculation": True}
        )
        
        # 验证步骤ID生成
        assert step_id is not None
        assert "test_session_1" in step_id
        assert "test_task_1" in step_id
        
        # 验证缓存中存储了步骤
        assert step_id in memory_manager._memory_cache
        stored_step = memory_manager._memory_cache[step_id]
        assert stored_step.user_input == "计算 2+2"
        assert stored_step.agent_output == "2+2=4"
        assert stored_step.success is True
        assert "python-executor" in stored_step.tools_used
    
    @pytest.mark.asyncio
    async def test_get_conversation_context(self, memory_manager):
        """测试获取会话上下文"""
        session_id = "test_session_2"
        
        # 存储多个会话步骤
        for i in range(5):
            await memory_manager.store_conversation_step(
                task_id=f"task_{i}",
                session_id=session_id,
                user_input=f"用户输入 {i}",
                agent_output=f"助手输出 {i}",
                tools_used=[f"tool_{i}"],
                success=True
            )
        
        # 获取会话上下文
        context = await memory_manager.get_conversation_context(
            session_id=session_id, 
            max_steps=3
        )
        
        # 验证返回的上下文
        assert len(context) <= 3  # 限制最大步骤数
        assert all(isinstance(step, ConversationStep) for step in context)
        assert all(step.session_id == session_id for step in context)
        
        # 验证按时间倒序排列（最新的在前）
        for i in range(len(context) - 1):
            assert context[i].timestamp >= context[i + 1].timestamp
    
    @pytest.mark.asyncio
    async def test_generate_context_summary(self, memory_manager):
        """测试生成上下文摘要"""
        session_id = "test_session_3"
        
        # 存储一些有趣的会话步骤
        await memory_manager.store_conversation_step(
            task_id="search_task",
            session_id=session_id,
            user_input="搜索AI技术发展趋势",
            agent_output="找到了关于AI技术的最新报告",
            tools_used=["web-search", "deepsearch"],
            success=True
        )
        
        await memory_manager.store_conversation_step(
            task_id="calc_task",
            session_id=session_id,
            user_input="计算投资回报率",
            agent_output="投资回报率为15.5%",
            tools_used=["python-executor"],
            success=True
        )
        
        # 生成上下文摘要
        summary = await memory_manager.generate_context_summary(session_id)
        
        # 验证摘要内容
        assert "会话历史摘要" in summary
        assert "成功步骤: 2" in summary
        assert "失败步骤: 0" in summary
        assert any(tool in summary for tool in ["web-search", "deepsearch", "python-executor"])
        assert len(summary) > 0
    
    @pytest.mark.asyncio
    async def test_store_session_summary(self, memory_manager):
        """测试存储会话摘要"""
        session_id = "test_session_4"
        
        # 先存储一些会话步骤
        await memory_manager.store_conversation_step(
            task_id="summary_task",
            session_id=session_id,
            user_input="完成研究任务",
            agent_output="研究任务已完成",
            tools_used=["research-tool"],
            success=True
        )
        
        # 存储会话摘要
        success = await memory_manager.store_session_summary(
            session_id=session_id,
            main_topics=["AI研究", "技术分析"],
            key_insights=["AI技术快速发展", "需要持续学习"]
        )
        
        # 验证摘要存储成功
        assert success is True
        assert session_id in memory_manager._session_cache
        
        stored_summary = memory_manager._session_cache[session_id]
        assert stored_summary.session_id == session_id
        assert "AI研究" in stored_summary.main_topics
        assert "AI技术快速发展" in stored_summary.key_insights
        assert stored_summary.total_steps == 1
        assert stored_summary.successful_steps == 1
    
    @pytest.mark.asyncio
    async def test_get_cross_session_insights(self, memory_manager):
        """测试获取跨会话洞察"""
        # 创建多个会话摘要
        for i in range(3):
            session_id = f"insight_session_{i}"
            await memory_manager.store_conversation_step(
                task_id=f"task_{i}",
                session_id=session_id,
                user_input=f"任务 {i}",
                agent_output=f"完成任务 {i}",
                tools_used=["common-tool", f"specific-tool-{i}"],
                success=True
            )
            
            await memory_manager.store_session_summary(
                session_id=session_id,
                main_topics=[f"主题{i}"],
                key_insights=[f"洞察{i}"]
            )
        
        # 获取跨会话洞察
        insights = await memory_manager.get_cross_session_insights(limit=5)
        
        # 验证洞察内容
        assert len(insights) > 0
        assert any("common-tool" in insight for insight in insights)  # 应该识别出常用工具
        assert any("成功率" in insight for insight in insights)  # 应该有成功率统计
        assert any("会话" in insight for insight in insights)  # 应该有会话统计
    
    @pytest.mark.asyncio
    async def test_memory_stats(self, memory_manager):
        """测试记忆统计信息"""
        # 存储一些数据
        await memory_manager.store_conversation_step(
            task_id="stats_task",
            session_id="stats_session",
            user_input="测试统计",
            agent_output="统计测试完成",
            success=True
        )
        
        # 获取统计信息
        stats = await memory_manager.get_memory_stats()
        
        # 验证统计信息
        assert "cache_size" in stats
        assert "total_steps" in stats
        assert "use_redis" in stats
        assert stats["cache_size"] >= 1
        assert stats["total_steps"] >= 1
        assert stats["use_redis"] is False  # 测试模式下不使用Redis
    
    @pytest.mark.asyncio
    async def test_health_check(self, memory_manager):
        """测试健康检查"""
        health = await memory_manager.health_check()
        
        # 验证健康检查结果
        assert "status" in health
        assert "timestamp" in health
        assert "cache_size" in health
        assert "redis_available" in health
        
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        assert health["redis_available"] is False  # 测试模式下Redis不可用
        assert isinstance(health["cache_size"], int)
        assert health["timestamp"] > 0
    
    @pytest.mark.asyncio
    async def test_clear_memory(self, memory_manager):
        """测试清理记忆"""
        session_id = "clear_test_session"
        
        # 存储一些数据
        await memory_manager.store_conversation_step(
            task_id="clear_task",
            session_id=session_id,
            user_input="清理测试",
            agent_output="测试数据",
            success=True
        )
        
        # 验证数据存在
        context = await memory_manager.get_conversation_context(session_id)
        assert len(context) > 0
        
        # 清理特定会话
        await memory_manager.clear_memory(session_id=session_id)
        
        # 验证数据已清理
        context_after_clear = await memory_manager.get_conversation_context(session_id)
        assert len(context_after_clear) == 0
    
    @pytest.mark.asyncio
    async def test_cache_cleanup(self, memory_manager):
        """测试缓存清理功能"""
        # 创建一个小容量的内存管理器
        small_memory_manager = MemoryManager(redis_manager=None, max_memory_entries=3)
        
        # 存储超过容量的数据
        for i in range(5):
            await small_memory_manager.store_conversation_step(
                task_id=f"cleanup_task_{i}",
                session_id="cleanup_session",
                user_input=f"测试 {i}",
                agent_output=f"输出 {i}",
                success=True
            )
        
        # 验证缓存大小被限制
        assert len(small_memory_manager._memory_cache) <= small_memory_manager.max_memory_entries + 100  # 允许一定的清理容差


# 运行测试的主函数
if __name__ == "__main__":
    async def run_tests():
        """运行所有测试"""
        import sys
        import traceback
        
        test_class = TestMemoryManager()
        memory_manager = MemoryManager(redis_manager=None)
        
        # 模拟await memory_manager fixture
        async def get_memory_manager():
            return memory_manager
        
        tests = [
            ("store_conversation_step", lambda: test_class.test_store_conversation_step(memory_manager)),
            ("get_conversation_context", lambda: test_class.test_get_conversation_context(memory_manager)),
            ("generate_context_summary", lambda: test_class.test_generate_context_summary(memory_manager)),
            ("store_session_summary", lambda: test_class.test_store_session_summary(memory_manager)),
            ("get_cross_session_insights", lambda: test_class.test_get_cross_session_insights(memory_manager)),
            ("memory_stats", lambda: test_class.test_memory_stats(memory_manager)),
            ("health_check", lambda: test_class.test_health_check(memory_manager)),
            ("clear_memory", lambda: test_class.test_clear_memory(memory_manager)),
            ("cache_cleanup", lambda: test_class.test_cache_cleanup(memory_manager))
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                print(f"运行测试: {test_name}...")
                await test_func()
                print(f"✅ {test_name} 通过")
                passed += 1
            except Exception as e:
                print(f"❌ {test_name} 失败: {e}")
                traceback.print_exc()
                failed += 1
        
        print(f"\n测试结果: {passed} 通过, {failed} 失败")
        return failed == 0
    
    # 运行测试
    success = asyncio.run(run_tests())
    exit(0 if success else 1)