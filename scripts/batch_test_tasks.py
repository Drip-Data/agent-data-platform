#!/usr/bin/env python3
"""
Agent Data Platform 批量任务测试脚本
支持从tasks.jsonl文件读取任务并批量执行测试
"""

import asyncio
import aiohttp
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import argparse

logger = logging.getLogger(__name__)

@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    original_task_id: Optional[str]
    description: str
    status: str
    success: bool
    final_result: Optional[str]
    error_message: Optional[str]
    total_duration: float
    submit_time: datetime
    complete_time: Optional[datetime]
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['submit_time'] = self.submit_time.isoformat()
        if self.complete_time:
            data['complete_time'] = self.complete_time.isoformat()
        return data

class BatchTaskTester:
    """批量任务测试器"""
    
    def __init__(self, 
                 task_api_url: str = "http://localhost:8000",
                 max_concurrent: int = 3,
                 timeout: int = 300):
        self.task_api_url = task_api_url
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.results: List[TaskResult] = []
        
    def load_tasks_from_jsonl(self, file_path: str) -> List[Dict]:
        """从JSONL文件加载任务"""
        tasks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        task = json.loads(line)
                        # 标准化任务格式
                        standardized_task = self.standardize_task_format(task)
                        if standardized_task:
                            tasks.append(standardized_task)
                        else:
                            logger.warning(f"跳过第{line_num}行：无效的任务格式")
                    except json.JSONDecodeError as e:
                        logger.error(f"第{line_num}行JSON解析错误: {e}")
                        
        except FileNotFoundError:
            logger.error(f"任务文件不存在: {file_path}")
            
        logger.info(f"从 {file_path} 加载了 {len(tasks)} 个任务")
        return tasks
    
    def standardize_task_format(self, task: Dict) -> Optional[Dict]:
        """标准化任务格式"""
        # 支持多种任务格式
        standardized = {}
        
        # 获取任务描述
        description = (task.get("description") or 
                      task.get("input") or 
                      task.get("task_description"))
        if not description:
            return None
            
        standardized["input"] = description
        standardized["description"] = f"批量测试: {description[:50]}..."
        
        # 保留原始task_id用于追踪
        if "task_id" in task:
            standardized["original_task_id"] = task["task_id"]
            
        # 其他可选字段
        if "priority" in task:
            standardized["priority"] = task["priority"]
            
        return standardized
    
    async def submit_task(self, session: aiohttp.ClientSession, 
                         task: Dict) -> Optional[str]:
        """提交单个任务"""
        try:
            async with session.post(
                f"{self.task_api_url}/api/v1/tasks",
                json=task,
                timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("task_id")
                else:
                    logger.error(f"任务提交失败 (HTTP {resp.status}): {task.get('description', '')}")
                    
        except Exception as e:
            logger.error(f"任务提交异常: {e}")
            
        return None
    
    async def wait_for_task_completion(self, session: aiohttp.ClientSession,
                                     task_id: str, 
                                     original_task_id: Optional[str],
                                     description: str,
                                     submit_time: datetime) -> TaskResult:
        """等待任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            try:
                async with session.get(
                    f"{self.task_api_url}/api/v1/tasks/{task_id}",
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = data.get("status")
                        
                        if status in ["completed", "failed"]:
                            result_data = data.get("result", {})
                            
                            return TaskResult(
                                task_id=task_id,
                                original_task_id=original_task_id,
                                description=description,
                                status=status,
                                success=result_data.get("success", False),
                                final_result=result_data.get("final_result"),
                                error_message=result_data.get("error_message"),
                                total_duration=result_data.get("total_duration", 0),
                                submit_time=submit_time,
                                complete_time=datetime.now()
                            )
                            
            except Exception as e:
                logger.debug(f"查询任务状态异常: {e}")
                
            # 等待后重试
            await asyncio.sleep(2)
        
        # 超时情况
        return TaskResult(
            task_id=task_id,
            original_task_id=original_task_id,
            description=description,
            status="timeout",
            success=False,
            final_result=None,
            error_message=f"任务超时 ({self.timeout}秒)",
            total_duration=self.timeout,
            submit_time=submit_time,
            complete_time=datetime.now()
        )
    
    async def process_single_task(self, session: aiohttp.ClientSession,
                                 task: Dict) -> TaskResult:
        """处理单个任务的完整流程"""
        submit_time = datetime.now()
        description = task.get("input", "")
        original_task_id = task.get("original_task_id")
        
        logger.info(f"🚀 提交任务: {description[:50]}...")
        
        # 提交任务
        task_id = await self.submit_task(session, task)
        if not task_id:
            return TaskResult(
                task_id="",
                original_task_id=original_task_id,
                description=description,
                status="submit_failed",
                success=False,
                final_result=None,
                error_message="任务提交失败",
                total_duration=0,
                submit_time=submit_time,
                complete_time=datetime.now()
            )
        
        logger.info(f"✅ 任务已提交: {task_id}")
        
        # 等待完成
        result = await self.wait_for_task_completion(
            session, task_id, original_task_id, description, submit_time
        )
        
        status_emoji = "✅" if result.success else "❌"
        logger.info(f"{status_emoji} 任务完成: {task_id} (耗时: {result.total_duration:.1f}s)")
        
        return result
    
    async def run_batch_test(self, tasks: List[Dict]) -> List[TaskResult]:
        """运行批量测试"""
        logger.info(f"🎯 开始批量测试 {len(tasks)} 个任务 (最大并发: {self.max_concurrent})")
        
        async with aiohttp.ClientSession() as session:
            # 创建信号量控制并发
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def process_with_semaphore(task):
                async with semaphore:
                    return await self.process_single_task(session, task)
            
            # 并发执行所有任务
            self.results = await asyncio.gather(
                *[process_with_semaphore(task) for task in tasks],
                return_exceptions=True
            )
            
            # 处理异常结果
            processed_results = []
            for i, result in enumerate(self.results):
                if isinstance(result, Exception):
                    logger.error(f"任务处理异常: {result}")
                    # 创建错误结果
                    error_result = TaskResult(
                        task_id="",
                        original_task_id=tasks[i].get("original_task_id"),
                        description=tasks[i].get("input", ""),
                        status="error",
                        success=False,
                        final_result=None,
                        error_message=str(result),
                        total_duration=0,
                        submit_time=datetime.now(),
                        complete_time=datetime.now()
                    )
                    processed_results.append(error_result)
                else:
                    processed_results.append(result)
            
            self.results = processed_results
            
        return self.results
    
    def generate_test_report(self) -> str:
        """生成测试报告"""
        if not self.results:
            return "无测试结果"
            
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful
        
        avg_duration = sum(r.total_duration for r in self.results) / total
        
        report = []
        report.append("📊 Agent Data Platform 批量测试报告")
        report.append("=" * 60)
        report.append(f"📋 总任务数: {total}")
        report.append(f"✅ 成功: {successful} ({successful/total*100:.1f}%)")
        report.append(f"❌ 失败: {failed} ({failed/total*100:.1f}%)")
        report.append(f"⏱️ 平均耗时: {avg_duration:.1f}秒")
        report.append("")
        
        # 详细结果
        report.append("📝 详细结果:")
        for i, result in enumerate(self.results, 1):
            status_emoji = "✅" if result.success else "❌"
            original_id = f" (原ID: {result.original_task_id})" if result.original_task_id else ""
            report.append(
                f"{i:2d}. {status_emoji} {result.description[:50]}... "
                f"[{result.status}] {result.total_duration:.1f}s{original_id}"
            )
            
        # 失败任务详情
        failed_tasks = [r for r in self.results if not r.success]
        if failed_tasks:
            report.append("")
            report.append("🔍 失败任务详情:")
            for result in failed_tasks:
                report.append(f"  - {result.description[:50]}...")
                report.append(f"    错误: {result.error_message}")
                
        return "\n".join(report)
    
    def save_results(self, output_file: str):
        """保存测试结果到文件"""
        results_data = {
            "test_time": datetime.now().isoformat(),
            "total_tasks": len(self.results),
            "successful_tasks": sum(1 for r in self.results if r.success),
            "failed_tasks": sum(1 for r in self.results if not r.success),
            "results": [result.to_dict() for result in self.results]
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"📁 测试结果已保存到: {output_file}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Agent Data Platform 批量任务测试")
    parser.add_argument("--tasks-file", default="tasks.jsonl", 
                       help="任务文件路径 (JSONL格式)")
    parser.add_argument("--api-url", default="http://localhost:8000",
                       help="Task API URL")
    parser.add_argument("--concurrent", type=int, default=3,
                       help="最大并发任务数")
    parser.add_argument("--timeout", type=int, default=300,
                       help="单个任务超时时间(秒)")
    parser.add_argument("--output", default="output/batch_test_results.json",
                       help="结果输出文件")
    parser.add_argument("--verbose", action="store_true",
                       help="详细日志输出")
    
    args = parser.parse_args()
    
    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 创建批量测试器
    tester = BatchTaskTester(
        task_api_url=args.api_url,
        max_concurrent=args.concurrent,
        timeout=args.timeout
    )
    
    # 加载任务
    tasks = tester.load_tasks_from_jsonl(args.tasks_file)
    if not tasks:
        logger.error("没有找到有效的任务，退出")
        return
        
    # 执行批量测试
    logger.info("🚀 开始批量测试...")
    start_time = time.time()
    
    results = await tester.run_batch_test(tasks)
    
    end_time = time.time()
    logger.info(f"🎉 批量测试完成，总耗时: {end_time - start_time:.1f}秒")
    
    # 生成报告
    report = tester.generate_test_report()
    print("\n" + report)
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tester.save_results(str(output_path))

if __name__ == "__main__":
    asyncio.run(main()) 