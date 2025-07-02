# -*- coding: utf-8 -*-
"""
V4 工具输出处理器
根据每个MCP Server的I/O规范，提供专门的输出格式化处理
"""

import json
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ToolOutputProcessor:
    """V4规范的工具输出统一处理器"""

    def __init__(self):
        self.server_processors = {
            'microsandbox_server': MicrosandboxOutputProcessor(),
            'browser_use_server': BrowserOutputProcessor(),
            'deepsearch_server': DeepsearchOutputProcessor(),
            'search_tool_server': SearchOutputProcessor()
        }

    def process_output(self, server: str, tool: str, result_obj: Any) -> str:
        """
        处理工具输出，返回V4规范的干净结果

        Args:
            server: 服务器名称
            tool: 工具名称
            result_obj: 原始结果对象

        Returns:
            符合V4规范的处理后输出字符串
        """
        # 1. 处理顶层异常
        if isinstance(result_obj, Exception):
            return f"Error calling tool '{tool}' on server '{server}': {result_obj}"

        # 2. 处理结构化错误响应
        if isinstance(result_obj, dict):
            if not result_obj.get('success', True):
                error_msg = result_obj.get('error_message', result_obj.get('error', 'Unknown error'))
                details = result_obj.get('error_details') or result_obj.get('data')
                if details:
                    # 美化字典和列表的输出
                    if isinstance(details, (dict, list)):
                        details_str = json.dumps(details, indent=2, ensure_ascii=False)
                        return f"Error: {error_msg}\nDetails:\n{details_str}"
                    return f"Error: {error_msg}\nDetails: {details}"
                return f"Error: {error_msg}"

        # 3. 分发给专门的处理器进行成功结果处理
        processor = self.server_processors.get(server)
        if processor:
            try:
                return processor.process(tool, result_obj)
            except Exception as e:
                logger.error(f"Error processing output for {server}/{tool}: {e}", exc_info=True)
                return f"Error processing tool output: {e}"
        else:
            logger.warning(f"未找到服务器 '{server}' 的专门处理器，使用默认处理")
            # 默认处理：尝试提取 'data' 字段或直接转为字符串
            if isinstance(result_obj, dict) and 'data' in result_obj:
                return self.format_data(result_obj['data'])
            return str(result_obj)

    def format_data(self, data: Any) -> str:
        """通用格式化工具，用于将任意数据结构转换为可读字符串"""
        if isinstance(data, (dict, list)):
            return json.dumps(data, indent=2, ensure_ascii=False)
        return str(data)

    def escape_xml_content(self, content: str) -> str:
        """
        V4规范的XML内容转义
        确保内容不含任何子标签，便于模型直接解析
        """
        if not isinstance(content, str):
            content = str(content)

        # 基本XML转义
        content = content.replace('&', '&amp;')
        content = content.replace('<', '&lt;')
        content = content.replace('>', '&gt;')
        content = content.replace('"', '&quot;')
        content = content.replace("'", '&apos;')

        return content.strip()


class MicrosandboxOutputProcessor:
    """microsandbox_server 输出处理器"""

    def process(self, tool: str, result_obj: Any) -> str:
        """根据V4规范处理microsandbox工具输出"""
        # 从结果中提取核心数据
        data = result_obj.get('data', result_obj)

        tool_map = {
            'microsandbox_execute': self._process_execute,
            'microsandbox_install_package': self._process_install_package,
            'microsandbox_list_sessions': self._process_list_sessions,
            'microsandbox_close_session': self._process_generic_success_message,
            'microsandbox_cleanup_expired': self._process_cleanup_expired,
            'microsandbox_get_performance_stats': self._process_get_performance_stats,
            'microsandbox_get_health_status': self._process_get_health_status,
        }

        handler = tool_map.get(tool)
        if handler:
            return handler(data)
        else:
            logger.warning(f"microsandbox_server 未知工具: {tool}, 使用通用格式化")
            return ToolOutputProcessor().format_data(data)

    def _process_execute(self, data: Dict) -> str:
        """
        V4规范: 返回代码的stdout
        成功: 返回stdout内容
        失败: 返回stderr或错误信息 (已由主处理器处理)
        超时: 返回明确的超时错误
        """
        stderr = data.get('stderr', '')
        if 'timeout' in str(stderr).lower():
            return f"Execution timed out after {data.get('timeout_used', 'N/A')} seconds."
        
        stdout = data.get('stdout', '')
        # 如果stdout为空但有stderr，也返回stderr
        return str(stdout) if stdout else str(stderr)

    def _process_install_package(self, data: Dict) -> str:
        """
        V4规范: 返回简洁的成功或失败信息
        """
        # 检查增强的安装结果
        install_details = data.get('install_details', {})
        if install_details:
            package_name = install_details.get('package_name', data.get('package_name', 'package'))
            if install_details.get('install_success') and install_details.get('import_success'):
                return f"Package '{package_name}' installed and verified successfully."
            else:
                error = install_details.get('pip_stderr', 'Installation failed')
                return f"ERROR: Failed to install package '{package_name}'. Details: {error}"

        # 降级到旧版逻辑
        package_name = data.get('package_name', 'package')
        # 假设成功（因为错误已在主处理器处理）
        return f"Package '{package_name}' installed successfully."

    def _process_list_sessions(self, data: Dict) -> str:
        sessions = data.get('sessions', [])
        if not sessions:
            return "No active sessions found."
        
        report = f"Found {len(sessions)} active sessions:\n"
        for s in sessions:
            report += f"- Session ID: {s.get('session_id')}, Type: {s.get('type', 'N/A')}, Executions: {s.get('execution_count', 0)}\n"
        return report.strip()

    def _process_generic_success_message(self, data: Dict) -> str:
        return data.get('message', 'Operation completed successfully.')

    def _process_cleanup_expired(self, data: Dict) -> str:
        count = data.get('count', 0)
        if count > 0:
            return f"Cleaned up {count} expired sessions."
        else:
            return "No expired sessions to clean up."

    def _process_get_performance_stats(self, data: Dict) -> str:
        stats = data.get('performance_stats', {})
        return f"Performance Stats: {json.dumps(stats, indent=2, ensure_ascii=False)}"

    def _process_get_health_status(self, data: Dict) -> str:
        status = data.get('status', 'unknown').upper()
        issues = data.get('issues', [])
        report = f"Health Status: {status}\n"
        if issues:
            report += "Issues found:\n"
            for issue in issues:
                report += f"- {issue}\n"
        else:
            report += "No issues found.\n"
        return report.strip()


class BrowserOutputProcessor:
    """browser_use_server 输出处理器"""

    def process(self, tool: str, result_obj: Any) -> str:
        """根据V4规范处理browser工具输出"""
        data = result_obj.get('data', result_obj)

        # 简化工具名称以进行映射
        simple_tool = tool.replace('browser_', '').replace('use_', '')

        tool_map = {
            'navigate': self._process_navigate,
            'extract_content': self._process_extract_content,
            'get_page_info': self._process_get_page_info,
            'get_current_url': self._process_get_current_url,
            'screenshot': self._process_screenshot,
            'execute_task': self._process_execute_task,
        }

        handler = tool_map.get(simple_tool)
        if handler:
            return handler(data)
        else:
            # 多数其他操作返回相似的结构
            return self._process_generic_action(data)

    def _process_navigate(self, data: Dict) -> str:
        """
        V4规范: 返回操作后的页面状态
        """
        url = data.get('current_url', data.get('url', 'unknown'))
        title = data.get('page_title', 'Unknown')
        return f"Navigated to {url}. Page title: {title}."

    def _process_extract_content(self, data: Dict) -> str:
        """
        V4规范: 返回提取到的、经过清洗和总结的内容
        """
        content = data.get('content', '')
        title = data.get('title', '')
        if title and title in content:
             return f"Extracted content:\n{content}"
        return f"Extracted content from page '{title}':\n{content}"

    def _process_generic_action(self, data: Dict) -> str:
        """处理通用的、返回简单内容或消息的动作"""
        content = data.get('content', data.get('message', ''))
        if content:
            return str(content)
        # 如果没有直接内容，格式化整个data字典
        return ToolOutputProcessor().format_data(data)

    def _process_get_page_info(self, data: Dict) -> str:
        return f"Current page: {data.get('title')} at {data.get('url')}"

    def _process_get_current_url(self, data: Dict) -> str:
        return f"Current URL: {data.get('url')}"

    def _process_screenshot(self, data: Dict) -> str:
        return data.get('message', f"Screenshot saved to {data.get('filename')}")

    def _process_execute_task(self, data: Dict) -> str:
        return f"AI task '{data.get('task')}' completed. Result: {data.get('result')}"


class DeepsearchOutputProcessor:
    """deepsearch_server 输出处理器"""

    def process(self, tool: str, result_obj: Any) -> str:
        """根据V4规范处理deepsearch工具输出"""
        data = result_obj.get('data', result_obj)
        
        # 所有研究类工具都返回相似的报告结构
        if tool in ['research', 'quick_research', 'comprehensive_research']:
            return self._process_research(data)
        
        # 其他工具，如健康检查
        return ToolOutputProcessor().format_data(data)

    def _process_research(self, data: Dict) -> str:
        """
        V4规范: 提供最终的、经过提炼的研究报告
        """
        # 新的结构将最终答案放在 'answer' 字段
        report = data.get('answer')
        if report:
            # 同时附上来源信息，这对模型很有用
            sources = data.get('sources', [])
            if sources:
                source_links = [f"[{s.get('title', 'Source')}]({s.get('url')})" for s in sources if s.get('url')]
                if source_links:
                    report += "\n\n**Sources:**\n- " + "\n- ".join(source_links)
            return str(report)
        else:
            # 兼容旧版输出
            legacy_report = (data.get('final_report') or
                             data.get('report') or
                             data.get('summary') or
                             data.get('output') or
                             data.get('content'))
            if legacy_report:
                return str(legacy_report)

        return "Research completed but no report content found."


class SearchOutputProcessor:
    """search_tool_server 输出处理器"""

    def process(self, tool: str, result_obj: Any) -> str:
        """根据V4规范处理search工具输出"""
        data = result_obj.get('data', result_obj)

        tool_map = {
            'search_file_content': self._process_search_file_content,
            'list_code_definitions': self._process_list_code_definitions,
            'analyze_tool_needs': self._process_analyze_tool_needs,
            'search_and_install_tools': self._process_search_and_install_tools,
        }
        
        handler = tool_map.get(tool)
        if handler:
            return handler(data)
        else:
            logger.warning(f"search_tool_server 未知工具: {tool}, 使用通用格式化")
            return ToolOutputProcessor().format_data(data)

    def _process_search_file_content(self, data: Dict) -> str:
        """
        V4规范: 返回格式化的匹配结果
        """
        # file_path 在顶层参数中，但为了健壮性也检查data
        file_path = data.get('file_path', 'unknown file')
        matches = data.get('matches', [])

        if matches:
            match_strs = [str(match) for match in matches]
            return f"Found {len(matches)} matches in '{file_path}':\n" + "\n".join(match_strs)
        else:
            return f"No matches found in '{file_path}'."

    def _process_list_code_definitions(self, data: Dict) -> str:
        """处理代码定义列表输出"""
        definitions = data.get('definitions', [])
        if definitions:
            def_strs = [f"- {d.get('type', 'def')} `{d.get('name', 'unknown')}` at {d.get('file')}:{d.get('line')}" for d in definitions]
            return f"Found {len(definitions)} code definitions:\n" + "\n".join(def_strs)
        else:
            return "No code definitions found."

    def _process_analyze_tool_needs(self, data: Dict) -> str:
        """处理工具需求分析结果"""
        if data.get('needs_new_tools'):
            return f"Analysis: New tools are needed. {data.get('analysis')}\nRecommendations: {', '.join(data.get('recommendations', []))}"
        else:
            return f"Analysis: Existing tools are sufficient. {data.get('analysis')}"

    def _process_search_and_install_tools(self, data: Dict) -> str:
        """处理工具搜索和安装结果"""
        summary = data.get('installation_summary', 'No tools were installed.')
        installed_tools = data.get('installed_tools', [])
        if installed_tools:
            tools_str = [t.get('tool_name', 'unknown tool') for t in installed_tools]
            return f"{summary}. Installed: {', '.join(tools_str)}"
        return summary
