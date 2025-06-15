import logging
import os
import sys
import io
import subprocess
from pathlib import Path

# 获取项目根目录，用于日志文件路径
project_root = Path(__file__).parent.parent
LOGS_DIR = project_root / 'logs'

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

def setup_logging():
    """配置日志系统，包括Windows控制台Unicode编码修复"""
    # 为Windows控制台设置UTF-8编码，修复emoji显示问题
    if os.name == 'nt':
        try:
            subprocess.run(['chcp', '65001'], shell=True, capture_output=True)
        except Exception:
            pass
        
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOGS_DIR / 'toolscore.log', mode='a', encoding='utf-8')
        ]
    )

    # 设置 aiohttp.access 日志级别为 WARNING，减少不必要的访问日志
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.client').setLevel(logging.WARNING) # 修复 Bug 10

    # 应用安全格式化器
    for handler in logging.root.handlers:
        handler.setFormatter(SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    # 返回一个logger实例，方便其他模块使用
    return logging.getLogger(__name__)

# 在模块加载时执行一次日志设置
# setup_logging() # 不在此处直接调用，由 main.py 显式调用