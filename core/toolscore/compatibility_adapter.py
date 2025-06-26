"""
兼容性适配器
在新架构部署期间提供向后兼容性
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CompatibilityAdapter:
    """兼容性适配器类"""
    
    def __init__(self):
        self.v2_available = False
        self.manager = None
        
        # 尝试加载v2.0架构
        try:
            from .enhanced_core_manager_v2 import EnhancedCoreManagerV2
            self.manager_class = EnhancedCoreManagerV2
            self.v2_available = True
            logger.info("✅ v2.0架构可用，使用增强服务容器")
        except ImportError as e:
            logger.debug(f"v2.0架构不可用: {e}")
            # 回退到原架构
            try:
                from .core_manager import CoreManager as OriginalCoreManager
                self.manager_class = OriginalCoreManager
                logger.info("⚠️ 使用原始架构")
            except ImportError:
                logger.error("❌ 无法加载任何核心管理器")
                raise
    
    def create_manager(self, *args, **kwargs):
        """创建兼容的管理器实例"""
        if self.v2_available:
            logger.info("🚀 创建v2.0增强核心管理器")
        else:
            logger.info("🔧 创建原始核心管理器")
        
        return self.manager_class(*args, **kwargs)
    
    def get_architecture_info(self) -> Dict[str, Any]:
        """获取当前架构信息"""
        return {
            "v2_available": self.v2_available,
            "current_architecture": "v2.0_service_container" if self.v2_available else "original",
            "manager_class": self.manager_class.__name__
        }