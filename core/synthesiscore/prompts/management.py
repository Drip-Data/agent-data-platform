#!/usr/bin/env python3
"""
Prompt 模板管理工具
提供模板监控、优化建议、A/B测试等高级功能
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from .base import PromptManager, PromptTemplate, PromptType

logger = logging.getLogger(__name__)


@dataclass
class PromptPerformanceMetrics:
    """Prompt性能指标"""
    template_name: str
    total_usage: int = 0
    success_rate: float = 0.0
    avg_response_time: float = 0.0
    error_count: int = 0
    last_used: Optional[datetime] = None
    performance_trend: List[float] = field(default_factory=list)
    
    def update_metrics(self, success: bool, response_time: float):
        """更新性能指标"""
        self.total_usage += 1
        self.last_used = datetime.now()
        
        if not success:
            self.error_count += 1
        
        # 更新成功率
        self.success_rate = (self.total_usage - self.error_count) / self.total_usage
        
        # 更新响应时间
        if self.avg_response_time == 0:
            self.avg_response_time = response_time
        else:
            self.avg_response_time = (self.avg_response_time * 0.8) + (response_time * 0.2)
        
        # 更新趋势（保留最近10次的成功率）
        current_success = 1.0 if success else 0.0
        self.performance_trend.append(current_success)
        if len(self.performance_trend) > 10:
            self.performance_trend.pop(0)


class PromptPerformanceManager:
    """Prompt性能管理器"""
    
    def __init__(self, storage_path: str = "output/SynthesisTask/prompt_metrics.json"):
        self.storage_path = Path(storage_path)
        self.metrics: Dict[str, PromptPerformanceMetrics] = {}
        self.load_metrics()
        
        logger.info("✅ PromptPerformanceManager 初始化完成")
    
    def record_usage(self, template_name: str, success: bool, response_time: float):
        """记录模板使用情况"""
        if template_name not in self.metrics:
            self.metrics[template_name] = PromptPerformanceMetrics(template_name)
        
        self.metrics[template_name].update_metrics(success, response_time)
        
        # 定期保存
        if self.metrics[template_name].total_usage % 10 == 0:
            self.save_metrics()
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        report = {
            "summary": {
                "total_templates": len(self.metrics),
                "total_usage": sum(m.total_usage for m in self.metrics.values()),
                "overall_success_rate": 0.0,
                "avg_response_time": 0.0
            },
            "top_performers": [],
            "underperformers": [],
            "usage_trends": {},
            "recommendations": []
        }
        
        if self.metrics:
            # 计算总体指标
            total_usage = sum(m.total_usage for m in self.metrics.values())
            if total_usage > 0:
                weighted_success_rate = sum(
                    m.success_rate * m.total_usage for m in self.metrics.values()
                ) / total_usage
                report["summary"]["overall_success_rate"] = weighted_success_rate
                
                weighted_response_time = sum(
                    m.avg_response_time * m.total_usage for m in self.metrics.values()
                ) / total_usage
                report["summary"]["avg_response_time"] = weighted_response_time
            
            # 排序模板
            sorted_metrics = sorted(
                self.metrics.values(),
                key=lambda x: x.success_rate * (x.total_usage + 1),  # 考虑使用频率
                reverse=True
            )
            
            # 最佳表现
            report["top_performers"] = [
                {
                    "name": m.template_name,
                    "success_rate": m.success_rate,
                    "usage_count": m.total_usage,
                    "avg_response_time": m.avg_response_time
                }
                for m in sorted_metrics[:5]
            ]
            
            # 表现不佳
            underperformers = [m for m in sorted_metrics if m.success_rate < 0.7 and m.total_usage > 5]
            report["underperformers"] = [
                {
                    "name": m.template_name,
                    "success_rate": m.success_rate,
                    "error_count": m.error_count,
                    "issues": self._analyze_issues(m)
                }
                for m in underperformers[-3:]
            ]
            
            # 使用趋势
            for name, metrics in self.metrics.items():
                if metrics.performance_trend:
                    recent_trend = sum(metrics.performance_trend[-5:]) / len(metrics.performance_trend[-5:])
                    report["usage_trends"][name] = {
                        "recent_success_rate": recent_trend,
                        "trend_direction": "improving" if recent_trend > metrics.success_rate else "declining"
                    }
            
            # 优化建议
            report["recommendations"] = self._generate_recommendations()
        
        return report
    
    def _analyze_issues(self, metrics: PromptPerformanceMetrics) -> List[str]:
        """分析性能问题"""
        issues = []
        
        if metrics.success_rate < 0.5:
            issues.append("成功率过低，需要重新设计模板")
        elif metrics.success_rate < 0.7:
            issues.append("成功率偏低，建议优化提示词")
        
        if metrics.avg_response_time > 30:
            issues.append("响应时间过长，考虑简化模板")
        
        if len(metrics.performance_trend) >= 5:
            recent_avg = sum(metrics.performance_trend[-5:]) / 5
            if recent_avg < metrics.success_rate - 0.1:
                issues.append("性能呈下降趋势")
        
        return issues
    
    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 分析总体模式
        total_templates = len(self.metrics)
        low_performers = sum(1 for m in self.metrics.values() if m.success_rate < 0.7)
        
        if low_performers / total_templates > 0.3:
            recommendations.append("超过30%的模板表现不佳，建议进行全面的模板质量审核")
        
        # 检查使用不平衡
        usage_counts = [m.total_usage for m in self.metrics.values()]
        if usage_counts:
            max_usage = max(usage_counts)
            min_usage = min(usage_counts)
            if max_usage > min_usage * 10:
                recommendations.append("模板使用不平衡，考虑整合低使用率模板")
        
        # 检查响应时间
        slow_templates = [m for m in self.metrics.values() if m.avg_response_time > 25]
        if len(slow_templates) > 0:
            recommendations.append(f"发现{len(slow_templates)}个响应缓慢的模板，建议优化或分解")
        
        return recommendations
    
    def save_metrics(self):
        """保存性能指标"""
        try:
            # 确保目录存在
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 序列化数据
            data = {}
            for name, metrics in self.metrics.items():
                data[name] = {
                    "template_name": metrics.template_name,
                    "total_usage": metrics.total_usage,
                    "success_rate": metrics.success_rate,
                    "avg_response_time": metrics.avg_response_time,
                    "error_count": metrics.error_count,
                    "last_used": metrics.last_used.isoformat() if metrics.last_used else None,
                    "performance_trend": metrics.performance_trend
                }
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"💾 性能指标已保存到: {self.storage_path}")
            
        except Exception as e:
            logger.error(f"❌ 保存性能指标失败: {e}")
    
    def load_metrics(self):
        """加载性能指标"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for name, metrics_data in data.items():
                    metrics = PromptPerformanceMetrics(
                        template_name=metrics_data["template_name"],
                        total_usage=metrics_data["total_usage"],
                        success_rate=metrics_data["success_rate"],
                        avg_response_time=metrics_data["avg_response_time"],
                        error_count=metrics_data["error_count"],
                        performance_trend=metrics_data.get("performance_trend", [])
                    )
                    
                    if metrics_data.get("last_used"):
                        metrics.last_used = datetime.fromisoformat(metrics_data["last_used"])
                    
                    self.metrics[name] = metrics
                
                logger.info(f"📊 加载了 {len(self.metrics)} 个模板的性能指标")
            
        except Exception as e:
            logger.error(f"❌ 加载性能指标失败: {e}")


class EnhancedPromptManager(PromptManager):
    """增强的Prompt管理器，集成性能监控"""
    
    def __init__(self):
        super().__init__()
        self.performance_manager = PromptPerformanceManager()
        
    async def render_template_with_monitoring(self, template_name: str, **kwargs) -> Tuple[str, bool, float]:
        """带性能监控的模板渲染"""
        start_time = datetime.now()
        success = False
        
        try:
            result = self.render_template(template_name, **kwargs)
            success = True
            return result, success, 0.0  # 渲染本身很快
            
        except Exception as e:
            logger.error(f"❌ 模板渲染失败 {template_name}: {e}")
            return "", success, 0.0
        finally:
            # 记录性能（这里主要记录模板使用情况）
            response_time = (datetime.now() - start_time).total_seconds()
            self.performance_manager.record_usage(template_name, success, response_time)
    
    async def render_and_call_llm(self, template_name: str, llm_client, **kwargs) -> Tuple[str, bool, float]:
        """渲染模板并调用LLM，记录完整性能"""
        start_time = datetime.now()
        success = False
        
        try:
            # 渲染模板
            prompt = self.render_template(template_name, **kwargs)
            
            # 调用LLM
            messages = [{"role": "user", "content": prompt}]
            response = await llm_client._call_api(messages, timeout=60)
            
            success = bool(response and len(response) > 10)  # 简单的成功判断
            return response, success, 0.0
            
        except Exception as e:
            logger.error(f"❌ 模板 {template_name} LLM调用失败: {e}")
            return "", success, 0.0
        finally:
            # 记录完整性能
            response_time = (datetime.now() - start_time).total_seconds()
            self.performance_manager.record_usage(template_name, success, response_time)
    
    def get_performance_dashboard(self) -> Dict[str, Any]:
        """获取性能仪表板"""
        template_stats = self.get_usage_statistics()
        performance_report = self.performance_manager.get_performance_report()
        
        return {
            "template_statistics": template_stats,
            "performance_metrics": performance_report,
            "health_status": self._assess_health_status(performance_report),
            "optimization_suggestions": self._get_optimization_suggestions(performance_report)
        }
    
    def _assess_health_status(self, performance_report: Dict) -> str:
        """评估系统健康状态"""
        overall_success_rate = performance_report["summary"]["overall_success_rate"]
        underperformers_count = len(performance_report["underperformers"])
        
        if overall_success_rate >= 0.9 and underperformers_count <= 1:
            return "excellent"
        elif overall_success_rate >= 0.8 and underperformers_count <= 2:
            return "good"
        elif overall_success_rate >= 0.7:
            return "fair"
        else:
            return "poor"
    
    def _get_optimization_suggestions(self, performance_report: Dict) -> List[str]:
        """获取优化建议"""
        suggestions = performance_report.get("recommendations", [])
        
        # 添加具体的操作建议
        if performance_report["summary"]["avg_response_time"] > 20:
            suggestions.append("考虑缓存常用模板的渲染结果以提高性能")
        
        underperformers = performance_report.get("underperformers", [])
        if len(underperformers) > 0:
            template_names = [u["name"] for u in underperformers]
            suggestions.append(f"优先优化以下模板: {', '.join(template_names)}")
        
        return suggestions


# 创建全局增强管理器实例
enhanced_prompt_manager = EnhancedPromptManager()