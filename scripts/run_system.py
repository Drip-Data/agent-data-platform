#!/usr/bin/env python3
"""
Agent Data Platform 系统运行脚本
包括服务启动和任务批量注入功能
"""

import asyncio
import argparse
import logging
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 确保日志目录存在
logs_dir = project_root / 'logs'
logs_dir.mkdir(exist_ok=True)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(logs_dir / 'run_system.log')
    ]
)
logger = logging.getLogger(__name__)

class SystemRunner:
    """系统运行器"""
    
    def __init__(self):
        self.main_process = None
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
    async def start_services(self, wait_time: int = 30):
        """启动服务"""
        logger.info("🚀 启动Agent Data Platform服务...")
        
        try:
            # 启动主服务
            main_py_path = project_root / "main.py"
            cmd = [sys.executable, str(main_py_path)]
            self.main_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=str(project_root)  # 设置工作目录
            )
            
            logger.info(f"✅ 主服务启动中 (PID: {self.main_process.pid})")
            
            # 等待服务启动并进行健康检查
            logger.info(f"⏳ 等待 {wait_time} 秒让服务启动...")
            
            # 分阶段等待和检查
            for i in range(wait_time):
                await asyncio.sleep(1)
                
                # 检查进程是否还活着
                if self.main_process.poll() is not None:
                    # 进程已退出，获取错误信息
                    stdout, stderr = self.main_process.communicate()
                    logger.error("❌ 服务启动失败 - 进程提前退出")
                    if stdout:
                        logger.error(f"标准输出: {stdout}")
                    if stderr:
                        logger.error(f"错误输出: {stderr}")
                    logger.error(f"退出码: {self.main_process.returncode}")
                    return False
                
                # 每5秒尝试一次健康检查
                if i % 5 == 4 and i > 10:  # 从第10秒开始，每5秒检查一次
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get('http://localhost:8000/health', timeout=3) as response:
                                if response.status == 200:
                                    logger.info("✅ 服务启动成功 - API健康检查通过")
                                    self.is_running = True
                                    return True
                    except:
                        # 健康检查失败，继续等待
                        pass
            
            # 超时后进行最终检查
            if self.main_process.poll() is None:
                # 进程还在运行，进行最终健康检查
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get('http://localhost:8000/health', timeout=5) as response:
                            if response.status == 200:
                                logger.info("✅ 服务启动成功 - 最终健康检查通过")
                                self.is_running = True
                                return True
                            else:
                                logger.warning(f"⚠️ API健康检查失败，状态码: {response.status}")
                except Exception as e:
                    logger.warning(f"⚠️ 健康检查异常: {e}")
                
                # 即使健康检查失败，如果进程还在运行就认为启动成功
                logger.info("✅ 服务进程启动成功（健康检查失败但进程运行中）")
                self.is_running = True
                return True
            else:
                # 进程已退出
                stdout, stderr = self.main_process.communicate()
                logger.error("❌ 服务启动失败 - 进程已退出")
                if stdout:
                    logger.error(f"标准输出: {stdout}")
                if stderr:
                    logger.error(f"错误输出: {stderr}")
                logger.error(f"退出码: {self.main_process.returncode}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动服务时出错: {e}")
            return False
    
    async def stop_services(self):
        """停止服务"""
        logger.info("🛑 停止服务...")
        
        if self.main_process and self.main_process.poll() is None:
            try:
                # 优雅关闭
                self.main_process.terminate()
                
                # 等待进程结束
                try:
                    self.main_process.wait(timeout=10)
                    logger.info("✅ 服务已优雅关闭")
                except subprocess.TimeoutExpired:
                    # 强制关闭
                    logger.warning("⚠️ 优雅关闭超时，强制关闭...")
                    self.main_process.kill()
                    self.main_process.wait()
                    logger.info("✅ 服务已强制关闭")
                    
            except Exception as e:
                logger.error(f"❌ 停止服务时出错: {e}")
        
        self.is_running = False
        self.shutdown_event.set()
    
    async def check_service_health(self) -> bool:
        """检查服务健康状态"""
        try:
            import aiohttp
            
            # 检查API服务
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get('http://localhost:8000/health', timeout=5) as response:
                        if response.status == 200:
                            logger.info("✅ API服务健康检查通过")
                            return True
                        else:
                            logger.warning(f"⚠️ API服务返回状态码: {response.status}")
                            return False
                except aiohttp.ClientError as e:
                    logger.warning(f"⚠️ API服务连接失败: {e}")
                    return False
                    
        except ImportError:
            logger.warning("⚠️ aiohttp未安装，跳过HTTP健康检查")
            
        # 检查进程状态
        if self.main_process and self.main_process.poll() is None:
            logger.info("✅ 主进程运行正常")
            return True
        else:
            logger.error("❌ 主进程未运行")
            return False
    
    async def inject_tasks(self, tasks_file: str, batch_size: int = 5, delay: float = 2.0):
        """批量注入任务"""
        logger.info(f"📋 开始批量注入任务: {tasks_file}")
        
        # 检查文件是否存在
        if not os.path.isabs(tasks_file):
            tasks_file = str(project_root / tasks_file)
        if not os.path.exists(tasks_file):
            logger.error(f"❌ 任务文件不存在: {tasks_file}")
            return False
        
        try:
            # 使用batch_test_tasks.py进行任务注入
            batch_script_path = project_root / "scripts" / "batch_test_tasks.py"
            cmd = [
                sys.executable, 
                str(batch_script_path),
                "--tasks-file", tasks_file,
                "--batch-size", str(batch_size),
                "--delay", str(delay),
                "--api-url", "http://localhost:8000"
            ]
            
            logger.info(f"🚀 执行命令: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=str(project_root)  # 设置工作目录
            )
            
            # 实时输出日志
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    logger.info(f"[BatchTester] {output.strip()}")
            
            return_code = process.poll()
            
            if return_code == 0:
                logger.info("✅ 任务注入完成")
                return True
            else:
                logger.error(f"❌ 任务注入失败，返回码: {return_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 注入任务时出错: {e}")
            return False
    
    async def run_interactive_mode(self):
        """交互式运行模式"""
        logger.info("🎮 进入交互式模式")
        logger.info("可用命令:")
        logger.info("  status  - 检查服务状态")
        logger.info("  inject <file> - 注入任务文件")
        logger.info("  health  - 健康检查")
        logger.info("  stop    - 停止服务")
        logger.info("  quit    - 退出")
        
        while self.is_running:
            try:
                command = input("\n> ").strip().split()
                if not command:
                    continue
                    
                cmd = command[0].lower()
                
                if cmd == "status":
                    if self.is_running:
                        logger.info("✅ 服务正在运行")
                    else:
                        logger.info("❌ 服务未运行")
                        
                elif cmd == "inject":
                    if len(command) < 2:
                        logger.error("❌ 请指定任务文件: inject <file>")
                        continue
                    task_file = command[1]
                    await self.inject_tasks(task_file)
                    
                elif cmd == "health":
                    healthy = await self.check_service_health()
                    if healthy:
                        logger.info("✅ 服务健康")
                    else:
                        logger.error("❌ 服务不健康")
                        
                elif cmd == "stop":
                    await self.stop_services()
                    break
                    
                elif cmd == "quit":
                    await self.stop_services()
                    break
                    
                else:
                    logger.error(f"❌ 未知命令: {cmd}")
                    
            except KeyboardInterrupt:
                logger.info("\n🛑 收到中断信号")
                break
            except EOFError:
                logger.info("\n🛑 输入结束")
                break
            except Exception as e:
                logger.error(f"❌ 命令执行错误: {e}")
    
    async def run_batch_mode(self, tasks_file: str, batch_size: int, delay: float):
        """批处理运行模式"""
        logger.info("🔄 批处理模式")
        
        # 等待服务就绪
        logger.info("⏳ 等待服务就绪...")
        for i in range(30):  # 最多等待30秒
            if await self.check_service_health():
                break
            await asyncio.sleep(1)
        else:
            logger.error("❌ 服务启动超时")
            return False
        
        # 注入任务
        success = await self.inject_tasks(tasks_file, batch_size, delay)
        
        # 等待任务完成（可以根据需要调整）
        logger.info("⏳ 等待任务执行完成...")
        await asyncio.sleep(10)
        
        return success


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Agent Data Platform 系统运行器")
    parser.add_argument("--mode", choices=["interactive", "batch"], default="interactive",
                        help="运行模式 (默认: interactive)")
    parser.add_argument("--tasks-file", default="data/tasks.jsonl",
                        help="任务文件路径 (默认: data/tasks.jsonl)")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="批次大小 (默认: 5)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="任务间延迟秒数 (默认: 2.0)")
    parser.add_argument("--wait-time", type=int, default=10,
                        help="服务启动等待时间 (默认: 10)")
    parser.add_argument("--no-start", action="store_true",
                        help="不启动服务，只注入任务")
    
    args = parser.parse_args()
    
    runner = SystemRunner()
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"\n🛑 收到信号 {signum}")
        asyncio.create_task(runner.stop_services())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        if not args.no_start:
            # 启动服务
            if not await runner.start_services(args.wait_time):
                logger.error("❌ 服务启动失败")
                return 1
        
        if args.mode == "interactive":
            await runner.run_interactive_mode()
        elif args.mode == "batch":
            success = await runner.run_batch_mode(
                args.tasks_file, args.batch_size, args.delay
            )
            if not success:
                logger.error("❌ 批处理执行失败")
                return 1
        
        logger.info("🎉 运行完成")
        return 0
        
    except Exception as e:
        logger.error(f"❌ 运行时错误: {e}")
        return 1
    finally:
        if runner.is_running:
            await runner.stop_services()


if __name__ == "__main__":
    # 确保logs目录存在（已在上面创建）
    # 切换到项目根目录执行
    os.chdir(str(project_root))
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 程序被中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)