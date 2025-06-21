#!/usr/bin/env python3
"""
SynthesisCore配置加载器
负责从YAML配置文件加载SynthesisCore的所有参数
"""

import os
import yaml
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SynthesisCoreConfigLoader:
    """SynthesisCore配置加载器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "synthesiscore_config.yaml"
        
        self.config_path = Path(config_path)
        self._config = None
        self._load_config()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                logger.error(f"❌ 配置文件不存在: {self.config_path}")
                self._use_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            
            logger.info(f"✅ SynthesisCore配置加载成功: {self.config_path}")
            
        except Exception as e:
            logger.error(f"❌ 加载配置文件失败: {e}")
            self._use_default_config()
    
    def _use_default_config(self) -> None:
        """使用默认配置（硬编码的后备配置）"""
        logger.warning("⚠️ 使用默认配置作为后备")
        
        self._config = {
            "atomic_generation": {
                "max_conclusions_per_corpus": 20,
                "max_candidate_atomic_tasks": 10,
                "conclusion_extraction_confidence": 0.7,
                "atomicity_verification_threshold": 0.2,
                "parallel_workers": 4
            },
            "depth_extension": {
                "max_hops": 3,
                "max_backward_search_attempts": 5,
                "superset_validation_threshold": 0.8,
                "intermediate_task_quality_threshold": 0.7,
                "max_search_results_per_query": 10
            },
            "width_extension": {
                "min_tasks_for_grouping": 2,
                "max_tasks_per_group": 3,
                "semantic_similarity_threshold": 0.6,
                "decomposition_validation_threshold": 0.8,
                "complexity_validation_threshold": 0.7
            },
            "verification": {
                "overall_quality_threshold": 0.75,
                "dimension_weights": {
                    "executability": 0.25,
                    "difficulty": 0.15,
                    "answer_uniqueness": 0.15,
                    "tool_requirements": 0.15,
                    "language_quality": 0.15,
                    "cognitive_complexity": 0.10,
                    "atomicity": 0.05
                },
                "execution_timeout_seconds": 60,
                "max_verification_retries": 3
            },
            "adaptive_prompt": {
                "prompt_optimization_threshold": 0.1,
                "few_shot_examples_per_type": 20,
                "ab_test_sample_size": 50,
                "success_rate_window_size": 100,
                "prompt_version_retention": 5
            },
            "redis_queue": {
                "streams": {
                    "corpus_queue": "synthesis:v2:corpus_queue",
                    "atomic_tasks": "synthesis:v2:atomic_tasks",
                    "extended_tasks": "synthesis:v2:extended_tasks",
                    "verification_queue": "synthesis:v2:verification_queue",
                    "training_data": "synthesis:v2:training_data",
                    "quality_reports": "synthesis:v2:quality_reports"
                },
                "keys": {
                    "config": "synthesis:v2:config",
                    "prompt_versions": "synthesis:v2:prompt_versions",
                    "success_rates": "synthesis:v2:success_rates",
                    "few_shot_examples": "synthesis:v2:few_shot_examples",
                    "generation_metrics": "synthesis:v2:generation_metrics"
                },
                "batch_size": 10,
                "processing_timeout": 300
            }
        }
    
    def get_atomic_generation_config(self) -> Dict[str, Any]:
        """获取原子任务生成配置"""
        return self._config.get("atomic_generation", {})
    
    def get_depth_extension_config(self) -> Dict[str, Any]:
        """获取深度扩展配置"""
        return self._config.get("depth_extension", {})
    
    def get_width_extension_config(self) -> Dict[str, Any]:
        """获取宽度扩展配置"""
        return self._config.get("width_extension", {})
    
    def get_verification_config(self) -> Dict[str, Any]:
        """获取验证引擎配置"""
        return self._config.get("verification", {})
    
    def get_adaptive_prompt_config(self) -> Dict[str, Any]:
        """获取自适应提示词配置"""
        return self._config.get("adaptive_prompt", {})
    
    def get_redis_config(self) -> Dict[str, Any]:
        """获取Redis队列配置"""
        return self._config.get("redis_queue", {})
    
    def get_all_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config.copy()
    
    def get_config_value(self, section: str, key: str, default=None):
        """
        获取指定配置值
        
        Args:
            section: 配置段名称 (如 'atomic_generation')
            key: 配置键名称 (如 'atomicity_verification_threshold')
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        return self._config.get(section, {}).get(key, default)
    
    def update_config_value(self, section: str, key: str, value: Any) -> None:
        """
        动态更新配置值（仅内存中，不写入文件）
        
        Args:
            section: 配置段名称
            key: 配置键名称  
            value: 新的配置值
        """
        if section not in self._config:
            self._config[section] = {}
        
        old_value = self._config[section].get(key, "未设置")
        self._config[section][key] = value
        
        logger.info(f"🔧 配置更新: {section}.{key} = {value} (原值: {old_value})")
    
    def save_config_to_file(self, output_path: str = None) -> None:
        """
        保存当前配置到YAML文件
        
        Args:
            output_path: 输出文件路径，如果为None则覆盖原文件
        """
        if output_path is None:
            output_path = self.config_path
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, 
                         allow_unicode=True, indent=2, sort_keys=False)
            
            logger.info(f"✅ 配置已保存到: {output_path}")
            
        except Exception as e:
            logger.error(f"❌ 保存配置失败: {e}")
    
    def reload_config(self) -> None:
        """重新加载配置文件"""
        logger.info("🔄 重新加载配置文件...")
        self._load_config()
    
    def validate_config(self) -> bool:
        """
        验证配置文件的完整性和合理性
        
        Returns:
            配置是否有效
        """
        errors = []
        
        # 检查必要的配置段
        required_sections = [
            "atomic_generation", "depth_extension", "width_extension", 
            "verification", "adaptive_prompt", "redis_queue"
        ]
        
        for section in required_sections:
            if section not in self._config:
                errors.append(f"缺少配置段: {section}")
        
        # 检查阈值范围 (0.0-1.0)
        threshold_checks = [
            ("atomic_generation", "conclusion_extraction_confidence"),
            ("atomic_generation", "atomicity_verification_threshold"),
            ("depth_extension", "superset_validation_threshold"),
            ("depth_extension", "intermediate_task_quality_threshold"),
            ("width_extension", "semantic_similarity_threshold"),
            ("width_extension", "decomposition_validation_threshold"),
            ("width_extension", "complexity_validation_threshold"),
            ("verification", "overall_quality_threshold"),
        ]
        
        for section, key in threshold_checks:
            value = self.get_config_value(section, key)
            if value is not None and not (0.0 <= value <= 1.0):
                errors.append(f"{section}.{key} = {value} 不在合理范围 [0.0, 1.0]")
        
        # 检查权重总和
        weights = self.get_config_value("verification", "dimension_weights", {})
        if weights:
            total_weight = sum(weights.values())
            if abs(total_weight - 1.0) > 0.01:  # 允许小的浮点误差
                errors.append(f"verification.dimension_weights 权重总和 = {total_weight:.3f} 不等于 1.0")
        
        if errors:
            logger.error("❌ 配置验证失败:")
            for error in errors:
                logger.error(f"  - {error}")
            return False
        
        logger.info("✅ 配置验证通过")
        return True
    
    def print_current_config(self) -> None:
        """打印当前配置摘要（用于调试）"""
        print("\n" + "="*60)
        print("SynthesisCore 当前配置摘要")
        print("="*60)
        
        # 原子任务生成关键参数
        atomic_config = self.get_atomic_generation_config()
        print(f"🔬 原子任务生成:")
        print(f"  - 原子性验证阈值: {atomic_config.get('atomicity_verification_threshold', '未设置')}")
        print(f"  - 结论提取置信度: {atomic_config.get('conclusion_extraction_confidence', '未设置')}")
        print(f"  - 并行工作线程: {atomic_config.get('parallel_workers', '未设置')}")
        
        # 验证引擎关键参数
        verification_config = self.get_verification_config()
        print(f"✅ 验证引擎:")
        print(f"  - 总体质量阈值: {verification_config.get('overall_quality_threshold', '未设置')}")
        
        # 扩展配置关键参数
        depth_config = self.get_depth_extension_config()
        width_config = self.get_width_extension_config()
        print(f"📈 扩展配置:")
        print(f"  - 最大跳跃数: {depth_config.get('max_hops', '未设置')}")
        print(f"  - 语义相似度阈值: {width_config.get('semantic_similarity_threshold', '未设置')}")
        
        print("="*60 + "\n")


# 全局配置实例
_config_loader = None

def get_synthesis_config() -> SynthesisCoreConfigLoader:
    """
    获取全局SynthesisCore配置实例（单例模式）
    
    Returns:
        SynthesisCoreConfigLoader实例
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = SynthesisCoreConfigLoader()
    return _config_loader

def reload_synthesis_config() -> None:
    """重新加载SynthesisCore配置"""
    global _config_loader
    if _config_loader is not None:
        _config_loader.reload_config()
    else:
        _config_loader = SynthesisCoreConfigLoader()