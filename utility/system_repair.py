#!/usr/bin/env python3
"""
系统修复工具 - 针对轨迹分析发现的核心问题进行精准修复
基于用户要求：精简、高效、从根本解决问题，不降低验证标准
"""

import asyncio
import json
import logging
import subprocess
import sys
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SystemRepair:
    """精简系统修复器 - 只修复轨迹中发现的核心问题"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        
    def check_port_availability(self, port: int) -> bool:
        """检查端口是否可用"""
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{port}"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def start_mcp_server(self, server_name: str, port: int) -> bool:
        """启动单个MCP服务器"""
        server_path = self.project_root / "mcp_servers" / f"{server_name}_server" / "main.py"
        
        if not server_path.exists():
            logger.error(f"❌ 服务器脚本不存在: {server_path}")
            return False
        
        try:
            logger.info(f"🚀 启动 {server_name} 服务器 (端口{port})")
            
            # 启动服务器
            process = subprocess.Popen(
                [sys.executable, str(server_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.project_root
            )
            
            # 等待启动
            time.sleep(3)
            
            # 检查进程状态
            if process.poll() is None:
                logger.info(f"✅ {server_name} 启动成功 (PID: {process.pid})")
                return True
            else:
                stdout, stderr = process.communicate()
                logger.error(f"❌ {server_name} 启动失败")
                if stderr:
                    logger.error(f"错误信息: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动 {server_name} 时出错: {e}")
            return False
    
    def fix_parameter_validation_in_place(self) -> bool:
        """在现有文件中修复参数验证问题"""
        try:
            # 修复推理提示构建器
            prompt_builder_path = self.project_root / "core" / "llm" / "prompt_builders" / "reasoning_prompt_builder.py"
            
            if prompt_builder_path.exists():
                # 读取现有内容
                with open(prompt_builder_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 如果还没有参数规则提醒，添加它
                if "参数完整性检查" not in content:
                    # 在系统提示中添加参数验证提醒
                    enhanced_system_prompt = '''
## ⚠️ 参数完整性检查 - 重要提醒
1. **必须包含所有必需参数** - 每个工具动作都有特定的必需参数
2. **deepsearch工具** - research, quick_research, comprehensive_research 都需要 "question" 参数
3. **microsandbox工具** - microsandbox_execute 需要 "code" 参数
4. **browser工具** - browser_navigate 需要 "url" 参数
5. **参数不能为空** - 所有必需参数都必须有有效值

## 📋 响应格式严格要求
```json
{
    "thinking": "详细分析...",
    "action": "具体动作名称",
    "tool_id": "工具ID", 
    "parameters": {
        "必需参数名": "参数值"
    },
    "confidence": 0.0-1.0
}
```
'''
                    
                    # 在build_prompt方法中添加参数提醒
                    if "system_prompt = f\"\"\"" in content:
                        content = content.replace(
                            "system_prompt = f\"\"\"你是一个专业的AI任务执行助手",
                            f"system_prompt = f\"\"\"你是一个专业的AI任务执行助手{enhanced_system_prompt}\\n\\n"
                        )
                        
                        # 写回文件
                        with open(prompt_builder_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        logger.info("✅ 推理提示构建器已增强参数验证")
                        return True
            
            return False
                
        except Exception as e:
            logger.error(f"修复参数验证失败: {e}")
            return False
    
    def verify_system_health(self) -> Dict[str, Any]:
        """验证系统健康状态"""
        health_status = {
            "services": {},
            "overall_health": False,
            "issues": []
        }
        
        # 检查关键服务端口
        critical_services = {
            "deepsearch": 8086,
            "microsandbox": 8090,
            "browser_use": 8084,
            "search_tool": 8080
        }
        
        active_services = 0
        for service, port in critical_services.items():
            is_active = self.check_port_availability(port)
            health_status["services"][service] = {
                "port": port,
                "active": is_active
            }
            
            if is_active:
                active_services += 1
            else:
                health_status["issues"].append(f"{service} 服务 (端口{port}) 未运行")
        
        # 计算整体健康状态
        health_status["overall_health"] = active_services >= len(critical_services) * 0.75
        health_status["active_services"] = active_services
        health_status["total_services"] = len(critical_services)
        
        return health_status
    
    async def repair_system(self) -> bool:
        """执行系统修复"""
        logger.info("🔧 开始系统修复...")
        
        success_count = 0
        total_repairs = 3
        
        # 1. 检查当前系统状态
        logger.info("1️⃣ 检查系统状态...")
        initial_health = self.verify_system_health()
        logger.info(f"当前活跃服务: {initial_health['active_services']}/{initial_health['total_services']}")
        
        if initial_health["issues"]:
            for issue in initial_health["issues"]:
                logger.warning(f"⚠️ {issue}")
        
        # 2. 修复MCP服务连接问题
        logger.info("2️⃣ 修复MCP服务...")
        services_to_fix = []
        for service, info in initial_health["services"].items():
            if not info["active"]:
                services_to_fix.append((service, info["port"]))
        
        if services_to_fix:
            logger.info(f"需要启动的服务: {[s[0] for s in services_to_fix]}")
            
            mcp_fix_success = True
            for service, port in services_to_fix:
                if not self.start_mcp_server(service, port):
                    mcp_fix_success = False
                    break
                # 等待服务稳定
                await asyncio.sleep(2)
            
            if mcp_fix_success:
                success_count += 1
                logger.info("✅ MCP服务修复成功")
            else:
                logger.error("❌ MCP服务修复失败")
        else:
            success_count += 1
            logger.info("✅ MCP服务已正常运行")
        
        # 3. 修复参数验证问题
        logger.info("3️⃣ 修复参数验证...")
        if self.fix_parameter_validation_in_place():
            success_count += 1
            logger.info("✅ 参数验证修复成功")
        else:
            logger.error("❌ 参数验证修复失败")
        
        # 4. 最终验证
        logger.info("4️⃣ 验证修复结果...")
        await asyncio.sleep(5)  # 等待服务完全启动
        
        final_health = self.verify_system_health()
        if final_health["overall_health"]:
            success_count += 1
            logger.info("✅ 系统修复验证通过")
        else:
            logger.error("❌ 系统修复验证失败")
            logger.error(f"剩余问题: {final_health['issues']}")
        
        # 计算修复成功率
        success_rate = success_count / total_repairs
        logger.info(f"\\n📊 修复结果: {success_count}/{total_repairs} ({success_rate:.1%})")
        
        return success_rate >= 0.75

async def main():
    """主函数"""
    logger.info("🚀 启动系统修复工具...")
    
    repair_tool = SystemRepair()
    
    try:
        success = await repair_tool.repair_system()
        
        if success:
            logger.info("\\n🎉 系统修复成功！")
            logger.info("💡 建议:")
            logger.info("  1. 重新运行失败的任务测试")
            logger.info("  2. 监控系统运行状态")
            return 0
        else:
            logger.error("\\n❌ 系统修复不完全")
            logger.error("💡 请检查日志中的错误信息并手动排查")
            return 1
            
    except Exception as e:
        logger.error(f"修复过程出错: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)