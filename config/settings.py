import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 获取项目根目录
# 假设 config 目录在项目根目录下
project_root = Path(__file__).parent.parent 

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

def get_available_api_keys_info():
    """获取并返回当前可用的API密钥信息（部分遮蔽）"""
    available_keys = []
    for key_name in ['GEMINI_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY']:
        if os.getenv(key_name):
            key_value = os.getenv(key_name)
            masked_key = f"{key_value[:4]}{'*' * (len(key_value) - 8)}{key_value[-4:]}" if len(key_value) > 8 else "****"
            available_keys.append(f"{key_name}: {masked_key}")
    return available_keys

# 在模块加载时执行一次环境和API密钥检查
# 这样在其他模块导入 settings 时，环境就已经准备好了
load_environment()
if not check_and_setup_api_keys():
    print("⚠️  警告: 没有可用的LLM API密钥，某些功能可能无法正常工作")
    print("系统将继续启动，但建议配置API密钥以获得完整功能")

# 定义其他配置常量
LOGS_DIR = project_root / 'logs'
OUTPUT_TRAJECTORIES_DIR = project_root / 'output' / 'trajectories'
CONFIG_DIR = project_root / 'config'
DATA_DIR = project_root / 'data'

# 确保必要的目录存在
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(OUTPUT_TRAJECTORIES_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 设置输出目录环境变量
os.environ.setdefault('OUTPUT_DIR', str(OUTPUT_TRAJECTORIES_DIR))

# 定义服务端口
TOOLSCORE_MCP_PORT = 8081
TOOLSCORE_MONITORING_PORT = 8082
TASK_API_PORT = 8000

# Metrics 服务端口
METRICS_REASONING_PORT = 8003
METRICS_SANDBOX_PORT = 8001
METRICS_WEB_NAVIGATOR_PORT = 8002
METRICS_SYNTHESIS_PORT = 8004 # 为 Synthesis API 预留一个端口

# MCP Server 动态端口范围
MCP_SERVER_PORT_RANGE_START = 9000
MCP_SERVER_PORT_RANGE_END = 9100

# 定义ToolScore的URL
TOOLSCORE_HTTP_URL = f"http://localhost:{TOOLSCORE_MONITORING_PORT}"
TOOLSCORE_WS_URL = f"ws://localhost:{TOOLSCORE_MCP_PORT}"
TOOLSCORE_MCP_WS_URL = f"ws://localhost:{TOOLSCORE_MCP_PORT}/websocket" # ToolScore 核心服务的 WebSocket endpoint，用于 MCP 客户端连接