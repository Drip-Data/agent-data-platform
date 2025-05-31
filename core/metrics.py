import time
from typing import Dict
from prometheus_client import Counter, Histogram, Gauge, start_http_server, CollectorRegistry

class EnhancedMetrics:
    """增强版Prometheus指标收集器"""
    
    def __init__(self, port: int = 8000):
        self.port = port
        self.registry = CollectorRegistry()
        
        # 任务指标
        self.tasks_submitted = Counter(
            'tasks_submitted_total',
            'Total submitted tasks',
            ['task_type', 'runtime'],
            registry=self.registry
        )
        
        self.tasks_completed = Counter(
            'tasks_completed_total',
            'Total completed tasks', 
            ['runtime', 'status'],
            registry=self.registry
        )
        
        self.tasks_failed = Counter(
            'tasks_failed_total',
            'Total failed tasks',
            ['runtime', 'error_type'],
            registry=self.registry
        )
        
        self.task_duration = Histogram(
            'task_duration_seconds',
            'Task execution duration',
            ['runtime'],
            registry=self.registry
        )
        
        self.active_tasks = Gauge(
            'active_tasks',
            'Currently active tasks',
            ['runtime'],
            registry=self.registry
        )
        
        # 队列指标
        self.queue_size = Gauge(
            'queue_size',
            'Task queue size',
            ['queue_name'],
            registry=self.registry
        )
        
        self.pending_lag_seconds = Gauge(
            'pending_lag_seconds',
            'Lag time for pending tasks',
            ['runtime'],
            registry=self.registry
        )
        
        # 缓存指标
        self.cache_hits = Counter(
            'cache_hits_total',
            'Template cache hits',
            ['cache_type'],
            registry=self.registry
        )
        
        self.cache_misses = Counter(
            'cache_misses_total', 
            'Template cache misses',
            ['cache_type'],
            registry=self.registry
        )
        
        # 系统指标
        self.runtime_health = Gauge(
            'runtime_health',
            'Runtime health status (1=healthy, 0=unhealthy)',
            ['runtime'],
            registry=self.registry
        )
        
        # 任务计时器
        self._task_timers: Dict[str, float] = {}
        
    def start_server(self):
        """启动metrics服务器"""
        start_http_server(self.port, registry=self.registry)
    
    def record_task_submitted(self, task_type: str, runtime: str):
        """记录任务提交"""
        self.tasks_submitted.labels(task_type=task_type, runtime=runtime).inc()
    
    def record_task_started(self, task_id: str, runtime: str):
        """记录任务开始"""
        self.active_tasks.labels(runtime=runtime).inc()
        self._task_timers[task_id] = time.time()
    
    def record_task_completed(self, task_id: str, runtime: str, success: bool, error_type: str = None):
        """记录任务完成"""
        self.active_tasks.labels(runtime=runtime).dec()
        
        # 记录完成状态
        status = 'success' if success else 'failure'
        self.tasks_completed.labels(runtime=runtime, status=status).inc()
        
        # 记录失败类型
        if not success and error_type:
            self.tasks_failed.labels(runtime=runtime, error_type=error_type).inc()
        
        # 记录执行时间
        if task_id in self._task_timers:
            duration = time.time() - self._task_timers[task_id]
            self.task_duration.labels(runtime=runtime).observe(duration)
            del self._task_timers[task_id]
    
    def update_queue_size(self, queue_name: str, size: int):
        """更新队列大小"""
        self.queue_size.labels(queue_name=queue_name).set(size)
    
    def update_runtime_health(self, runtime: str, healthy: bool):
        """更新运行时健康状态"""
        self.runtime_health.labels(runtime=runtime).set(1 if healthy else 0)
    
    def record_cache_hit(self, cache_type: str = 'template'):
        """记录缓存命中"""
        self.cache_hits.labels(cache_type=cache_type).inc()
    
    def record_cache_miss(self, cache_type: str = 'template'):
        """记录缓存未命中"""
        self.cache_misses.labels(cache_type=cache_type).inc()