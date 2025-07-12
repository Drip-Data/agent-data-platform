#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工具输出格式化器
专门处理各种MCP工具的输出结果格式化
"""

import json
import logging
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


class ToolOutputFormatter:
    """工具输出格式化器 - 处理所有MCP工具的输出格式化"""
    
    @staticmethod
    def format_tool_output(service_name: str, tool_name: str, output: Any) -> str:
        """
        统一格式化所有工具的输出结果，使其清晰易读
        
        Args:
            service_name: 服务名称 (microsandbox, deepsearch, browser_use等)
            tool_name: 工具名称
            output: 原始输出结果
            
        Returns:
            str: 格式化后的清晰结果
        """
        # 1. MicroSandbox - 智能提取核心执行结果
        if service_name == 'microsandbox':
            return ToolOutputFormatter._format_microsandbox_output(output)
        
        # 2. DeepSearch - 格式化搜索结果
        elif service_name == 'deepsearch':
            if isinstance(output, dict):
                return ToolOutputFormatter._format_deepsearch_output(output)
            elif isinstance(output, list):
                return ToolOutputFormatter._format_deepsearch_list_output(output)
            return str(output)
        
        # 3. Browser Use - 格式化浏览器操作结果
        elif service_name == 'browser_use':
            if isinstance(output, dict):
                return ToolOutputFormatter._format_browser_use_output(output)
            return str(output)
        
        # 4. Search Tool - 格式化搜索结果
        elif service_name == 'search_tool':
            if isinstance(output, dict):
                return ToolOutputFormatter._format_search_tool_output(output)
            return str(output)
        
        # 5. Memory Staging - 格式化内存暂存结果
        elif service_name == 'memory_staging':
            return ToolOutputFormatter._format_memory_staging_output_generic(tool_name, output)
        
        # 6. 其他工具 - 通用格式化
        else:
            return ToolOutputFormatter._format_generic_output(output)
    
    @staticmethod
    def _format_deepsearch_output(output: dict) -> str:
        """正确处理DeepSearch的实际输出格式，支持JSON字符串和结构化数据"""
        try:
            # 首先处理 DeepSearch 的实际输出格式
            # 检查是否是包含JSON字符串的格式（成功情况）
            if 'query' in output and 'content' in output:
                content = output['content']
                
                # 如果content是JSON字符串，尝试解析
                if isinstance(content, str):
                    try:
                        parsed_content = json.loads(content)
                        # 解析成功，使用解析后的数据
                        return ToolOutputFormatter._extract_deepsearch_content_recursive(parsed_content)
                    except json.JSONDecodeError:
                        # 不是JSON，直接使用字符串内容
                        return ToolOutputFormatter._format_deepsearch_text_content(content)
                
                # 如果content已经是字典或列表，直接处理
                elif isinstance(content, (dict, list)):
                    return ToolOutputFormatter._extract_deepsearch_content_recursive(content)
                else:
                    return str(content)
            
            # 检查是否是错误格式
            elif 'error' in output:
                error_msg = output['error']
                return f"❌ DeepSearch 查询失败: {error_msg}"
            
            # 检查是否直接包含研究结果
            elif 'research_result' in output:
                research_result = output['research_result']
                if isinstance(research_result, dict):
                    return ToolOutputFormatter._format_research_result(research_result)
                else:
                    return str(research_result)
            
            # 检查是否是直接的字符串结果
            elif isinstance(output, dict) and len(output) == 1:
                key, value = next(iter(output.items()))
                if isinstance(value, str) and len(value) > 50:
                    return ToolOutputFormatter._format_deepsearch_text_content(value)
            
            # 其他情况，尝试通用处理
            return ToolOutputFormatter._extract_deepsearch_content_recursive(output)
            
        except Exception as e:
            logger.warning(f"格式化DeepSearch输出时出错: {e}")
            return str(output)
    
    @staticmethod
    def _format_deepsearch_text_content(content: str) -> str:
        """格式化DeepSearch的文本内容"""
        if not content or not isinstance(content, str):
            return str(content)
        
        # 清理内容
        cleaned_content = content.strip()
        
        # 如果内容很短，直接返回
        if len(cleaned_content) < 100:
            return cleaned_content
        
        # 尝试按段落分割
        paragraphs = [p.strip() for p in cleaned_content.split('\n\n') if p.strip()]
        
        if len(paragraphs) > 1:
            # 多段落，格式化显示
            formatted_parts = []
            for i, para in enumerate(paragraphs[:3]):  # 只显示前3段
                if para:
                    formatted_parts.append(f"{para}")
            
            result = '\n\n'.join(formatted_parts)
            if len(paragraphs) > 3:
                result += f"\n\n... (还有 {len(paragraphs) - 3} 段内容)"
            
            return result
        else:
            # 单段落，可能需要截断
            if len(cleaned_content) > 1000:
                return cleaned_content[:1000] + "...\n\n[内容已截断]"
            return cleaned_content
    
    @staticmethod
    def _format_research_result(research_result: dict) -> str:
        """格式化研究结果"""
        try:
            result_parts = []
            
            # 添加标题
            if 'title' in research_result:
                result_parts.append(f"📋 研究主题: {research_result['title']}")
            
            # 添加摘要
            if 'summary' in research_result:
                summary = research_result['summary']
                if len(summary) > 300:
                    summary = summary[:300] + "..."
                result_parts.append(f"📝 摘要: {summary}")
            
            # 添加关键发现
            if 'key_findings' in research_result:
                findings = research_result['key_findings']
                if isinstance(findings, list):
                    result_parts.append("🔍 关键发现:")
                    for i, finding in enumerate(findings[:5], 1):
                        result_parts.append(f"  {i}. {finding}")
                    if len(findings) > 5:
                        result_parts.append(f"  ... (还有 {len(findings) - 5} 项发现)")
            
            # 添加结论
            if 'conclusion' in research_result:
                conclusion = research_result['conclusion']
                if len(conclusion) > 200:
                    conclusion = conclusion[:200] + "..."
                result_parts.append(f"💡 结论: {conclusion}")
            
            return '\n\n'.join(result_parts) if result_parts else str(research_result)
            
        except Exception as e:
            logger.warning(f"格式化研究结果时出错: {e}")
            return str(research_result)
    
    @staticmethod
    def _format_deepsearch_list_output(output: list) -> str:
        """格式化DeepSearch的列表输出"""
        if not output:
            return "🔍 DeepSearch: 无搜索结果"
        
        try:
            result_parts = [f"🔍 DeepSearch 找到 {len(output)} 个结果:"]
            
            for i, item in enumerate(output[:5], 1):  # 只显示前5个结果
                if isinstance(item, dict):
                    title = item.get('title', f'结果 {i}')
                    content = item.get('content', item.get('summary', str(item)))
                    
                    # 截断过长的内容
                    if len(content) > 150:
                        content = content[:150] + "..."
                    
                    result_parts.append(f"\n{i}. **{title}**")
                    result_parts.append(f"   {content}")
                else:
                    content = str(item)
                    if len(content) > 150:
                        content = content[:150] + "..."
                    result_parts.append(f"\n{i}. {content}")
            
            if len(output) > 5:
                result_parts.append(f"\n... (还有 {len(output) - 5} 个结果)")
            
            return '\n'.join(result_parts)
            
        except Exception as e:
            logger.warning(f"格式化DeepSearch列表输出时出错: {e}")
            return f"🔍 DeepSearch: {len(output)} 个结果 (格式化失败)"
    
    @staticmethod
    def _format_browser_use_output(output: dict) -> str:
        """格式化Browser Use输出"""
        try:
            if 'success' in output and not output['success']:
                error_msg = output.get('error', '未知错误')
                return f"❌ 浏览器操作失败: {error_msg}"
            
            # 检查是否有页面信息
            if 'page_info' in output:
                page_info = output['page_info']
                result_parts = ["🌐 浏览器页面信息:"]
                
                if 'title' in page_info:
                    result_parts.append(f"标题: {page_info['title']}")
                if 'url' in page_info:
                    result_parts.append(f"URL: {page_info['url']}")
                if 'content' in page_info:
                    content = page_info['content']
                    if len(content) > 300:
                        content = content[:300] + "..."
                    result_parts.append(f"内容预览: {content}")
                
                return '\n'.join(result_parts)
            
            # 检查是否有搜索结果
            if 'search_results' in output:
                results = output['search_results']
                if isinstance(results, list) and results:
                    result_parts = [f"🔍 找到 {len(results)} 个搜索结果:"]
                    
                    for i, result in enumerate(results[:3], 1):
                        if isinstance(result, dict):
                            title = result.get('title', f'结果 {i}')
                            url = result.get('url', '')
                            snippet = result.get('snippet', result.get('description', ''))
                            
                            result_parts.append(f"\n{i}. **{title}**")
                            if url:
                                result_parts.append(f"   URL: {url}")
                            if snippet:
                                if len(snippet) > 150:
                                    snippet = snippet[:150] + "..."
                                result_parts.append(f"   {snippet}")
                    
                    if len(results) > 3:
                        result_parts.append(f"\n... (还有 {len(results) - 3} 个结果)")
                    
                    return '\n'.join(result_parts)
            
            # 检查是否有提取的内容
            if 'extracted_content' in output:
                content = output['extracted_content']
                if content:
                    if len(content) > 500:
                        content = content[:500] + "..."
                    return f"📄 提取的内容:\n{content}"
            
            # 检查操作结果消息
            if 'message' in output:
                message = output['message']
                status = "✅" if output.get('success', True) else "❌"
                return f"{status} {message}"
            
            # 检查是否有状态信息
            if 'status' in output:
                status_info = output['status']
                return f"🔄 浏览器状态: {status_info}"
            
            # 通用格式化
            if output.get('success', True):
                return "✅ 浏览器操作完成"
            else:
                return str(output)
                
        except Exception as e:
            logger.warning(f"格式化Browser Use输出时出错: {e}")
            return str(output)
    
    @staticmethod
    def _format_search_tool_output(output: dict) -> str:
        """格式化Search Tool输出"""
        try:
            # 检查是否有搜索结果
            if 'results' in output:
                results = output['results']
                query = output.get('query', '未知查询')
                
                if not results:
                    return f"🔍 搜索 '{query}' 无结果"
                
                result_parts = [f"🔍 搜索 '{query}' 找到 {len(results)} 个结果:"]
                
                for i, result in enumerate(results[:5], 1):
                    if isinstance(result, dict):
                        file_path = result.get('file', result.get('path', ''))
                        line_num = result.get('line', '')
                        content = result.get('content', result.get('match', ''))
                        
                        result_parts.append(f"\n{i}. {file_path}")
                        if line_num:
                            result_parts.append(f"   行 {line_num}: {content}")
                        else:
                            if len(content) > 100:
                                content = content[:100] + "..."
                            result_parts.append(f"   {content}")
                    else:
                        content = str(result)
                        if len(content) > 100:
                            content = content[:100] + "..."
                        result_parts.append(f"\n{i}. {content}")
                
                if len(results) > 5:
                    result_parts.append(f"\n... (还有 {len(results) - 5} 个结果)")
                
                return '\n'.join(result_parts)
            
            # 检查代码定义列表
            if 'definitions' in output:
                definitions = output['definitions']
                if not definitions:
                    return "📋 未找到代码定义"
                
                result_parts = [f"📋 找到 {len(definitions)} 个代码定义:"]
                
                for i, defn in enumerate(definitions[:10], 1):
                    if isinstance(defn, dict):
                        name = defn.get('name', '')
                        type_info = defn.get('type', '')
                        file_path = defn.get('file', '')
                        line_num = defn.get('line', '')
                        
                        result_parts.append(f"\n{i}. {type_info} **{name}**")
                        if file_path:
                            location = f"   位置: {file_path}"
                            if line_num:
                                location += f":{line_num}"
                            result_parts.append(location)
                    else:
                        result_parts.append(f"\n{i}. {str(defn)}")
                
                if len(definitions) > 10:
                    result_parts.append(f"\n... (还有 {len(definitions) - 10} 个定义)")
                
                return '\n'.join(result_parts)
            
            # 检查工具需求分析
            if 'analysis' in output:
                analysis = output['analysis']
                if isinstance(analysis, dict):
                    result_parts = ["🔧 工具需求分析:"]
                    
                    if 'recommended_tools' in analysis:
                        tools = analysis['recommended_tools']
                        if tools:
                            result_parts.append(f"推荐工具: {', '.join(tools)}")
                    
                    if 'reasoning' in analysis:
                        reasoning = analysis['reasoning']
                        if len(reasoning) > 200:
                            reasoning = reasoning[:200] + "..."
                        result_parts.append(f"分析: {reasoning}")
                    
                    return '\n'.join(result_parts)
            
            # 通用处理
            if 'message' in output:
                return f"🔧 {output['message']}"
            
            return str(output)
            
        except Exception as e:
            logger.warning(f"格式化Search Tool输出时出错: {e}")
            return str(output)
    
    @staticmethod
    def _format_microsandbox_output(output: Any) -> str:
        """智能格式化MicroSandbox输出，提取核心执行结果"""
        try:
            # 如果是字符串，直接处理
            if isinstance(output, str):
                return ToolOutputFormatter._clean_microsandbox_text(output)
            
            # 如果是字典，提取关键信息
            if isinstance(output, dict):
                # 检查是否有输出字段
                if 'output' in output:
                    result = output['output']
                    if isinstance(result, str):
                        return ToolOutputFormatter._clean_microsandbox_text(result)
                
                # 检查是否有结果字段
                if 'result' in output:
                    result = output['result']
                    return ToolOutputFormatter._clean_microsandbox_text(str(result))
                
                # 检查是否有stdout字段
                if 'stdout' in output:
                    stdout = output['stdout']
                    stderr = output.get('stderr', '')
                    
                    result_parts = []
                    if stdout:
                        result_parts.append(ToolOutputFormatter._clean_microsandbox_text(stdout))
                    if stderr:
                        result_parts.append(f"错误: {stderr}")
                    
                    return '\n'.join(result_parts) if result_parts else "执行完成，无输出"
                
                # 检查是否有错误信息
                if 'error' in output:
                    return f"❌ 执行错误: {output['error']}"
                
                # 检查是否有状态信息
                if 'status' in output:
                    status = output['status']
                    if status == 'success':
                        return "✅ 代码执行成功"
                    elif status == 'error':
                        error_msg = output.get('message', '未知错误')
                        return f"❌ 执行失败: {error_msg}"
                
                # 其他字典格式，尝试提取有用信息
                return str(output)
            
            # 其他类型，直接转换为字符串
            return str(output)
            
        except Exception as e:
            logger.warning(f"格式化MicroSandbox输出时出错: {e}")
            return str(output)
    
    @staticmethod
    def _clean_microsandbox_text(text: str) -> str:
        """清理MicroSandbox的文本输出"""
        if not text:
            return "执行完成，无输出"
        
        # 移除过多的空行
        lines = text.split('\n')
        cleaned_lines = []
        prev_empty = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not prev_empty:
                    cleaned_lines.append('')
                prev_empty = True
            else:
                cleaned_lines.append(line)
                prev_empty = False
        
        # 移除末尾的空行
        while cleaned_lines and not cleaned_lines[-1]:
            cleaned_lines.pop()
        
        result = '\n'.join(cleaned_lines)
        
        # 如果输出过长，进行截断
        if len(result) > 2000:
            result = result[:2000] + "\n\n... [输出已截断]"
        
        return result if result else "执行完成，无输出"
    
    @staticmethod
    def _format_generic_output(output: Any) -> str:
        """通用输出格式化"""
        try:
            if isinstance(output, dict):
                # 检查常见的成功/失败模式
                if 'success' in output:
                    if output['success']:
                        message = output.get('message', output.get('result', '操作成功'))
                        return f"✅ {message}"
                    else:
                        error = output.get('error', output.get('message', '操作失败'))
                        return f"❌ {error}"
                
                # 检查是否有消息字段
                if 'message' in output:
                    return str(output['message'])
                
                # 检查是否有结果字段
                if 'result' in output:
                    return str(output['result'])
                
                # 其他情况，尝试格式化为JSON
                try:
                    return json.dumps(output, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    return str(output)
            
            elif isinstance(output, list):
                if not output:
                    return "无结果"
                elif len(output) == 1:
                    return str(output[0])
                else:
                    return f"返回 {len(output)} 个结果:\n" + '\n'.join(f"{i+1}. {item}" for i, item in enumerate(output[:5]))
            
            else:
                return str(output)
                
        except Exception as e:
            logger.warning(f"通用格式化输出时出错: {e}")
            return str(output)
    
    @staticmethod
    def _format_memory_staging_output_generic(action: str, output: dict) -> str:
        """格式化内存暂存工具输出 - 通用格式化方法"""
        try:
            if not isinstance(output, dict):
                return str(output)
            
            success = output.get("success", False)
            
            if action == "memory_write":
                if success:
                    key = output.get("key", "unknown")
                    data_type = output.get("data_type", "unknown")
                    return f"✅ 数据已保存到暂存区: {key} (类型: {data_type})"
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 保存数据失败: {error}"
            
            elif action == "memory_read":
                if success:
                    key = output.get("key", "unknown")
                    value = output.get("value")
                    data_type = output.get("data_type", "unknown")
                    age = output.get("age_seconds", 0)
                    
                    # 格式化年龄
                    if age < 60:
                        age_str = f"{int(age)}秒前"
                    elif age < 3600:
                        age_str = f"{int(age/60)}分钟前"
                    else:
                        age_str = f"{int(age/3600)}小时前"
                    
                    # 格式化值预览
                    if isinstance(value, (dict, list)):
                        value_preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    else:
                        value_preview = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
                    
                    return f"📖 从暂存区读取: {key}\n类型: {data_type} ({age_str})\n内容: {value_preview}"
                else:
                    error = output.get("error", "Unknown error")
                    available_keys = output.get("available_keys", [])
                    if available_keys:
                        return f"❌ 读取失败: {error}\n可用键名: {', '.join(available_keys)}"
                    else:
                        return f"❌ 读取失败: {error}"
            
            elif action == "memory_list":
                if success:
                    entries = output.get("entries", [])
                    total_count = output.get("total_count", 0)
                    
                    if total_count == 0:
                        return "📋 暂存区为空"
                    
                    result_lines = [f"📋 暂存区内容 ({total_count} 项):"]
                    for entry in entries[:10]:  # 只显示前10项
                        key = entry.get("key", "unknown")
                        data_type = entry.get("data_type", "unknown")
                        age = entry.get("age_seconds", 0)
                        
                        if age < 60:
                            age_str = f"{int(age)}秒前"
                        elif age < 3600:
                            age_str = f"{int(age/60)}分钟前"
                        else:
                            age_str = f"{int(age/3600)}小时前"
                        
                        result_lines.append(f"  - {key} ({data_type}) - {age_str}")
                    
                    if total_count > 10:
                        result_lines.append(f"  ... 还有 {total_count - 10} 项")
                    
                    return "\n".join(result_lines)
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 列表获取失败: {error}"
            
            elif action == "memory_search":
                if success:
                    matches = output.get("matches", [])
                    total_matches = output.get("total_matches", 0)
                    query = output.get("query", "")
                    
                    if total_matches == 0:
                        return f"🔍 搜索 '{query}' 无结果"
                    
                    result_lines = [f"🔍 搜索 '{query}' 找到 {total_matches} 个匹配项:"]
                    for match in matches[:5]:  # 只显示前5个匹配
                        key = match.get("key", "unknown")
                        score = match.get("score", 0)
                        reasons = match.get("match_reasons", [])
                        value_preview = str(match.get("value", ""))[:100] + "..." if len(str(match.get("value", ""))) > 100 else str(match.get("value", ""))
                        
                        result_lines.append(f"  - {key} (分数: {score}, 匹配: {', '.join(reasons)})")
                        result_lines.append(f"    内容: {value_preview}")
                    
                    if total_matches > 5:
                        result_lines.append(f"  ... 还有 {total_matches - 5} 个匹配项")
                    
                    return "\n".join(result_lines)
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 搜索失败: {error}"
            
            elif action == "memory_clear":
                if success:
                    key = output.get("key")
                    if key:
                        return f"🗑️ 已清除暂存数据: {key}"
                    else:
                        cleared_count = output.get("cleared_count", 0)
                        return f"🗑️ 已清空所有暂存数据 ({cleared_count} 项)"
                else:
                    error = output.get("error", "Unknown error")
                    return f"❌ 清除失败: {error}"
            
            else:
                # 未知动作，使用通用格式化
                message = output.get("message", str(output))
                return f"🔄 内存暂存操作 ({action}): {message}"
        
        except Exception as e:
            logger.warning(f"Failed to format memory staging output: {e}")
            return str(output)
    
    @staticmethod
    def _extract_deepsearch_content_recursive(data: Any, max_depth: int = 3) -> str:
        """递归提取DeepSearch内容，支持多层嵌套结构"""
        if max_depth <= 0:
            return str(data)
        
        try:
            if isinstance(data, dict):
                # 优先查找研究相关字段
                content_fields = [
                    'research_result', 'content', 'result', 'answer', 'summary', 
                    'findings', 'conclusion', 'analysis', 'response', 'text', 'data'
                ]
                
                for field in content_fields:
                    if field in data:
                        field_data = data[field]
                        if isinstance(field_data, str) and len(field_data) > 20:
                            # 检查是否是有意义的研究内容
                            if ToolOutputFormatter._is_meaningful_research_content(field_data):
                                return ToolOutputFormatter._format_deepsearch_text_content(field_data)
                        elif isinstance(field_data, (dict, list)):
                            recursive_result = ToolOutputFormatter._extract_deepsearch_content_recursive(field_data, max_depth - 1)
                            if recursive_result and len(recursive_result) > 20:
                                return recursive_result
                
                # 如果没有找到标准字段，尝试处理整个字典
                result_parts = []
                for key, value in data.items():
                    if isinstance(value, str) and len(value) > 50:
                        if ToolOutputFormatter._is_meaningful_research_content(value):
                            result_parts.append(f"**{key}**: {value}")
                    elif isinstance(value, (dict, list)):
                        recursive_result = ToolOutputFormatter._extract_deepsearch_content_recursive(value, max_depth - 1)
                        if recursive_result and len(recursive_result) > 20:
                            result_parts.append(f"**{key}**: {recursive_result}")
                
                if result_parts:
                    return '\n\n'.join(result_parts[:3])  # 最多显示3个部分
                
                # 最后尝试JSON格式
                try:
                    return json.dumps(data, ensure_ascii=False, indent=2)[:1000]
                except (TypeError, ValueError):
                    return str(data)
            
            elif isinstance(data, list):
                if not data:
                    return "无搜索结果"
                
                result_parts = []
                for i, item in enumerate(data[:3]):  # 最多处理前3项
                    if isinstance(item, (dict, list)):
                        recursive_result = ToolOutputFormatter._extract_deepsearch_content_recursive(item, max_depth - 1)
                        if recursive_result:
                            result_parts.append(f"{i+1}. {recursive_result}")
                    elif isinstance(item, str) and len(item) > 20:
                        if ToolOutputFormatter._is_meaningful_research_content(item):
                            result_parts.append(f"{i+1}. {item}")
                
                if result_parts:
                    final_result = '\n\n'.join(result_parts)
                    if len(data) > 3:
                        final_result += f"\n\n... (还有 {len(data) - 3} 项结果)"
                    return final_result
                else:
                    return f"包含 {len(data)} 项结果"
            
            else:
                # 字符串或其他类型
                content = str(data)
                if len(content) > 20 and ToolOutputFormatter._is_meaningful_research_content(content):
                    return ToolOutputFormatter._format_deepsearch_text_content(content)
                else:
                    return content
        
        except Exception as e:
            logger.warning(f"递归提取DeepSearch内容时出错: {e}")
            return str(data)
    
    @staticmethod
    def _is_meaningful_research_content(content: str) -> bool:
        """判断内容是否是有意义的研究内容"""
        if not content or not isinstance(content, str):
            return False
        
        content_lower = content.lower()
        
        # 检查长度
        if len(content) < 30:
            return False
        
        # 检查研究相关指标
        research_indicators = [
            # 中文研究指标
            '研究', '分析', '应用', '技术', '方法', '发展', '趋势', '挑战', '机遇', 
            '算法', '模型', '系统', '框架', '实验', '结果', '结论', '总结',
            '量子', '机器学习', '人工智能', '深度学习', '神经网络',
            # 英文研究指标
            'research', 'analysis', 'application', 'technology', 'method', 'development',
            'trend', 'challenge', 'opportunity', 'algorithm', 'model', 'system', 
            'framework', 'experiment', 'result', 'conclusion', 'summary',
            'quantum', 'machine learning', 'artificial intelligence', 'deep learning',
            'neural network', 'computing', 'optimization'
        ]
        
        # 计算研究相关词汇的出现次数
        research_score = sum(1 for indicator in research_indicators if indicator in content_lower)
        
        # 检查结构化内容指标
        structure_indicators = [
            '1.', '2.', '3.', '一、', '二、', '三、', '首先', '其次', '最后',
            'introduction', 'background', 'methodology', 'approach', 'conclusion',
            '背景', '方法', '结论', '总结'
        ]
        has_structure = any(indicator in content_lower for indicator in structure_indicators)
        
        # 检查技术深度指标
        technical_indicators = [
            'algorithm', 'implementation', 'performance', 'accuracy', 'efficiency',
            'optimization', 'parameter', 'dataset', 'training', 'testing',
            '算法', '实现', '性能', '准确率', '效率', '优化', '参数', '数据集', '训练', '测试'
        ]
        technical_score = sum(1 for indicator in technical_indicators if indicator in content_lower)
        
        # 综合评分判断
        is_meaningful = (
            research_score >= 3 or  # 至少3个研究相关词汇
            (research_score >= 2 and has_structure) or  # 2个研究词汇+结构化
            (research_score >= 2 and technical_score >= 2) or  # 研究词汇+技术词汇
            (len(content) >= 200 and research_score >= 1)  # 长内容+基本研究词汇
        )
        
        logger.debug(f"内容质量评估: 长度={len(content)}, 研究分数={research_score}, "
                    f"技术分数={technical_score}, 有结构={has_structure}, 有意义={is_meaningful}")
        
        return is_meaningful


# 便捷函数
def format_tool_output(service_name: str, tool_name: str, output: Any) -> str:
    """便捷函数：格式化工具输出"""
    return ToolOutputFormatter.format_tool_output(service_name, tool_name, output)