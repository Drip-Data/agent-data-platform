"""
工具参数校验和自动补齐模块
解决 P0-1: LLM 生成的 parameters 缺少必填字段问题
"""

import logging
import json
import asyncio
import time
import yaml
from typing import Dict, Any, Optional, List, Union, Tuple
from pydantic import BaseModel, ValidationError, Field
from dataclasses import dataclass
from pathlib import Path

# 🔧 P1修复2: 导入统一映射管理器
from core.config.unified_mapping_manager import get_unified_mapping_manager

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """参数校验结果"""
    is_valid: bool
    missing_required: List[str]
    invalid_params: List[str]
    suggestions: Dict[str, Any]
    error_message: Optional[str] = None

class ParameterValidator:
    """工具参数校验器"""
    
    def __init__(self):
        # 🔧 P0-2强化：异步安全和配置化别名系统
        self._schema_cache_lock = asyncio.Lock()
        self._last_schema_check = 0
        self._alias_config_path = Path(__file__).parent.parent.parent / "config" / "tool_aliases.yaml"
        
        # 🔧 P1修复2: 使用统一映射管理器
        self.unified_mapper = get_unified_mapping_manager()
        
        # 加载外部别名配置（向后兼容）
        self._load_alias_config()
        
        # 定义每个工具的必需参数和参数模式
        self.tool_schemas = {
            "deepsearch": {
                "research": {
                    "required": ["question"],
                    "optional": ["max_results", "initial_queries", "reasoning_model"],
                    "patterns": {
                        "question": "研究问题或查询内容",
                        "max_results": 10,
                        "initial_queries": ["相关搜索词"],
                        "reasoning_model": "gpt-4"
                    }
                },
                "quick_research": {
                    "required": ["question"],
                    "optional": ["max_results"],
                    "patterns": {
                        "question": "快速研究问题",
                        "max_results": 5
                    }
                },
                "comprehensive_research": {
                    "required": ["question"],
                    "optional": ["max_results", "depth"],
                    "patterns": {
                        "question": "全面研究问题",
                        "max_results": 15,
                        "depth": "comprehensive"
                    }
                }
            },
            "microsandbox": {
                "microsandbox_execute": {
                    "required": ["code"],
                    "optional": ["session_id", "timeout"],
                    "patterns": {
                        "code": "Python代码字符串",
                        "session_id": "session_1",
                        "timeout": 30
                    }
                },
                "microsandbox_install_package": {
                    "required": ["package_name"],
                    "optional": ["version", "session_id"],
                    "patterns": {
                        "package_name": "包名",
                        "version": "最新版本",
                        "session_id": "session_1"
                    }
                },
                "microsandbox_list_sessions": {
                    "required": [],
                    "optional": [],
                    "patterns": {}
                },
                "microsandbox_close_session": {
                    "required": ["session_id"],
                    "optional": [],
                    "patterns": {
                        "session_id": "要关闭的会话ID"
                    }
                },
                "microsandbox_cleanup_expired": {
                    "required": [],
                    "optional": ["max_age"],
                    "patterns": {
                        "max_age": 3600
                    }
                }
            },
            "browser_use": {
                "browser_use_execute_task": {
                    "required": ["task"],
                    "optional": ["max_steps", "use_vision"],
                    "patterns": {
                        "task": "浏览器任务描述",
                        "max_steps": 10,
                        "use_vision": True
                    }
                },
                "browser_navigate": {
                    "required": ["url"],
                    "optional": ["wait_time"],
                    "patterns": {
                        "url": "https://example.com",
                        "wait_time": 3
                    }
                },
                "browser_click_element": {
                    # 🔧 P0紧急修复3: browser_click_element实际使用index参数而非selector
                    "required": ["index"],
                    "optional": [],
                    "patterns": {
                        "index": 1
                    }
                },
                "browser_input_text": {
                    # 🔧 P0紧急修复3: browser_input_text实际使用index+text参数而非selector
                    "required": ["index", "text"],
                    "optional": [],
                    "patterns": {
                        "index": 0,
                        "text": "输入的文本"
                    }
                },
                "browser_extract_content": {
                    "required": [],
                    "optional": ["selector"],
                    "patterns": {
                        "selector": "h1, p"
                    }
                },
                "browser_search_google": {
                    "required": ["query"],
                    "optional": [],
                    "patterns": {
                        "query": "搜索查询"
                    }
                }
            },
            "mcp-search-tool": {
                "search_file_content": {
                    "required": ["file_path", "regex_pattern"],
                    "optional": [],
                    "patterns": {
                        "file_path": "src/main.py",
                        "regex_pattern": "def.*"
                    }
                },
                "list_code_definitions": {
                    "required": [],
                    "optional": ["file_path", "directory_path"],
                    "patterns": {
                        "file_path": "src/main.py",
                        "directory_path": "src/"
                    }
                },
                "analyze_tool_needs": {
                    "required": ["task_description"],
                    "optional": [],
                    "patterns": {
                        "task_description": "任务描述"
                    }
                },
                "search_and_install_tools": {
                    "required": ["task_description"],
                    "optional": ["reason"],
                    "patterns": {
                        "task_description": "需要的工具功能描述",
                        "reason": "当前工具不足的原因"
                    }
                }
            },
            # 🔧 P1-1扩展：新增工具schema支持
            "filesystem": {
                "read_file": {
                    "required": ["path"],
                    "optional": ["encoding", "max_size"],
                    "patterns": {
                        "path": "文件路径",
                        "encoding": "utf-8",
                        "max_size": 1024000
                    }
                },
                "write_file": {
                    "required": ["path", "content"],
                    "optional": ["encoding", "mode"],
                    "patterns": {
                        "path": "文件路径",
                        "content": "文件内容",
                        "encoding": "utf-8",
                        "mode": "w"
                    }
                },
                "list_directory": {
                    "required": ["path"],
                    "optional": ["recursive", "pattern"],
                    "patterns": {
                        "path": "目录路径",
                        "recursive": False,
                        "pattern": "*"
                    }
                }
            },
            "database": {
                "execute_query": {
                    "required": ["query"],
                    "optional": ["database", "timeout"],
                    "patterns": {
                        "query": "SQL查询语句",
                        "database": "默认数据库", 
                        "timeout": 30
                    }
                },
                "insert_data": {
                    "required": ["table", "data"],
                    "optional": ["batch_size"],
                    "patterns": {
                        "table": "表名",
                        "data": {"column": "value"},
                        "batch_size": 100
                    }
                },
                "create_table": {
                    "required": ["table", "schema"],
                    "optional": ["if_not_exists"],
                    "patterns": {
                        "table": "表名",
                        "schema": {"column": "type"},
                        "if_not_exists": True
                    }
                }
            },
            "api-client": {
                "make_request": {
                    "required": ["url"],
                    "optional": ["method", "data", "headers", "timeout"],
                    "patterns": {
                        "url": "API接口地址",
                        "method": "GET",
                        "data": {"key": "value"},
                        "headers": {"Content-Type": "application/json"},
                        "timeout": 30
                    }
                },
                "upload_file": {
                    "required": ["url", "file_path"],
                    "optional": ["field_name", "headers"],
                    "patterns": {
                        "url": "上传接口地址",
                        "file_path": "文件路径",
                        "field_name": "file",
                        "headers": {}
                    }
                }
            },
            "text-processing": {
                "analyze_text": {
                    "required": ["text"],
                    "optional": ["analysis_type", "language"],
                    "patterns": {
                        "text": "待分析文本",
                        "analysis_type": "sentiment",
                        "language": "zh-CN"
                    }
                },
                "transform_text": {
                    "required": ["text", "operation"],
                    "optional": ["options"],
                    "patterns": {
                        "text": "原始文本",
                        "operation": "lowercase",
                        "options": {}
                    }
                },
                "extract_keywords": {
                    "required": ["text"],
                    "optional": ["max_keywords", "min_score"],
                    "patterns": {
                        "text": "文本内容",
                        "max_keywords": 10,
                        "min_score": 0.5
                    }
                }
            },
            "data-visualization": {
                "create_chart": {
                    "required": ["data", "chart_type"],
                    "optional": ["title", "labels", "colors"],
                    "patterns": {
                        "data": [{"x": 1, "y": 2}],
                        "chart_type": "line",
                        "title": "图表标题",
                        "labels": {"x": "X轴", "y": "Y轴"},
                        "colors": ["#FF6B6B", "#4ECDC4"]
                    }
                },
                "export_chart": {
                    "required": ["chart_id", "format"],
                    "optional": ["path", "quality"],
                    "patterns": {
                        "chart_id": "chart_001",
                        "format": "png",
                        "path": "charts/",
                        "quality": 95
                    }
                }
            }
        }

    def validate_tool_call(self, tool_id: str, action: str, parameters: Dict[str, Any], 
                          task_description: str = "") -> ValidationResult:
        """
        校验工具调用参数
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            parameters: 参数字典
            task_description: 任务描述，用于智能补齐
            
        Returns:
            ValidationResult: 校验结果
        """
        logger.debug(f"🔍 校验工具调用: {tool_id}.{action} with {parameters}")
        
        # 🔧 P1修复2: 使用统一映射管理器进行预处理
        try:
            # 自动修正请求
            corrected_request = self.unified_mapper.auto_correct_request(tool_id, action, parameters)
            
            # 验证工具动作组合
            validation_result = self.unified_mapper.validate_tool_action_combination(tool_id, action)
            if not validation_result.is_valid:
                return ValidationResult(
                    is_valid=False,
                    missing_required=[],
                    invalid_params=[],
                    suggestions={},
                    error_message=f"无效的工具动作组合: {'; '.join(validation_result.errors)}"
                )
            
            # 使用修正后的值进行后续验证
            tool_id = corrected_request['tool_id']
            action = corrected_request['action'] 
            parameters = corrected_request['parameters']
            
            logger.debug(f"✅ 统一映射修正后: {tool_id}.{action} with {parameters}")
            
        except Exception as e:
            logger.warning(f"⚠️ 统一映射处理异常: {e}")
        
        # 检查工具是否存在
        if tool_id not in self.tool_schemas:
            return ValidationResult(
                is_valid=False,
                missing_required=[],
                invalid_params=[],
                suggestions={},
                error_message=f"未知工具: {tool_id}"
            )
        
        # 检查动作是否存在
        if action not in self.tool_schemas[tool_id]:
            available_actions = list(self.tool_schemas[tool_id].keys())
            return ValidationResult(
                is_valid=False,
                missing_required=[],
                invalid_params=[],
                suggestions={},
                error_message=f"工具 {tool_id} 不支持动作 {action}。可用动作: {available_actions}"
            )
        
        schema = self.tool_schemas[tool_id][action]
        required_params = schema["required"]
        optional_params = schema["optional"]
        patterns = schema["patterns"]
        
        # 🔧 增强的必需参数检查 - 处理更多边界情况
        missing_required = []
        for param in required_params:
            param_value = parameters.get(param)
            # 检查空值、None、空字符串、空列表、空字典
            if (param_value is None or 
                param_value == "" or 
                param_value == [] or 
                param_value == {} or
                (isinstance(param_value, str) and param_value.strip() == "")):
                missing_required.append(param)
        
        # 🔧 增强的参数类型和有效性检查
        valid_params = set(required_params + optional_params)
        invalid_params = []
        type_errors = []
        
        for param, value in parameters.items():
            if param not in valid_params:
                invalid_params.append(param)
            else:
                # 🔍 参数类型验证
                try:
                    type_error = self._validate_parameter_type(tool_id, action, param, value, patterns)
                    if type_error:
                        type_errors.append(f"{param}: {type_error}")
                except Exception as e:
                    logger.warning(f"参数类型验证异常 {param}: {e}")
        
        # 将类型错误也视为无效参数
        if type_errors:
            logger.warning(f"参数类型错误: {type_errors}")
        
        # 生成参数补齐建议
        suggestions = {}
        if missing_required:
            suggestions = self._generate_parameter_suggestions(
                tool_id, action, missing_required, task_description, patterns
            )
        
        is_valid = len(missing_required) == 0
        
        if not is_valid:
            error_msg = f"缺少必需参数: {missing_required}"
            if invalid_params:
                error_msg += f"，无效参数: {invalid_params}"
        else:
            error_msg = None
            if invalid_params:
                logger.warning(f"⚠️ 发现无效参数（将被忽略）: {invalid_params}")
        
        return ValidationResult(
            is_valid=is_valid,
            missing_required=missing_required,
            invalid_params=invalid_params,
            suggestions=suggestions,
            error_message=error_msg
        )
    
    def _generate_parameter_suggestions(self, tool_id: str, action: str, 
                                      missing_params: List[str], task_description: str,
                                      patterns: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于任务描述和模式生成参数建议 - 增强版
        """
        suggestions = {}
        
        # 🧠 智能任务语义分析
        task_lower = task_description.lower()
        task_keywords = self._extract_task_keywords(task_description)
        
        for param in missing_params:
            if param in patterns:
                # 🎯 智能参数推断逻辑
                if param in ["question", "query", "task_description"]:
                    # 直接使用任务描述，如果为空则使用模式
                    suggestions[param] = task_description if task_description.strip() else patterns[param]
                    
                elif param == "code":
                    # 🔧 代码参数智能生成
                    if any(keyword in task_lower for keyword in ['代码', 'code', '计算', 'calculate', '执行', 'execute']):
                        # 基于任务类型生成代码框架
                        if '计算' in task_lower or 'calculate' in task_lower:
                            suggestions[param] = f"# 计算任务: {task_description}\n# TODO: 实现具体计算逻辑\nresult = None\nprint(f'计算结果: {{result}}')"
                        elif '数据' in task_lower or 'data' in task_lower:
                            suggestions[param] = f"# 数据处理任务: {task_description}\nimport pandas as pd\n# TODO: 实现数据处理逻辑\nprint('数据处理完成')"
                        else:
                            suggestions[param] = f"# 任务: {task_description}\n# TODO: 根据任务需求编写代码\nprint('任务执行开始')"
                    else:
                        suggestions[param] = patterns[param]
                        
                elif param == "url":
                    # 🌐 URL参数智能提取
                    import re
                    # 优先从任务描述中提取URL
                    urls = re.findall(r'https?://[^\s\u4e00-\u9fff]+', task_description)
                    if urls:
                        suggestions[param] = urls[0]
                    elif any(keyword in task_lower for keyword in ['google', '谷歌', '搜索']):
                        suggestions[param] = "https://www.google.com"
                    elif any(keyword in task_lower for keyword in ['github', 'git']):
                        suggestions[param] = "https://github.com"
                    elif any(keyword in task_lower for keyword in ['python', 'py']):
                        suggestions[param] = "https://python.org"
                    else:
                        suggestions[param] = patterns[param]
                        
                elif param == "index":
                    # 🎯 索引参数智能推断
                    if '第一个' in task_description or 'first' in task_lower:
                        suggestions[param] = 0
                    elif '第二个' in task_description or 'second' in task_lower:
                        suggestions[param] = 1
                    elif '按钮' in task_description or 'button' in task_lower:
                        suggestions[param] = 1  # 通常按钮索引为1
                    else:
                        suggestions[param] = patterns[param]
                        
                elif param == "text":
                    # 📝 文本参数智能推断
                    # 从任务描述中提取可能的输入文本
                    if '输入' in task_description:
                        # 提取"输入"后面的内容
                        import re
                        match = re.search(r'输入[：:]?\s*["""\'](.*?)["""\']', task_description)
                        if match:
                            suggestions[param] = match.group(1)
                        else:
                            match = re.search(r'输入[：:]?\s*(\w+)', task_description)
                            if match:
                                suggestions[param] = match.group(1)
                            else:
                                suggestions[param] = task_description[:50]  # 截取前50字符作为输入
                    elif 'search' in task_lower or '搜索' in task_description:
                        # 搜索任务，提取搜索关键词
                        search_terms = []
                        for keyword in task_keywords:
                            if keyword not in ['search', 'google', '搜索', '查找']:
                                search_terms.append(keyword)
                        suggestions[param] = ' '.join(search_terms[:3]) if search_terms else task_description[:30]
                    else:
                        suggestions[param] = patterns[param]
                        
                elif param in ["file_path", "regex_pattern"]:
                    # 📁 文件和正则参数推断
                    if param == "file_path":
                        if any(ext in task_lower for ext in ['.py', '.js', '.java', '.cpp']):
                            # 从任务中提取文件扩展名
                            import re
                            ext_match = re.search(r'\.(\w+)', task_description)
                            if ext_match:
                                ext = ext_match.group()
                                suggestions[param] = f"src/main{ext}"
                            else:
                                suggestions[param] = "src/main.py"
                        else:
                            suggestions[param] = patterns[param]
                    elif param == "regex_pattern":
                        if 'function' in task_lower or '函数' in task_description:
                            suggestions[param] = r"def\s+\w+"
                        elif 'class' in task_lower or '类' in task_description:
                            suggestions[param] = r"class\s+\w+"
                        else:
                            suggestions[param] = patterns[param]
                else:
                    suggestions[param] = patterns[param]
                    
        # 🔍 参数相关性验证
        suggestions = self._validate_parameter_relationships(suggestions, tool_id, action)
        
        return suggestions
    
    def _extract_task_keywords(self, task_description: str) -> List[str]:
        """提取任务关键词"""
        import re
        # 移除标点符号并分词
        words = re.findall(r'\w+', task_description.lower())
        # 过滤停用词
        stop_words = {'的', '了', '在', '是', '和', '与', 'the', 'and', 'or', 'to', 'of', 'in', 'for'}
        keywords = [word for word in words if word not in stop_words and len(word) > 1]
        return keywords[:10]  # 返回前10个关键词
    
    def _validate_parameter_relationships(self, suggestions: Dict[str, Any], 
                                        tool_id: str, action: str) -> Dict[str, Any]:
        """验证参数间的关系和一致性"""
        validated = suggestions.copy()
        
        # 🔧 工具特定的参数关系验证
        if tool_id == "browser_use":
            # 浏览器工具的参数关系验证
            if action == "browser_input_text" and "index" in validated and "text" in validated:
                # 确保index是有效数字
                if not isinstance(validated["index"], int):
                    try:
                        validated["index"] = int(validated["index"])
                    except (ValueError, TypeError):
                        validated["index"] = 0
                        
        elif tool_id == "deepsearch":
            # DeepSearch的参数优化
            if action in ["research", "comprehensive_research"] and "question" in validated:
                # 确保question不为空且有意义
                if not validated["question"] or len(validated["question"].strip()) < 3:
                    validated["question"] = "请提供具体的研究问题"
                    
        elif tool_id == "microsandbox":
            # MicroSandbox的代码参数验证
            if action == "microsandbox_execute" and "code" in validated:
                # 确保代码包含基本的Python语法
                code = validated["code"]
                if not any(keyword in code for keyword in ['print', 'import', '=', 'def', 'class']):
                    validated["code"] = f"# {code}\nprint('执行开始')\n# TODO: 添加具体逻辑\nprint('执行完成')"
        
        return validated
    
    def _validate_parameter_type(self, tool_id: str, action: str, param: str, value: Any, patterns: Dict[str, Any]) -> Optional[str]:
        """验证参数类型是否正确
        
        Returns:
            str: 错误信息，如果验证通过则返回None
        """
        try:
            # 🔧 基于工具和动作的特定类型检查
            if tool_id == "browser_use":
                if param == "index" and not isinstance(value, int):
                    try:
                        int(value)  # 尝试转换
                    except (ValueError, TypeError):
                        return f"index必须是整数，得到: {type(value).__name__}"
                elif param == "url" and isinstance(value, str):
                    if not value.startswith(('http://', 'https://', 'file://')):
                        return "url必须以 http://, https:// 或 file:// 开头"
                elif param == "text" and not isinstance(value, str):
                    return f"text必须是字符串，得到: {type(value).__name__}"
                    
            elif tool_id == "microsandbox":
                if param == "code" and not isinstance(value, str):
                    return f"code必须是字符串，得到: {type(value).__name__}"
                elif param == "timeout" and not isinstance(value, (int, float)):
                    try:
                        float(value)  # 尝试转换
                    except (ValueError, TypeError):
                        return f"timeout必须是数字，得到: {type(value).__name__}"
                        
            elif tool_id == "deepsearch":
                if param == "question" and not isinstance(value, str):
                    return f"question必须是字符串，得到: {type(value).__name__}"
                elif param == "max_results" and not isinstance(value, int):
                    try:
                        int(value)  # 尝试转换
                    except (ValueError, TypeError):
                        return f"max_results必须是整数，得到: {type(value).__name__}"
            
            # 🔧 通用类型检查（基于patterns）
            if param in patterns:
                pattern_value = patterns[param]
                pattern_type = type(pattern_value)
                
                # 如果pattern有明确的类型，验证参数类型
                if pattern_type in (int, float, str, bool, list, dict):
                    if not isinstance(value, pattern_type):
                        # 尝试类型转换
                        if pattern_type == int and isinstance(value, (str, float)):
                            try:
                                int(value)
                            except (ValueError, TypeError):
                                return f"参数{param}应为{pattern_type.__name__}类型，得到: {type(value).__name__}"
                        elif pattern_type == float and isinstance(value, (str, int)):
                            try:
                                float(value)
                            except (ValueError, TypeError):
                                return f"参数{param}应为{pattern_type.__name__}类型，得到: {type(value).__name__}"
                        elif pattern_type == str and not isinstance(value, str):
                            return f"参数{param}应为字符串类型，得到: {type(value).__name__}"
                        elif pattern_type in (list, dict) and not isinstance(value, pattern_type):
                            return f"参数{param}应为{pattern_type.__name__}类型，得到: {type(value).__name__}"
            
            return None  # 验证通过
            
        except Exception as e:
            logger.warning(f"参数类型验证异常: {e}")
            return None  # 验证异常时不报错，继续执行
    
    def auto_complete_parameters(self, tool_id: str, action: str, 
                               parameters: Dict[str, Any], task_description: str = "") -> Dict[str, Any]:
        """
        自动补齐缺失的必需参数
        
        Args:
            tool_id: 工具ID
            action: 动作名称  
            parameters: 原始参数
            task_description: 任务描述
            
        Returns:
            Dict[str, Any]: 补齐后的参数
        """
        validation_result = self.validate_tool_call(tool_id, action, parameters, task_description)
        
        if validation_result.is_valid:
            return parameters
        
        # 补齐缺失参数
        completed_params = parameters.copy()
        for param, suggestion in validation_result.suggestions.items():
            if param not in completed_params or not completed_params[param]:
                completed_params[param] = suggestion
                logger.info(f"🔧 自动补齐参数 {param}: {suggestion}")
        
        # 🔧 新增：自动修复参数类型错误
        completed_params = self._auto_fix_parameter_types(tool_id, action, completed_params)
        
        return completed_params
    
    def _auto_fix_parameter_types(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """自动修复参数类型错误"""
        fixed_params = parameters.copy()
        
        try:
            if tool_id not in self.tool_schemas or action not in self.tool_schemas[tool_id]:
                return fixed_params
                
            patterns = self.tool_schemas[tool_id][action]["patterns"]
            
            for param, value in fixed_params.items():
                if param in patterns:
                    pattern_value = patterns[param]
                    pattern_type = type(pattern_value)
                    
                    # 尝试自动类型转换
                    if not isinstance(value, pattern_type):
                        try:
                            if pattern_type == int:
                                fixed_params[param] = int(value)
                                logger.info(f"🔧 自动转换参数类型 {param}: {value} -> {fixed_params[param]} (int)")
                            elif pattern_type == float:
                                fixed_params[param] = float(value)
                                logger.info(f"🔧 自动转换参数类型 {param}: {value} -> {fixed_params[param]} (float)")
                            elif pattern_type == str and not isinstance(value, str):
                                fixed_params[param] = str(value)
                                logger.info(f"🔧 自动转换参数类型 {param}: {value} -> {fixed_params[param]} (str)")
                            elif pattern_type == bool and isinstance(value, str):
                                fixed_params[param] = value.lower() in ('true', '1', 'yes', 'on')
                                logger.info(f"🔧 自动转换参数类型 {param}: {value} -> {fixed_params[param]} (bool)")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"⚠️ 无法自动转换参数类型 {param}: {value} -> {pattern_type.__name__}: {e}")
            
            return fixed_params
            
        except Exception as e:
            logger.error(f"❌ 自动修复参数类型失败: {e}")
            return parameters
    
    def get_valid_actions(self, tool_id: str) -> List[str]:
        """获取工具的有效动作列表"""
        if tool_id in self.tool_schemas:
            return list(self.tool_schemas[tool_id].keys())
        return []
    
    def get_parameter_schema(self, tool_id: str, action: str) -> Optional[Dict[str, Any]]:
        """获取特定动作的参数模式"""
        if tool_id in self.tool_schemas and action in self.tool_schemas[tool_id]:
            return self.tool_schemas[tool_id][action]
        return None
    
    # 🔧 P0-2&P1-1强化：配置化别名系统和异步安全校验
    def _load_alias_config(self):
        """加载外部别名配置"""
        try:
            if self._alias_config_path.exists():
                with open(self._alias_config_path, 'r', encoding='utf-8') as f:
                    alias_config = yaml.safe_load(f)
                    
                self.parameter_aliases = alias_config.get('parameter_aliases', {})
                self.action_aliases = alias_config.get('action_aliases', {})
                self.tool_alternatives = alias_config.get('tool_alternatives', {})
                self.error_corrections = alias_config.get('error_corrections', {})
                self.smart_suggestions = alias_config.get('smart_suggestions', {})
                
                logger.info(f"✅ 加载别名配置: {len(self.parameter_aliases)}个工具参数映射, {len(self.action_aliases)}个动作映射")
            else:
                logger.warning(f"⚠️ 别名配置文件不存在: {self._alias_config_path}")
                self._setup_default_aliases()
        except Exception as e:
            logger.error(f"❌ 别名配置加载失败: {e}")
            self._setup_default_aliases()
    
    def _setup_default_aliases(self):
        """设置默认别名配置"""
        self.parameter_aliases = {
            'deepsearch': {'query': 'question'},
            'browser_use': {'link': 'url'},
            'microsandbox': {'script': 'code'}
        }
        self.action_aliases = {
            'browser_use': {'navigate_to_url': 'browser_navigate'}
        }
        self.tool_alternatives = {}
        self.error_corrections = {}
        self.smart_suggestions = {}
    
    def apply_aliases_and_normalize(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
        """应用别名并标准化工具调用"""
        try:
            # 🔄 工具别名映射
            normalized_tool_id = self.tool_alternatives.get(tool_id, tool_id)
            if normalized_tool_id != tool_id:
                logger.debug(f"🔧 工具别名映射: {tool_id} -> {normalized_tool_id}")
            
            # 🔄 动作别名映射
            normalized_action = action
            if normalized_tool_id in self.action_aliases:
                normalized_action = self.action_aliases[normalized_tool_id].get(action, action)
                if normalized_action != action:
                    logger.debug(f"🔧 动作别名映射: {action} -> {normalized_action}")
            
            # 🔄 参数别名映射
            normalized_params = parameters.copy()
            if normalized_tool_id in self.parameter_aliases:
                aliases = self.parameter_aliases[normalized_tool_id]
                for alias, canonical in aliases.items():
                    if alias in normalized_params and canonical not in normalized_params:
                        normalized_params[canonical] = normalized_params.pop(alias)
                        logger.debug(f"🔧 参数别名映射: {alias} -> {canonical}")
            
            return normalized_tool_id, normalized_action, normalized_params
            
        except Exception as e:
            logger.error(f"❌ 别名标准化失败: {e}")
            return tool_id, action, parameters
    
    async def validate_tool_call_async(self, tool_id: str, action: str, 
                                     parameters: Dict[str, Any], 
                                     task_description: str = "") -> ValidationResult:
        """异步版本的工具调用校验，支持实时Schema检查"""
        logger.debug(f"🔍 异步校验: {tool_id}.{action}")
        
        # 🔄 应用别名标准化
        normalized_tool_id, normalized_action, normalized_params = self.apply_aliases_and_normalize(
            tool_id, action, parameters
        )
        
        # 🚫 P0-3强化：智能空动作检查 + 工具下线机制
        if normalized_tool_id not in self.tool_schemas:
            # 工具不存在，触发动态发现
            discovery_result = await self._try_discover_tool(normalized_tool_id)
            if not discovery_result:
                alternative_tools = self._suggest_alternative_tools(normalized_tool_id)
                return ValidationResult(
                    is_valid=False,
                    missing_required=[],
                    invalid_params=[],
                    suggestions={
                        "tool_discovery_failed": True,
                        "suggested_tools": alternative_tools,
                        "original_tool": normalized_tool_id
                    },
                    error_message=f"工具 {normalized_tool_id} 不存在且无法动态发现。建议工具: {alternative_tools}"
                )
        
        available_actions = list(self.tool_schemas[normalized_tool_id].keys()) if normalized_tool_id in self.tool_schemas else []
        
        if not available_actions:
            # 🔄 暂时下线工具，通知Runtime
            await self._mark_tool_temporarily_offline(normalized_tool_id)
            alternative_tools = self._suggest_alternative_tools(normalized_tool_id)
            
            return ValidationResult(
                is_valid=False,
                missing_required=[],
                invalid_params=[],
                suggestions={
                    "tool_offline": True,
                    "retry_after_seconds": 300,  # 5分钟后重试
                    "alternative_tools": alternative_tools,
                    "offline_reason": "no_available_actions"
                },
                error_message=f"工具 {normalized_tool_id} 暂无可用动作，已临时下线。建议替代工具: {alternative_tools}"
            )
        
        # 🔄 轻量级Schema检查：优先使用本地缓存
        async with self._schema_cache_lock:
            current_time = time.time()
            if current_time - self._last_schema_check > 300:  # 5分钟检查一次
                await self._update_schema_cache()
                self._last_schema_check = current_time
        
        # 📋 基础校验（使用缓存）
        basic_result = self._validate_with_cache(normalized_tool_id, normalized_action, normalized_params, task_description)
        
        if not basic_result.is_valid and "不支持动作" in basic_result.error_message:
            # 🚨 动作无效时进行实时验证和智能建议
            try:
                suggested_action = await self._suggest_correct_action(normalized_tool_id, normalized_action)
                if suggested_action and suggested_action != normalized_action:
                    return ValidationResult(
                        is_valid=False,
                        missing_required=[],
                        invalid_params=[],
                        suggestions={
                            "corrected_action": suggested_action,
                            "original_action": normalized_action,
                            "corrected_tool": normalized_tool_id,
                            "available_actions": available_actions
                        },
                        error_message=f"动作 '{normalized_action}' 不支持。建议使用: {suggested_action}"
                    )
            except Exception as e:
                logger.warning(f"⚠️ 智能动作建议失败: {e}")
        
        return basic_result
    
    def _validate_with_cache(self, tool_id: str, action: str, parameters: Dict[str, Any], task_description: str) -> ValidationResult:
        """使用缓存进行基础校验"""
        # 这里复用原有的validate_tool_call逻辑，但使用标准化后的参数
        return self.validate_tool_call(tool_id, action, parameters, task_description)
    
    async def _update_schema_cache(self):
        """更新Schema缓存"""
        try:
            # 这里可以从ToolSchemaManager获取最新的Schema
            from core.tool_schema_manager import get_tool_schema_manager
            schema_manager = get_tool_schema_manager()
            
            live_schemas = await asyncio.wait_for(
                schema_manager.get_live_tool_schemas(force_refresh=False), 
                timeout=5.0
            )
            
            # 更新本地tool_schemas
            for tool_id, schema in live_schemas.items():
                if tool_id not in self.tool_schemas:
                    self.tool_schemas[tool_id] = {}
                
                for action_name, action_info in schema.actions.items():
                    self.tool_schemas[tool_id][action_name] = {
                        "required": self._extract_required_params(action_info),
                        "optional": self._extract_optional_params(action_info),
                        "patterns": self._extract_param_patterns(action_info)
                    }
            
            logger.debug(f"🔄 Schema缓存已更新: {len(live_schemas)} 个工具")
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ Schema缓存更新超时")
        except Exception as e:
            logger.error(f"❌ Schema缓存更新失败: {e}")
    
    def _extract_required_params(self, action_info: Dict) -> List[str]:
        """从动作信息中提取必需参数"""
        params = action_info.get('params', {})
        required = []
        for param, info in params.items():
            if '必需' in str(info) or 'required' in str(info).lower():
                required.append(param)
        return required
    
    def _extract_optional_params(self, action_info: Dict) -> List[str]:
        """从动作信息中提取可选参数"""
        params = action_info.get('params', {})
        optional = []
        for param, info in params.items():
            if '可选' in str(info) or 'optional' in str(info).lower():
                optional.append(param)
        return optional
    
    def _extract_param_patterns(self, action_info: Dict) -> Dict[str, Any]:
        """从动作信息中提取参数模式"""
        return action_info.get('example', {})
    
    async def _suggest_correct_action(self, tool_id: str, incorrect_action: str) -> Optional[str]:
        """智能建议正确的动作"""
        try:
            # 从实时Schema获取可用动作
            from core.tool_schema_manager import get_tool_schema_manager
            schema_manager = get_tool_schema_manager()
            
            tool_schema = await asyncio.wait_for(
                schema_manager.get_tool_schema(tool_id), 
                timeout=3.0
            )
            
            if tool_schema and tool_schema.actions:
                available_actions = list(tool_schema.actions.keys())
                
                # 使用编辑距离找到最相似的动作
                best_action = self._find_most_similar_action(incorrect_action, available_actions)
                logger.debug(f"🔧 为 {incorrect_action} 建议动作: {best_action}")
                return best_action
            
            return None
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ 动作建议查询超时: {tool_id}")
            return None
        except Exception as e:
            logger.error(f"❌ 动作建议失败: {e}")
            return None
    
    def _find_most_similar_action(self, target_action: str, available_actions: List[str]) -> Optional[str]:
        """使用编辑距离查找最相似动作"""
        def edit_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return edit_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)
            
            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            
            return previous_row[-1]
        
        if not available_actions:
            return None
            
        best_action = available_actions[0]
        min_distance = edit_distance(target_action.lower(), best_action.lower())
        
        for action in available_actions[1:]:
            distance = edit_distance(target_action.lower(), action.lower())
            if distance < min_distance:
                min_distance = distance
                best_action = action
        
        # 只有相似度足够高才返回建议（编辑距离小于字符串长度的一半）
        max_allowed_distance = max(len(target_action), len(best_action)) // 2
        if min_distance <= max_allowed_distance:
            return best_action
        
        return None
    
    # 📊 保持同步接口兼容性
    def validate_tool_call_with_async(self, tool_id: str, action: str, parameters: Dict[str, Any], 
                                    task_description: str = "") -> ValidationResult:
        """同步接口，内部调用异步版本"""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.validate_tool_call_async(tool_id, action, parameters, task_description)
            )
        except Exception as e:
            logger.warning(f"⚠️ 异步校验失败，降级到基础校验: {e}")
            # 降级到基础校验
            normalized_tool_id, normalized_action, normalized_params = self.apply_aliases_and_normalize(
                tool_id, action, parameters
            )
            return self._validate_with_cache(normalized_tool_id, normalized_action, normalized_params, task_description)
    
    # 🔧 P0-3强化：工具发现和下线管理
    async def _try_discover_tool(self, tool_id: str) -> bool:
        """尝试动态发现工具"""
        try:
            logger.info(f"🔍 尝试动态发现工具: {tool_id}")
            
            # 从ToolSchemaManager获取最新工具列表
            from core.tool_schema_manager import get_tool_schema_manager
            schema_manager = get_tool_schema_manager()
            
            # 强制刷新并查找工具
            live_schemas = await asyncio.wait_for(
                schema_manager.get_live_tool_schemas(force_refresh=True), 
                timeout=10.0
            )
            
            if tool_id in live_schemas:
                # 发现工具，更新本地schema
                schema = live_schemas[tool_id]
                self.tool_schemas[tool_id] = {}
                
                for action_name, action_info in schema.actions.items():
                    self.tool_schemas[tool_id][action_name] = {
                        "required": self._extract_required_params(action_info),
                        "optional": self._extract_optional_params(action_info),
                        "patterns": self._extract_param_patterns(action_info)
                    }
                
                logger.info(f"✅ 成功发现工具: {tool_id}, 动作: {list(schema.actions.keys())}")
                return True
            
            logger.warning(f"⚠️ 未发现工具: {tool_id}")
            return False
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ 工具发现超时: {tool_id}")
            return False
        except Exception as e:
            logger.error(f"❌ 工具发现异常 {tool_id}: {e}")
            return False
    
    def _suggest_alternative_tools(self, tool_id: str) -> List[str]:
        """基于工具ID建议替代工具"""
        alternatives = []
        
        # 从配置中获取替代建议
        if hasattr(self, 'tool_alternatives'):
            for alt_key, alt_tool in self.tool_alternatives.items():
                if alt_key.lower() in tool_id.lower() or tool_id.lower() in alt_key.lower():
                    alternatives.append(alt_tool)
        
        # 基于关键词的智能建议
        tool_id_lower = tool_id.lower()
        
        if 'browser' in tool_id_lower or 'web' in tool_id_lower or 'navigate' in tool_id_lower:
            alternatives.append('browser_use')
        
        if 'code' in tool_id_lower or 'python' in tool_id_lower or 'sandbox' in tool_id_lower:
            alternatives.append('microsandbox')
        
        if 'search' in tool_id_lower or 'research' in tool_id_lower:
            if 'file' in tool_id_lower or 'code' in tool_id_lower:
                alternatives.append('mcp-search-tool')
            else:
                alternatives.append('deepsearch')
        
        # 去重并返回
        return list(set(alternatives))
    
    async def _mark_tool_temporarily_offline(self, tool_id: str):
        """标记工具临时下线"""
        try:
            from datetime import datetime, timedelta
            
            # 记录下线事件
            offline_event = {
                "tool_id": tool_id,
                "timestamp": datetime.now().isoformat(),
                "reason": "empty_actions",
                "auto_retry_at": (datetime.now() + timedelta(minutes=5)).isoformat(),
                "retry_count": getattr(self, f'_retry_count_{tool_id}', 0) + 1
            }
            
            # 更新重试计数
            setattr(self, f'_retry_count_{tool_id}', offline_event["retry_count"])
            
            # 记录到内存缓存（生产环境可以存储到Redis）
            if not hasattr(self, '_offline_tools'):
                self._offline_tools = {}
            
            self._offline_tools[tool_id] = offline_event
            
            logger.warning(f"🔴 工具 {tool_id} 已临时下线 (第{offline_event['retry_count']}次): {offline_event}")
            
            # 通知工具管理器（如果存在）
            try:
                from core.tool_schema_manager import get_tool_schema_manager
                schema_manager = get_tool_schema_manager()
                if hasattr(schema_manager, 'mark_tool_offline'):
                    await schema_manager.mark_tool_offline(tool_id, reason="no_available_actions")
            except Exception as e:
                logger.debug(f"通知工具管理器失败: {e}")
            
        except Exception as e:
            logger.error(f"❌ 标记工具下线失败 {tool_id}: {e}")
    
    def is_tool_offline(self, tool_id: str) -> bool:
        """检查工具是否处于下线状态"""
        if not hasattr(self, '_offline_tools'):
            return False
        
        if tool_id not in self._offline_tools:
            return False
        
        try:
            from datetime import datetime
            offline_info = self._offline_tools[tool_id]
            retry_time = datetime.fromisoformat(offline_info["auto_retry_at"])
            
            if datetime.now() >= retry_time:
                # 下线时间已过，移除下线状态
                del self._offline_tools[tool_id]
                logger.info(f"🟢 工具 {tool_id} 下线期已过，恢复可用状态")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 检查工具下线状态失败 {tool_id}: {e}")
            return False
    
    def get_offline_tools_info(self) -> Dict[str, Any]:
        """获取当前下线工具信息"""
        if not hasattr(self, '_offline_tools'):
            return {}
        
        return self._offline_tools.copy()

# 全局实例
_parameter_validator = None

def get_parameter_validator() -> ParameterValidator:
    """获取全局参数校验器实例"""
    global _parameter_validator
    if _parameter_validator is None:
        _parameter_validator = ParameterValidator()
    return _parameter_validator