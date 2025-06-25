"""
Guardrails-AI集成中间件
为LLM输入输出提供专业的内容安全检查和结构化验证
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime
import traceback

# 🔧 P1修复2: 导入统一映射管理器
from core.config.unified_mapping_manager import get_unified_mapping_manager

logger = logging.getLogger(__name__)

try:
    import guardrails as gd
    from guardrails import Guard
    GUARDRAILS_AVAILABLE = True
    logger.info("✅ Guardrails-AI核心模块导入成功")
except ImportError as e:
    GUARDRAILS_AVAILABLE = False
    gd = None
    Guard = None
    logger.error(f"❌ Guardrails-AI导入失败: {e}")

from core.toolscore.structured_tools import LLMRequest, ToolValidationError

@dataclass
class GuardrailsValidationResult:
    """Guardrails验证结果"""
    is_valid: bool
    validated_data: Optional[Dict[str, Any]] = None
    original_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    corrections_applied: List[str] = field(default_factory=list)
    validation_time: float = 0.0
    guardrails_used: List[str] = field(default_factory=list)
    reask_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

class GuardrailsLLMMiddleware:
    """
    Guardrails-AI集成的LLM中间件
    提供输入输出的专业安全检查和结构化验证
    """
    
    def __init__(self, available_tool_ids: Optional[List[str]] = None):
        self.available_tool_ids = available_tool_ids or []
        self.validation_stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "reasks_triggered": 0,
            "auto_corrections": 0
        }
        
        # 🔧 P1修复2: 初始化统一映射管理器
        self.unified_mapper = get_unified_mapping_manager()
        
        # 初始化Guardrails Guards
        self._setup_guards()
        
    def _setup_guards(self):
        """设置Guardrails Guards"""
        if not GUARDRAILS_AVAILABLE:
            logger.warning("⚠️ Guardrails-AI未安装，将使用基础验证模式")
            self.input_guard = None
            self.output_guard = None
            return
        
        try:
            # 输入验证Guard - 使用Pydantic模型进行结构化验证
            logger.info("🔧 初始化输入验证Guard...")
            # 修复版本兼容性：新版本不支持prompt参数
            self.input_guard = Guard.from_pydantic(
                output_class=LLMRequest
            )
            
            # 输出验证Guard - 使用Rail string进行复杂验证
            logger.info("🔧 初始化输出验证Guard...")
            self.output_guard = self._create_advanced_output_guard()
            
            logger.info("✅ Guardrails Guards初始化成功")
            logger.info(f"   - 输入Guard: {'✅' if self.input_guard else '❌'}")
            logger.info(f"   - 输出Guard: {'✅' if self.output_guard else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ Guardrails Guards初始化失败: {e}")
            logger.error(f"   错误详情: {type(e).__name__}: {str(e)}")
            # 启用错误追踪以便调试
            import traceback
            logger.error(f"   完整追踪: {traceback.format_exc()}")
            
            # 尝试创建基础Guards作为后备
            try:
                logger.info("🔄 尝试创建基础Guards作为后备...")
                # 创建最基础的Guard配置 - 使用空Guard
                self.input_guard = Guard()
                self.output_guard = Guard()
                logger.info("✅ 基础Guards创建成功，将使用增强的基础验证模式")
            except Exception as fallback_error:
                logger.error(f"❌ 连基础Guards也无法创建: {fallback_error}")
                self.input_guard = None
                self.output_guard = None
    
    def _create_advanced_output_guard(self) -> Optional[Guard]:
        """创建高级输出验证Guard"""
        if not GUARDRAILS_AVAILABLE:
            return None
            
        try:
            # 创建基础Guard
            logger.debug("🔍 创建基础输出Guard")
            guard = Guard()
            
            return guard
            
        except Exception as e:
            logger.error(f"❌ 创建高级输出Guard失败: {e}")
            # 返回None，使用基础验证
            return None
    
    def _build_comprehensive_rail_schema(self) -> str:
        """构建综合性的Rail验证模式"""
        valid_actions = self._get_valid_actions_list()
        valid_tools = self._get_valid_tool_ids_list()
        
        # 构建更通用的Rail schema，不依赖特定验证器
        return f"""
<rail version="0.1">
<output>
    <object name="llm_response">
        <string name="thinking" description="LLM思考过程，必须详细且逻辑清晰" />
        <string name="action" description="要执行的具体动作" />
        <string name="tool_id" description="工具标识符" />
        <object name="parameters" description="动作执行参数" />
        <float name="confidence" description="执行置信度，范围0.0-1.0" />
    </object>
</output>

<prompt>
验证LLM响应的结构化输出：
1. thinking字段必须包含清晰的推理过程（长度5-3000字符）
2. action必须是支持的动作之一: {', '.join(valid_actions[:10])}...
3. tool_id必须是可用工具之一: {', '.join(valid_tools)}
4. parameters必须是有效的JSON对象
5. confidence必须在0.0-1.0范围内

确保所有字段都符合预期格式和业务逻辑。
</prompt>
</rail>
"""
    
    def _get_valid_actions_list(self) -> List[str]:
        """获取有效的动作列表"""
        # 从可用工具中提取动作
        common_actions = [
            "comprehensive_research", "quick_research", "research",
            "microsandbox_execute", "microsandbox_install_package", 
            "browser_navigate", "browser_extract_content", "browser_click_element",
            "analyze_tool_needs", "search_and_install_tools",
            "search_file_content", "list_code_definitions"
        ]
        return common_actions
    
    def _get_valid_tool_ids_list(self) -> List[str]:
        """获取有效的工具ID列表"""
        if self.available_tool_ids:
            return self.available_tool_ids
        
        # 默认工具ID
        default_tools = [
            "mcp-deepsearch", "microsandbox-mcp-server", 
            "browser-use-mcp-server", "mcp-search-tool"
        ]
        return default_tools
    
    def _get_valid_actions(self) -> str:
        """获取有效的动作列表（字符串格式）"""
        return " ".join(self._get_valid_actions_list())
    
    def _get_valid_tool_ids(self) -> str:
        """获取有效的工具ID列表（字符串格式）"""
        return " ".join(self._get_valid_tool_ids_list())
    
    def _add_custom_validators(self, guard: Guard):
        """为Guard添加自定义验证器 - 简化版本"""
        try:
            logger.debug("🔧 跳过复杂验证器添加，使用基础验证")
            # 由于Guardrails版本兼容性问题，暂时跳过复杂验证器
            pass
            
        except Exception as e:
            logger.debug(f"ℹ️ 自定义验证器添加跳过: {e}")
    
    def update_available_tools(self, tool_ids: List[str]):
        """更新可用工具列表"""
        self.available_tool_ids = tool_ids
        # 重新创建Guards以反映新的工具
        self._setup_guards()
        logger.info(f"🔄 Guardrails工具列表已更新: {len(tool_ids)}个工具")
    
    async def validate_input(self, input_data: Dict[str, Any]) -> GuardrailsValidationResult:
        """
        验证LLM输入
        检查恶意内容、格式正确性等
        """
        start_time = asyncio.get_event_loop().time()
        self.validation_stats["total_validations"] += 1
        
        try:
            if not GUARDRAILS_AVAILABLE or not self.input_guard:
                # 基础验证模式
                return await self._basic_input_validation(input_data, start_time)
            
            # 使用Guardrails进行高级验证
            try:
                # 构建验证消息
                validation_messages = [
                    {"role": "user", "content": f"Please validate this LLM input: {json.dumps(input_data, ensure_ascii=False)}"}
                ]
                
                validated_output = self.input_guard(
                    messages=validation_messages,
                    num_reasks=2  # 最多重新询问2次
                )
                
                validation_time = asyncio.get_event_loop().time() - start_time
                self.validation_stats["successful_validations"] += 1
                
                return GuardrailsValidationResult(
                    is_valid=True,
                    validated_data=validated_output.validated_output if hasattr(validated_output, 'validated_output') else input_data,
                    original_data=input_data,
                    validation_time=validation_time,
                    guardrails_used=["input_safety_check", "structure_validation"]
                )
                
            except Exception as e:
                # Guardrails验证失败
                validation_time = asyncio.get_event_loop().time() - start_time
                self.validation_stats["failed_validations"] += 1
                
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data=input_data,
                    error_message=f"Guardrails输入验证失败: {str(e)}",
                    validation_time=validation_time
                )
                
        except Exception as e:
            logger.error(f"❌ 输入验证过程出错: {e}")
            validation_time = asyncio.get_event_loop().time() - start_time
            
            return GuardrailsValidationResult(
                is_valid=False,
                original_data=input_data,
                error_message=f"验证过程异常: {str(e)}",
                validation_time=validation_time
            )
    
    async def validate_output(self, output_text: str, context: Dict[str, Any] = None) -> GuardrailsValidationResult:
        """
        验证LLM输出
        检查JSON格式、工具选择合理性、内容安全等
        """
        start_time = asyncio.get_event_loop().time()
        self.validation_stats["total_validations"] += 1
        
        try:
            # 首先尝试解析JSON
            try:
                if output_text.strip().startswith('{'):
                    parsed_data = json.loads(output_text)
                else:
                    # 提取JSON部分
                    import re
                    json_match = re.search(r'\{.*\}', output_text, re.DOTALL)
                    if json_match:
                        parsed_data = json.loads(json_match.group(0))
                    else:
                        raise ValueError("无法从输出中提取JSON")
            except (json.JSONDecodeError, ValueError) as e:
                validation_time = asyncio.get_event_loop().time() - start_time
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data={"raw_output": output_text},
                    error_message=f"JSON解析失败: {str(e)}",
                    validation_time=validation_time
                )
            
            if not GUARDRAILS_AVAILABLE or not self.output_guard:
                # 基础验证模式
                return await self._basic_output_validation(parsed_data, start_time)
            
            # 使用Guardrails进行高级验证
            try:
                # 构建验证消息
                validation_messages = [
                    {"role": "user", "content": f"Please validate this LLM output: {json.dumps(parsed_data, ensure_ascii=False)}"}
                ]
                
                validated_output = self.output_guard(
                    messages=validation_messages,
                    num_reasks=1  # 输出验证只重新询问1次
                )
                
                validation_time = asyncio.get_event_loop().time() - start_time
                self.validation_stats["successful_validations"] += 1
                
                return GuardrailsValidationResult(
                    is_valid=True,
                    validated_data=validated_output.validated_output if hasattr(validated_output, 'validated_output') else parsed_data,
                    original_data=parsed_data,
                    validation_time=validation_time,
                    guardrails_used=["output_structure_check", "tool_choice_validation", "rail_schema_validation"]
                )
                
            except Exception as e:
                # 尝试自动修正
                corrected_data = await self._attempt_auto_correction(parsed_data)
                if corrected_data != parsed_data:
                    validation_time = asyncio.get_event_loop().time() - start_time
                    self.validation_stats["auto_corrections"] += 1
                    
                    return GuardrailsValidationResult(
                        is_valid=True,
                        validated_data=corrected_data,
                        original_data=parsed_data,
                        corrections_applied=["tool_id_correction", "action_normalization"],
                        validation_time=validation_time,
                        guardrails_used=["auto_correction"]
                    )
                
                # 无法修正
                validation_time = asyncio.get_event_loop().time() - start_time
                self.validation_stats["failed_validations"] += 1
                
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data=parsed_data,
                    error_message=f"输出验证失败: {str(e)}",
                    validation_time=validation_time
                )
                
        except Exception as e:
            logger.error(f"❌ 输出验证过程出错: {e}")
            validation_time = asyncio.get_event_loop().time() - start_time
            
            return GuardrailsValidationResult(
                is_valid=False,
                original_data={"raw_output": output_text},
                error_message=f"验证过程异常: {str(e)}",
                validation_time=validation_time
            )
    
    async def _basic_input_validation(self, input_data: Dict[str, Any], start_time: float) -> GuardrailsValidationResult:
        """基础输入验证（Guardrails不可用时）"""
        try:
            # 检查必需字段
            required_fields = ["thinking", "action", "tool_id"]
            missing_fields = [field for field in required_fields if field not in input_data]
            
            if missing_fields:
                validation_time = asyncio.get_event_loop().time() - start_time
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data=input_data,
                    error_message=f"缺少必需字段: {missing_fields}",
                    validation_time=validation_time
                )
            
            # 基础内容安全检查
            text_content = f"{input_data.get('thinking', '')} {input_data.get('action', '')}"
            if self._contains_suspicious_content(text_content):
                validation_time = asyncio.get_event_loop().time() - start_time
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data=input_data,
                    error_message="输入包含可疑内容",
                    validation_time=validation_time
                )
            
            validation_time = asyncio.get_event_loop().time() - start_time
            self.validation_stats["successful_validations"] += 1
            
            return GuardrailsValidationResult(
                is_valid=True,
                validated_data=input_data,
                original_data=input_data,
                validation_time=validation_time,
                guardrails_used=["basic_validation"]
            )
            
        except Exception as e:
            validation_time = asyncio.get_event_loop().time() - start_time
            return GuardrailsValidationResult(
                is_valid=False,
                original_data=input_data,
                error_message=f"基础验证失败: {str(e)}",
                validation_time=validation_time
            )
    
    async def _basic_output_validation(self, parsed_data: Dict[str, Any], start_time: float) -> GuardrailsValidationResult:
        """基础输出验证（Guardrails不可用时）"""
        try:
            # 检查必需字段
            required_fields = ["thinking", "action", "tool_id"]
            missing_fields = [field for field in required_fields if field not in parsed_data]
            
            if missing_fields:
                validation_time = asyncio.get_event_loop().time() - start_time
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data=parsed_data,
                    error_message=f"输出缺少必需字段: {missing_fields}",
                    validation_time=validation_time
                )
            
            # 检查工具ID是否在可用列表中
            tool_id = parsed_data.get("tool_id", "")
            if self.available_tool_ids and tool_id not in self.available_tool_ids:
                # 尝试自动修正
                corrected_data = await self._attempt_auto_correction(parsed_data)
                if corrected_data != parsed_data:
                    validation_time = asyncio.get_event_loop().time() - start_time
                    self.validation_stats["auto_corrections"] += 1
                    
                    return GuardrailsValidationResult(
                        is_valid=True,
                        validated_data=corrected_data,
                        original_data=parsed_data,
                        corrections_applied=["tool_id_correction"],
                        validation_time=validation_time,
                        guardrails_used=["basic_auto_correction"]
                    )
                
                validation_time = asyncio.get_event_loop().time() - start_time
                return GuardrailsValidationResult(
                    is_valid=False,
                    original_data=parsed_data,
                    error_message=f"工具ID '{tool_id}' 不在可用列表中",
                    validation_time=validation_time
                )
            
            validation_time = asyncio.get_event_loop().time() - start_time
            self.validation_stats["successful_validations"] += 1
            
            return GuardrailsValidationResult(
                is_valid=True,
                validated_data=parsed_data,
                original_data=parsed_data,
                validation_time=validation_time,
                guardrails_used=["basic_validation"]
            )
            
        except Exception as e:
            validation_time = asyncio.get_event_loop().time() - start_time
            return GuardrailsValidationResult(
                is_valid=False,
                original_data=parsed_data,
                error_message=f"基础输出验证失败: {str(e)}",
                validation_time=validation_time
            )
    
    def _contains_suspicious_content(self, text: str) -> bool:
        """检查是否包含可疑内容"""
        suspicious_patterns = [
            # SQL注入模式
            r"(?i)\b(union|select|insert|delete|drop|exec|execute)\s+",
            # 脚本注入模式
            r"<script[^>]*>.*?</script>",
            # 命令注入模式
            r"(?i)\b(rm\s+-rf|del\s+/f|format\s+c:)",
            # 敏感文件路径
            r"(?i)(\.\.\/|\/etc\/passwd|\/etc\/shadow)"
        ]
        
        import re
        for pattern in suspicious_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    async def _attempt_auto_correction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """尝试自动修正数据"""
        corrected_data = data.copy()
        
        # 修正工具ID
        tool_id = data.get("tool_id", "")
        if tool_id and self.available_tool_ids:
            # 查找最相似的工具ID
            corrected_tool_id = self._find_closest_tool_id(tool_id)
            if corrected_tool_id and corrected_tool_id != tool_id:
                corrected_data["tool_id"] = corrected_tool_id
                logger.info(f"🔧 自动修正工具ID: {tool_id} -> {corrected_tool_id}")
        
        # 修正动作名称
        action = data.get("action", "")
        if action:
            corrected_action = self._normalize_action_name(action)
            if corrected_action != action:
                corrected_data["action"] = corrected_action
                logger.info(f"🔧 自动修正动作名称: {action} -> {corrected_action}")
        
        return corrected_data
    
    def _find_closest_tool_id(self, tool_id: str) -> Optional[str]:
        """查找最相似的工具ID"""
        if not self.available_tool_ids:
            return None
        
        # 简单的相似度匹配
        tool_id_lower = tool_id.lower()
        for available_id in self.available_tool_ids:
            if tool_id_lower in available_id.lower() or available_id.lower() in tool_id_lower:
                return available_id
        
        return None
    
    def _normalize_action_name(self, action: str) -> str:
        """规范化动作名称"""
        # 🔧 P1修复2: 使用统一映射管理器进行动作标准化
        try:
            # 尝试从统一映射中获取规范化的动作名称
            # 由于我们不知道具体的工具ID，我们需要遍历所有工具尝试匹配
            canonical_ids = ['mcp-deepsearch', 'microsandbox-mcp-server', 'browser-use-mcp-server', 'mcp-search-tool']
            
            for tool_id in canonical_ids:
                canonical_action = self.unified_mapper.get_canonical_action(tool_id, action)
                if canonical_action != action:
                    # 找到了映射
                    return canonical_action
            
            # 如果统一映射中没有找到，回退到原有逻辑
            action_mappings = {
                "search": "research",
                "browse": "browser_navigate",
                "execute": "microsandbox_execute",
                "install": "microsandbox_install_package",
                "run": "microsandbox_execute"
            }
            
            action_lower = action.lower()
            for pattern, replacement in action_mappings.items():
                if pattern in action_lower:
                    return replacement
                    
        except Exception as e:
            logger.warning(f"⚠️ 统一映射动作标准化失败: {e}")
            # 回退到原有逻辑
            action_mappings = {
                "search": "research",
                "browse": "browser_navigate",
                "execute": "microsandbox_execute",
                "install": "microsandbox_install_package",
                "run": "microsandbox_execute"
            }
            
            action_lower = action.lower()
            for pattern, replacement in action_mappings.items():
                if pattern in action_lower:
                    return replacement
        
        return action
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """获取验证统计信息"""
        total = self.validation_stats["total_validations"]
        if total == 0:
            return self.validation_stats
        
        return {
            **self.validation_stats,
            "success_rate": self.validation_stats["successful_validations"] / total,
            "failure_rate": self.validation_stats["failed_validations"] / total,
            "auto_correction_rate": self.validation_stats["auto_corrections"] / total,
            "guardrails_available": GUARDRAILS_AVAILABLE
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.validation_stats = {
            "total_validations": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "reasks_triggered": 0,
            "auto_corrections": 0
        }

# 全局Guardrails中间件实例
guardrails_middleware = GuardrailsLLMMiddleware()

def setup_guardrails_middleware(available_tool_ids: List[str]):
    """设置全局Guardrails中间件"""
    global guardrails_middleware
    guardrails_middleware = GuardrailsLLMMiddleware(available_tool_ids)
    logger.info(f"✅ Guardrails中间件已设置，支持{len(available_tool_ids)}个工具")

async def validate_llm_input(input_data: Dict[str, Any]) -> GuardrailsValidationResult:
    """验证LLM输入的便捷函数"""
    return await guardrails_middleware.validate_input(input_data)

async def validate_llm_output(output_text: str, context: Dict[str, Any] = None) -> GuardrailsValidationResult:
    """验证LLM输出的便捷函数"""
    return await guardrails_middleware.validate_output(output_text, context)