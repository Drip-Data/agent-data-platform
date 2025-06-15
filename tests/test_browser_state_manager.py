# -*- coding: utf-8 -*-
"""
测试 browser_state_manager.py 模块 - 浏览器状态管理器

覆盖功能:
1. BrowserStateManager初始化和配置
2. 导航历史记录管理
3. 页面状态跟踪
4. 文本和链接提取
5. 错误记录和统计
6. LLM提示生成
7. 状态重置和清理
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def browser_state_config():
    """BrowserStateManager配置"""
    return {
        "max_history_size": 50,
        "max_text_length": 10000,
        "max_links_count": 100,
        "error_threshold": 5
    }


@pytest.fixture
def sample_navigation_data():
    """示例导航数据"""
    return {
        "url": "https://example.com/page1",
        "title": "示例页面",
        "timestamp": datetime.now().isoformat(),
        "success": True,
        "load_time": 1.5
    }


@pytest.fixture
def sample_page_content():
    """示例页面内容"""
    return {
        "text": "这是页面的主要文本内容。包含一些重要信息。",
        "links": [
            {"text": "首页", "url": "https://example.com/"},
            {"text": "关于我们", "url": "https://example.com/about"},
            {"text": "联系方式", "url": "https://example.com/contact"}
        ],
        "forms": [
            {
                "id": "login-form",
                "action": "/login",
                "method": "POST",
                "fields": ["username", "password"]
            }
        ]
    }


class TestBrowserStateManagerInit:
    """BrowserStateManager初始化测试"""
    
    def test_init_with_config(self, browser_state_config):
        """测试使用配置初始化"""
        from core.browser_state_manager import BrowserStateManager
        
        manager = BrowserStateManager(browser_state_config)
        
        assert manager.config == browser_state_config
        assert manager.current_url is None
        assert manager.current_title is None
        assert manager.navigation_history == []
        assert manager.extracted_text == ""
        assert manager.extracted_links == []
        assert manager.action_errors == []
        assert manager.error_counts == {}
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        from core.browser_state_manager import BrowserStateManager
        
        manager = BrowserStateManager()
        
        # 验证默认配置
        assert manager.config["max_history_size"] == 100
        assert manager.config["max_text_length"] == 50000
        assert manager.config["max_links_count"] == 200
        assert manager.config["error_threshold"] == 10
    
    def test_init_partial_config(self):
        """测试使用部分配置初始化"""
        from core.browser_state_manager import BrowserStateManager
        
        partial_config = {"max_history_size": 25}
        manager = BrowserStateManager(partial_config)
        
        # 验证部分配置被应用，其他使用默认值
        assert manager.config["max_history_size"] == 25
        assert manager.config["max_text_length"] == 50000  # 默认值


class TestBrowserStateManagerNavigation:
    """BrowserStateManager导航管理测试"""
    
    @pytest.fixture
    def browser_manager(self, browser_state_config):
        """创建BrowserStateManager实例"""
        from core.browser_state_manager import BrowserStateManager
        return BrowserStateManager(browser_state_config)
    
    def test_record_navigation_success(self, browser_manager, sample_navigation_data):
        """测试记录成功导航"""
        browser_manager.record_navigation(
            sample_navigation_data["url"],
            sample_navigation_data["title"],
            sample_navigation_data["success"],
            sample_navigation_data["load_time"]
        )
        
        # 验证当前状态
        assert browser_manager.current_url == sample_navigation_data["url"]
        assert browser_manager.current_title == sample_navigation_data["title"]
        
        # 验证历史记录
        assert len(browser_manager.navigation_history) == 1
        
        history_entry = browser_manager.navigation_history[0]
        assert history_entry["url"] == sample_navigation_data["url"]
        assert history_entry["title"] == sample_navigation_data["title"]
        assert history_entry["success"] == sample_navigation_data["success"]
        assert history_entry["load_time"] == sample_navigation_data["load_time"]
        assert "timestamp" in history_entry
    
    def test_record_navigation_failure(self, browser_manager):
        """测试记录失败导航"""
        browser_manager.record_navigation(
            "https://invalid-url.com",
            None,
            False,
            0.0,
            error_message="页面加载失败"
        )
        
        # 验证当前状态（失败导航不更新当前状态）
        assert browser_manager.current_url is None
        assert browser_manager.current_title is None
        
        # 验证历史记录包含错误信息
        assert len(browser_manager.navigation_history) == 1
        
        history_entry = browser_manager.navigation_history[0]
        assert history_entry["success"] == False
        assert history_entry["error_message"] == "页面加载失败"
    
    def test_record_multiple_navigations(self, browser_manager):
        """测试记录多次导航"""
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3"
        ]
        
        for i, url in enumerate(urls):
            browser_manager.record_navigation(url, f"页面{i+1}", True, 1.0)
        
        # 验证当前状态是最后一次导航
        assert browser_manager.current_url == urls[-1]
        assert browser_manager.current_title == "页面3"
        
        # 验证历史记录
        assert len(browser_manager.navigation_history) == 3
        
        for i, entry in enumerate(browser_manager.navigation_history):
            assert entry["url"] == urls[i]
            assert entry["title"] == f"页面{i+1}"
    
    def test_navigation_history_size_limit(self, browser_manager):
        """测试导航历史记录大小限制"""
        max_size = browser_manager.config["max_history_size"]
        
        # 添加超过限制的导航记录
        for i in range(max_size + 10):
            browser_manager.record_navigation(f"https://example.com/page{i}", f"页面{i}", True, 1.0)
        
        # 验证历史记录大小不超过限制
        assert len(browser_manager.navigation_history) == max_size
        
        # 验证保留的是最新的记录
        last_entry = browser_manager.navigation_history[-1]
        assert "page59" in last_entry["url"]  # max_size=50, 所以最后一个是page59
    
    def test_record_navigation_attempt(self, browser_manager):
        """测试记录导航尝试"""
        target_url = "https://example.com/target"
        
        browser_manager.record_navigation_attempt(target_url, "点击链接")
        
        # 验证历史记录包含尝试信息
        assert len(browser_manager.navigation_history) == 1
        
        attempt_entry = browser_manager.navigation_history[0]
        assert attempt_entry["url"] == target_url
        assert attempt_entry["action"] == "点击链接"
        assert attempt_entry["type"] == "attempt"
        assert "timestamp" in attempt_entry


class TestBrowserStateManagerContentExtraction:
    """BrowserStateManager内容提取测试"""
    
    @pytest.fixture
    def browser_manager(self, browser_state_config):
        """创建BrowserStateManager实例"""
        from core.browser_state_manager import BrowserStateManager
        return BrowserStateManager(browser_state_config)
    
    def test_record_extracted_text(self, browser_manager, sample_page_content):
        """测试记录提取的文本"""
        browser_manager.record_extracted_text(sample_page_content["text"])
        
        assert browser_manager.extracted_text == sample_page_content["text"]
    
    def test_record_extracted_text_length_limit(self, browser_manager):
        """测试文本长度限制"""
        max_length = browser_manager.config["max_text_length"]
        long_text = "x" * (max_length + 1000)
        
        browser_manager.record_extracted_text(long_text)
        
        # 验证文本被截断
        assert len(browser_manager.extracted_text) <= max_length
        assert browser_manager.extracted_text.endswith("...")
    
    def test_record_extracted_links(self, browser_manager, sample_page_content):
        """测试记录提取的链接"""
        browser_manager.record_extracted_links(sample_page_content["links"])
        
        assert browser_manager.extracted_links == sample_page_content["links"]
        assert len(browser_manager.extracted_links) == 3
    
    def test_record_extracted_links_count_limit(self, browser_manager):
        """测试链接数量限制"""
        max_count = browser_manager.config["max_links_count"]
        
        # 创建超过限制的链接列表
        many_links = [
            {"text": f"链接{i}", "url": f"https://example.com/link{i}"}
            for i in range(max_count + 20)
        ]
        
        browser_manager.record_extracted_links(many_links)
        
        # 验证链接数量不超过限制
        assert len(browser_manager.extracted_links) == max_count
    
    def test_record_extracted_links_empty_list(self, browser_manager):
        """测试记录空链接列表"""
        browser_manager.record_extracted_links([])
        
        assert browser_manager.extracted_links == []
    
    def test_record_extracted_links_none(self, browser_manager):
        """测试记录None链接"""
        browser_manager.record_extracted_links(None)
        
        assert browser_manager.extracted_links == []


class TestBrowserStateManagerErrorHandling:
    """BrowserStateManager错误处理测试"""
    
    @pytest.fixture
    def browser_manager(self, browser_state_config):
        """创建BrowserStateManager实例"""
        from core.browser_state_manager import BrowserStateManager
        return BrowserStateManager(browser_state_config)
    
    def test_record_action_error(self, browser_manager):
        """测试记录操作错误"""
        error_info = {
            "action": "click",
            "selector": "#submit-btn",
            "error_message": "元素未找到",
            "error_type": "ElementNotFound"
        }
        
        browser_manager.record_action_error(
            error_info["action"],
            error_info["error_message"],
            error_info["selector"],
            error_info["error_type"]
        )
        
        # 验证错误记录
        assert len(browser_manager.action_errors) == 1
        
        error_entry = browser_manager.action_errors[0]
        assert error_entry["action"] == error_info["action"]
        assert error_entry["error_message"] == error_info["error_message"]
        assert error_entry["selector"] == error_info["selector"]
        assert error_entry["error_type"] == error_info["error_type"]
        assert "timestamp" in error_entry
        
        # 验证错误计数
        assert browser_manager.error_counts["ElementNotFound"] == 1
    
    def test_record_multiple_errors_same_type(self, browser_manager):
        """测试记录相同类型的多个错误"""
        for i in range(3):
            browser_manager.record_action_error(
                "click",
                f"错误{i+1}",
                f"#btn{i+1}",
                "ElementNotFound"
            )
        
        # 验证错误记录数量
        assert len(browser_manager.action_errors) == 3
        
        # 验证错误计数
        assert browser_manager.error_counts["ElementNotFound"] == 3
    
    def test_record_different_error_types(self, browser_manager):
        """测试记录不同类型的错误"""
        error_types = ["ElementNotFound", "TimeoutError", "NetworkError"]
        
        for error_type in error_types:
            browser_manager.record_action_error(
                "action",
                f"{error_type}发生",
                "#element",
                error_type
            )
        
        # 验证错误计数
        for error_type in error_types:
            assert browser_manager.error_counts[error_type] == 1
    
    def test_get_error_count(self, browser_manager):
        """测试获取错误计数"""
        # 添加一些错误
        browser_manager.record_action_error("click", "错误1", "#btn1", "ElementNotFound")
        browser_manager.record_action_error("click", "错误2", "#btn2", "ElementNotFound")
        browser_manager.record_action_error("wait", "超时", None, "TimeoutError")
        
        # 测试获取特定类型的错误计数
        assert browser_manager.get_error_count("ElementNotFound") == 2
        assert browser_manager.get_error_count("TimeoutError") == 1
        assert browser_manager.get_error_count("NonExistentError") == 0
        
        # 测试获取总错误计数
        assert browser_manager.get_error_count() == 3


class TestBrowserStateManagerLLMIntegration:
    """BrowserStateManager LLM集成测试"""
    
    @pytest.fixture
    def browser_manager_with_data(self, browser_state_config, sample_navigation_data, sample_page_content):
        """创建包含数据的BrowserStateManager实例"""
        from core.browser_state_manager import BrowserStateManager
        
        manager = BrowserStateManager(browser_state_config)
        
        # 添加导航历史
        manager.record_navigation(
            sample_navigation_data["url"],
            sample_navigation_data["title"],
            sample_navigation_data["success"],
            sample_navigation_data["load_time"]
        )
        
        # 添加页面内容
        manager.record_extracted_text(sample_page_content["text"])
        manager.record_extracted_links(sample_page_content["links"])
        
        # 添加一些错误
        manager.record_action_error("click", "按钮未找到", "#submit", "ElementNotFound")
        
        return manager
    
    def test_get_state_summary_for_llm(self, browser_manager_with_data):
        """测试获取LLM状态摘要"""
        summary = browser_manager_with_data.get_state_summary_for_llm()
        
        # 验证摘要包含所有关键信息
        assert "current_page" in summary
        assert "navigation_history" in summary
        assert "page_content" in summary
        assert "recent_errors" in summary
        assert "error_statistics" in summary
        
        # 验证当前页面信息
        current_page = summary["current_page"]
        assert current_page["url"] == "https://example.com/page1"
        assert current_page["title"] == "示例页面"
        
        # 验证页面内容
        page_content = summary["page_content"]
        assert "这是页面的主要文本内容" in page_content["text"]
        assert len(page_content["links"]) == 3
        
        # 验证错误统计
        error_stats = summary["error_statistics"]
        assert error_stats["total_errors"] == 1
        assert error_stats["error_types"]["ElementNotFound"] == 1
    
    def test_get_state_summary_empty_state(self, browser_state_config):
        """测试获取空状态的摘要"""
        from core.browser_state_manager import BrowserStateManager
        
        manager = BrowserStateManager(browser_state_config)
        summary = manager.get_state_summary_for_llm()
        
        # 验证空状态摘要
        assert summary["current_page"]["url"] is None
        assert summary["current_page"]["title"] is None
        assert summary["navigation_history"] == []
        assert summary["page_content"]["text"] == ""
        assert summary["page_content"]["links"] == []
        assert summary["recent_errors"] == []
        assert summary["error_statistics"]["total_errors"] == 0
    
    def test_get_state_summary_with_history_limit(self, browser_manager_with_data):
        """测试获取带历史限制的状态摘要"""
        # 添加更多导航历史
        for i in range(10):
            browser_manager_with_data.record_navigation(
                f"https://example.com/page{i+2}",
                f"页面{i+2}",
                True,
                1.0
            )
        
        # 获取限制为5条的历史摘要
        summary = browser_manager_with_data.get_state_summary_for_llm(max_history_items=5)
        
        # 验证历史记录被限制
        assert len(summary["navigation_history"]) == 5
        
        # 验证是最新的5条记录
        last_entry = summary["navigation_history"][-1]
        assert "page11" in last_entry["url"]
    
    def test_get_state_summary_with_error_limit(self, browser_manager_with_data):
        """测试获取带错误限制的状态摘要"""
        # 添加更多错误
        for i in range(10):
            browser_manager_with_data.record_action_error(
                "click",
                f"错误{i+2}",
                f"#btn{i+2}",
                "ElementNotFound"
            )
        
        # 获取限制为3条的错误摘要
        summary = browser_manager_with_data.get_state_summary_for_llm(max_error_items=3)
        
        # 验证错误记录被限制
        assert len(summary["recent_errors"]) == 3
        
        # 验证错误统计仍然正确
        assert summary["error_statistics"]["total_errors"] == 11
        assert summary["error_statistics"]["error_types"]["ElementNotFound"] == 11


class TestBrowserStateManagerUtilityMethods:
    """BrowserStateManager工具方法测试"""
    
    @pytest.fixture
    def browser_manager(self, browser_state_config):
        """创建BrowserStateManager实例"""
        from core.browser_state_manager import BrowserStateManager
        return BrowserStateManager(browser_state_config)
    
    def test_reset_state(self, browser_manager, sample_navigation_data, sample_page_content):
        """测试重置状态"""
        # 添加一些数据
        browser_manager.record_navigation(
            sample_navigation_data["url"],
            sample_navigation_data["title"],
            True,
            1.0
        )
        browser_manager.record_extracted_text(sample_page_content["text"])
        browser_manager.record_extracted_links(sample_page_content["links"])
        browser_manager.record_action_error("click", "错误", "#btn", "Error")
        
        # 验证数据存在
        assert browser_manager.current_url is not None
        assert len(browser_manager.navigation_history) > 0
        assert browser_manager.extracted_text != ""
        assert len(browser_manager.extracted_links) > 0
        assert len(browser_manager.action_errors) > 0
        
        # 重置状态
        browser_manager.reset_state()
        
        # 验证状态被重置
        assert browser_manager.current_url is None
        assert browser_manager.current_title is None
        assert browser_manager.navigation_history == []
        assert browser_manager.extracted_text == ""
        assert browser_manager.extracted_links == []
        assert browser_manager.action_errors == []
        assert browser_manager.error_counts == {}
    
    def test_get_current_state(self, browser_manager, sample_navigation_data):
        """测试获取当前状态"""
        # 设置当前状态
        browser_manager.record_navigation(
            sample_navigation_data["url"],
            sample_navigation_data["title"],
            True,
            1.0
        )
        
        current_state = browser_manager.get_current_state()
        
        assert current_state["url"] == sample_navigation_data["url"]
        assert current_state["title"] == sample_navigation_data["title"]
        assert "timestamp" in current_state
    
    def test_get_current_state_empty(self, browser_manager):
        """测试获取空的当前状态"""
        current_state = browser_manager.get_current_state()
        
        assert current_state["url"] is None
        assert current_state["title"] is None
        assert current_state["timestamp"] is None
    
    def test_has_recent_errors(self, browser_manager):
        """测试检查是否有最近的错误"""
        # 初始状态没有错误
        assert browser_manager.has_recent_errors() == False
        
        # 添加错误
        browser_manager.record_action_error("click", "错误", "#btn", "Error")
        
        # 现在应该有错误
        assert browser_manager.has_recent_errors() == True
        
        # 测试时间窗口（默认5分钟）
        assert browser_manager.has_recent_errors(minutes=5) == True
        assert browser_manager.has_recent_errors(minutes=0) == False
    
    def test_get_navigation_summary(self, browser_manager):
        """测试获取导航摘要"""
        # 添加多次导航
        urls = [
            "https://example.com/home",
            "https://example.com/about",
            "https://example.com/contact"
        ]
        
        for i, url in enumerate(urls):
            browser_manager.record_navigation(url, f"页面{i+1}", True, 1.0)
        
        summary = browser_manager.get_navigation_summary()
        
        assert summary["total_navigations"] == 3
        assert summary["current_url"] == urls[-1]
        assert summary["successful_navigations"] == 3
        assert summary["failed_navigations"] == 0
        
        # 添加失败的导航
        browser_manager.record_navigation("https://invalid.com", None, False, 0.0)
        
        summary = browser_manager.get_navigation_summary()
        assert summary["total_navigations"] == 4
        assert summary["successful_navigations"] == 3
        assert summary["failed_navigations"] == 1


if __name__ == "__main__":
    pytest.main(["-v", __file__])