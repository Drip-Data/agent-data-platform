#!/usr/bin/env python3
"""
Deepsearch Server Configuration
确保Gemini API Key正确配置
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def ensure_gemini_api_key():
    """确保Gemini API Key已配置"""
    # 检查环境变量
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        logger.info("✅ GEMINI_API_KEY found in environment variables")
        return True
    
    # 检查.env文件
    env_files = [
        Path.cwd() / ".env",
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent.parent / ".env",  # agent-data-platform/.env
    ]
    
    for env_file in env_files:
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        if line.strip().startswith('GEMINI_API_KEY='):
                            api_key = line.strip().split('=', 1)[1].strip().strip('"\'')
                            if api_key:
                                os.environ['GEMINI_API_KEY'] = api_key
                                logger.info(f"✅ GEMINI_API_KEY loaded from {env_file}")
                                return True
            except Exception as e:
                logger.warning(f"Failed to read {env_file}: {e}")
    
    logger.error("❌ GEMINI_API_KEY not found. Please set it in environment variables or .env file")
    return False

def validate_dependencies():
    """验证依赖包是否已安装"""
    required_packages = [
        'langchain_google_genai',
        'langgraph', 
        'google.genai',
        'pydantic'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('.', '_') if '.' in package else package)
            logger.debug(f"✅ {package} is available")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"❌ {package} is not installed")
    
    if missing_packages:
        logger.error(f"Missing packages: {', '.join(missing_packages)}")
        logger.error("Please install with: pip install -r requirements.txt")
        return False
    
    return True

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("🔧 Checking Deepsearch Server Configuration...")
    
    # 检查API Key
    api_key_ok = ensure_gemini_api_key()
    
    # 检查依赖
    deps_ok = validate_dependencies()
    
    if api_key_ok and deps_ok:
        print("✅ Deepsearch Server configuration is ready!")
    else:
        print("❌ Configuration issues found. Please resolve before starting the server.")
        exit(1)