#!/usr/bin/env python3
"""
系统健康检查脚本 - 验证修复后的系统状态
"""

import subprocess
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_port(port: int) -> bool:
    """检查端口是否被占用"""
    try:
        result = subprocess.run(["lsof", "-i", f":{port}"], 
                              capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        return False

def check_file_modifications():
    """检查关键文件是否已修复"""
    project_root = Path(__file__).parent.parent
    
    checks = {}
    
    # 检查推理提示构建器
    reasoning_prompt_path = project_root / "core" / "llm" / "prompt_builders" / "reasoning_prompt_builder.py"
    if reasoning_prompt_path.exists():
        content = reasoning_prompt_path.read_text(encoding='utf-8')
        checks["reasoning_prompt_parameters"] = "必需参数检查" in content
    
    # 检查Web提示构建器
    web_prompt_path = project_root / "core" / "llm" / "prompt_builders" / "web_prompt_builder.py"
    if web_prompt_path.exists():
        content = web_prompt_path.read_text(encoding='utf-8')
        checks["web_prompt_duplicates"] = "不要重复导航" in content
    
    # 检查Guardrails中间件
    guardrails_path = project_root / "core" / "llm" / "guardrails_middleware.py"
    if guardrails_path.exists():
        content = guardrails_path.read_text(encoding='utf-8')
        checks["guardrails_llm_client"] = "llm_client" in content
    
    return checks

def test_json_parsing():
    """测试JSON解析功能"""
    try:
        # 导入项目模块
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        from core.llm.response_parsers.reasoning_response_parser import ReasoningResponseParser
        
        parser = ReasoningResponseParser()
        
        # 测试markdown包装的JSON
        test_response = '''```json
{
    "thinking": "需要研究Python相关内容",
    "action": "research", 
    "tool_id": "deepsearch",
    "parameters": {
        "question": "Python基础知识"
    }
}
```'''
        
        result = parser.parse_response(test_response)
        
        # 验证解析结果
        return (result.get("action") == "research" and 
                result.get("tool_id") == "deepsearch" and
                "question" in result.get("parameters", {}))
        
    except Exception as e:
        logger.error(f"JSON解析测试失败: {e}")
        return False

def main():
    """主检查函数"""
    logger.info("🔍 开始系统健康检查...")
    
    health_report = {
        "timestamp": "2025-06-26",
        "mcp_services": {},
        "code_fixes": {},
        "functionality_tests": {},
        "overall_health": False
    }
    
    # 1. 检查MCP服务端口
    logger.info("1️⃣ 检查MCP服务端口...")
    services = {
        "deepsearch": 8086,
        "microsandbox": 8090,
        "browser_use": 8084,
        "search_tool": 8080
    }
    
    active_services = 0
    for service, port in services.items():
        is_active = check_port(port)
        health_report["mcp_services"][service] = {
            "port": port,
            "active": is_active
        }
        if is_active:
            active_services += 1
        
        status = "✅" if is_active else "❌"
        logger.info(f"  {service} (端口{port}): {status}")
    
    # 2. 检查代码修复
    logger.info("2️⃣ 检查代码修复...")
    code_fixes = check_file_modifications()
    health_report["code_fixes"] = code_fixes
    
    for fix_name, fixed in code_fixes.items():
        status = "✅" if fixed else "❌"
        logger.info(f"  {fix_name}: {status}")
    
    # 3. 功能测试
    logger.info("3️⃣ 功能测试...")
    json_test = test_json_parsing()
    health_report["functionality_tests"]["json_parsing"] = json_test
    
    status = "✅" if json_test else "❌"
    logger.info(f"  JSON解析测试: {status}")
    
    # 4. 计算整体健康状态
    service_health = active_services / len(services)
    code_health = sum(code_fixes.values()) / max(len(code_fixes), 1)
    func_health = 1.0 if json_test else 0.0
    
    overall_health = (service_health + code_health + func_health) / 3
    health_report["overall_health"] = overall_health >= 0.75
    
    # 输出结果
    logger.info(f"\\n📊 健康检查结果:")
    logger.info(f"  MCP服务: {active_services}/{len(services)} 活跃")
    logger.info(f"  代码修复: {sum(code_fixes.values())}/{len(code_fixes)} 完成")
    logger.info(f"  功能测试: {'通过' if json_test else '失败'}")
    logger.info(f"  整体健康度: {overall_health:.1%}")
    
    if health_report["overall_health"]:
        logger.info("🎉 系统健康状态良好！")
        logger.info("💡 可以继续进行任务测试")
    else:
        logger.warning("⚠️ 系统仍有问题需要解决")
        
        # 提供具体建议
        if active_services < len(services):
            logger.info("建议: 运行 python3 scripts/start_mcp_services.py 启动服务")
        
        failed_fixes = [name for name, fixed in code_fixes.items() if not fixed]
        if failed_fixes:
            logger.info(f"建议: 检查以下修复: {failed_fixes}")
    
    # 保存报告
    report_path = Path(__file__).parent.parent / "output" / "system_health_report.json"
    report_path.parent.mkdir(exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(health_report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"📄 健康报告已保存: {report_path}")
    
    return health_report["overall_health"]

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)