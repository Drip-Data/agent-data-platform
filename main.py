#!/usr/bin/env python3
"""
Agent Data Platform - Main Entry Point (无Docker版本)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
import subprocess, signal
from dotenv import load_dotenv
import argparse

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入服务管理器和服务模块
from services.service_manager import ServiceManager
from services import (
    redis_service,
    toolscore_service,
    task_api_service,  # 重新启用task_api_service
    runtime_service,
    mcp_server_launcher,
    synthesis_service
)

from core.path_utils import ensure_output_structure

# 创建必要的目录结构
ensure_output_structure()
os.makedirs(project_root / 'logs', exist_ok=True)
os.makedirs(project_root / 'config', exist_ok=True)
os.makedirs(project_root / 'data', exist_ok=True)

# 加载环境变量文件
def load_environment():
    """加载环境变量，优先级：.env > .env.local > 系统环境变量"""
    env_files = ['.env', '.env.local']
    loaded_any = False
    
    for env_file in env_files:
        env_path = project_root / env_file
        if env_path.exists():
            load_dotenv(env_path, override=False)
            loaded_any = True
            print(f"✅ 已加载环境变量文件: {env_file}")
    
    if not loaded_any:
        print("⚠️  未找到 .env 文件，将使用系统环境变量")
    
    return loaded_any

# 加载环境变量
load_environment()

# 检查并设置API密钥
def check_and_setup_api_keys():
    """检查并设置API密钥，按优先级自动选择可用的API"""
    api_providers = [
        ('GEMINI_API_KEY', 'Google Gemini'),
        ('DEEPSEEK_API_KEY', 'DeepSeek'),
        ('OPENAI_API_KEY', 'OpenAI'),
    ]
    
    available_apis = []
    for api_key, provider_name in api_providers:
        if os.getenv(api_key):
            available_apis.append(provider_name)
            print(f"✅ 发现 {provider_name} API 密钥")
    
    if available_apis:
        print(f"🚀 可用的API提供商: {', '.join(available_apis)}")
        return True
    else:
        print("❌ 错误: 未找到任何API密钥！")
        print("请设置以下任一API密钥：")
        for api_key, provider_name in api_providers:
            print(f"  - {api_key} ({provider_name})")
        print("💡 您可以创建 .env 文件或设置系统环境变量")
        print("💡 参考 .env.example 文件获取配置模板")
        return False

# 检查API密钥
if not check_and_setup_api_keys():
    print("⚠️  警告: 没有可用的LLM API密钥，某些功能可能无法正常工作")
    print("系统将继续启动，但建议配置API密钥以获得完整功能")

# 配置日志 - 修复Windows控制台Unicode编码问题
import sys
import io

# 为Windows控制台设置UTF-8编码，修复emoji显示问题
if os.name == 'nt':
    # 设置控制台代码页为UTF-8
    try:
        import subprocess
        subprocess.run(['chcp', '65001'], shell=True, capture_output=True)
    except:
        pass
    
    # 重定向标准输出为UTF-8编码
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置日志，避免emoji字符导致的编码错误
class SafeFormatter(logging.Formatter):
    """安全的日志格式化器，处理Unicode字符"""
    def format(self, record):
        try:
            return super().format(record)
        except UnicodeEncodeError:
            # 移除emoji字符，替换为文字描述
            msg = record.getMessage()
            msg = msg.replace('✅', '[OK]').replace('❌', '[ERROR]').replace('⚠️', '[WARN]').replace('🚀', '[START]').replace('🔧', '[FIX]').replace('⏳', '[WAIT]').replace('🔄', '[PROC]')
            record.msg = msg
            record.args = ()
            return super().format(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/toolscore.log', mode='a', encoding='utf-8')
    ]
)

# 应用安全格式化器
for handler in logging.root.handlers:
    handler.setFormatter(SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger = logging.getLogger(__name__)

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Agent Data Platform")
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def load_configuration(args):
    """加载配置"""
    # 加载.env文件
    load_dotenv()
    
    # 命令行参数覆盖环境变量
    config = {}
    
    # 如果提供了配置文件，加载它
    if args.config:
        # 此处可以添加配置文件加载逻辑
        pass
    
    # 设置调试模式
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        config['DEBUG'] = True
    
    return config

def setup_signal_handlers(service_manager):
    """设置信号处理器以优雅关闭"""
    def signal_handler(sig, frame):
        logger.info(f"收到信号 {sig}，正在优雅关闭...")
        service_manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def main():
    """主函数，应用入口点"""
    logger.info("=== Agent Data Platform 启动中 ===")
    
    # 解析命令行参数
    args = parse_arguments()
    
    # 加载配置
    config = load_configuration(args)
    
    # 创建服务管理器
    service_manager = ServiceManager()
    
    # 注册所有服务
    service_manager.register_service(
        name="redis",
        initialize_fn=redis_service.initialize,
        start_fn=redis_service.start,
        stop_fn=redis_service.stop,
        health_check_fn=redis_service.health_check,
        dependencies=[]  # Redis是基础服务，没有依赖
    )
    
    service_manager.register_service(
        name="toolscore",
        initialize_fn=toolscore_service.initialize,
        start_fn=toolscore_service.start,        
        stop_fn=toolscore_service.stop,
        health_check_fn=toolscore_service.health_check,
        dependencies=["redis"]  # ToolScore依赖Redis
    )
    
    service_manager.register_service(
        name="mcp_servers",
        initialize_fn=mcp_server_launcher.initialize,
        start_fn=mcp_server_launcher.start,
        stop_fn=mcp_server_launcher.stop,
        health_check_fn=mcp_server_launcher.health_check,
        dependencies=["toolscore"]  # MCP服务器依赖ToolScore
    )
    
    service_manager.register_service(
        name="task_api",
        initialize_fn=task_api_service.initialize,
        start_fn=task_api_service.start,
        stop_fn=task_api_service.stop,
        health_check_fn=task_api_service.health_check,
        dependencies=["redis", "toolscore"]  # 任务API依赖Redis和ToolScore
    )
    
    service_manager.register_service(
        name="runtime",
        initialize_fn=runtime_service.initialize,
        start_fn=runtime_service.start,
        stop_fn=runtime_service.stop,
        health_check_fn=runtime_service.health_check,
        dependencies=["redis", "toolscore", "mcp_servers"]  # 运行时依赖Redis、ToolScore和MCP服务器
    )
    
    service_manager.register_service(
        name="synthesis",
        initialize_fn=synthesis_service.initialize,
        start_fn=synthesis_service.start,
        stop_fn=synthesis_service.stop,
        health_check_fn=synthesis_service.health_check,
        dependencies=["redis"]  # 合成服务依赖Redis
    )
    
    # 设置信号处理
    setup_signal_handlers(service_manager)
    
    try:
        # 初始化所有服务
        service_manager.initialize_all(config)
        
        # 启动所有服务
        service_manager.start_all()
        
        # 在这里，我们可以让主线程等待，因为各个服务会在自己的线程中运行
        logger.info("所有服务已启动，按 Ctrl+C 停止")
        
        # 这里可以添加一个简单的循环来保持主线程运行
        # 或者使用更复杂的事件循环管理
        import platform, threading
        if platform.system().lower() == 'windows':
            logger.info("Windows平台下使用Event().wait()保持主线程挂起")
            threading.Event().wait()
        else:
            signal.pause()  # 等待信号
        
    except Exception as e:
        logger.error(f"启动过程中出错: {e}", exc_info=True)
        service_manager.stop_all()
        sys.exit(1)

if __name__ == "__main__":
    main()