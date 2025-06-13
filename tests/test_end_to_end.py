import asyncio
import sys
import types
import uuid
import os

# Allow importing from project root
# Stub prometheus_client
prom_pkg = types.ModuleType("prometheus_client")
class _Counter:
    def __init__(self, *args, **kwargs):
        pass
    def labels(self, *args, **kwargs):
        return self
    def inc(self, *args, **kwargs):
        pass
    def set(self, *args, **kwargs):
        pass
class _Histogram(_Counter):
    observe = _Counter.inc
class _Gauge(_Counter):
    pass
prom_pkg.Counter = _Counter
prom_pkg.Histogram = _Histogram
prom_pkg.Gauge = _Gauge
prom_pkg.CollectorRegistry = object
prom_pkg.start_http_server = lambda *a, **k: None
sys.modules.setdefault("prometheus_client", prom_pkg)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Stub redis ---
redis_pkg = types.ModuleType('redis')
redis_asyncio = types.ModuleType('redis.asyncio')
class FakeRedis:
    async def ping(self):
        pass
    async def setex(self, *args, **kwargs):
        pass
    async def get(self, *args, **kwargs):
        return None
    async def publish(self, *args, **kwargs):
        pass
    async def hset(self, *args, **kwargs):
        pass
    async def hgetall(self, *args, **kwargs):
        return {}
    async def xadd(self, *args, **kwargs):
        pass
    async def xlen(self, *args, **kwargs):
        return 0
    async def xpending_range(self, *args, **kwargs):
        return []
    async def close(self):
        pass
redis_asyncio.Redis = FakeRedis
redis_asyncio.from_url = lambda url: FakeRedis()
redis_pkg.asyncio = redis_asyncio
sys.modules.setdefault('redis', redis_pkg)
sys.modules.setdefault('redis.asyncio', redis_asyncio)

# --- Stub websockets ---
websockets_mod = types.ModuleType('websockets')
async def connect(url, timeout=None):
    class Dummy:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def send(self, msg):
            pass
        async def recv(self):
            return ''
        async def close(self):
            pass
    return Dummy()
websockets_mod.connect = connect
sys.modules.setdefault('websockets', websockets_mod)

# --- Stub httpx ---
httpx_mod = types.ModuleType('httpx')
class DummyResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
    def json(self):
        return self._data
class AsyncClient:
    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def post(self, url, json=None):
        return DummyResponse({"recommended_tools": ["python_executor"], "confidence": 0.9, "strategy": "stub"})
httpx_mod.AsyncClient = AsyncClient
sys.modules.setdefault('httpx', httpx_mod)

from core.dispatcher_enhanced import EnhancedTaskDispatcher
from core.interfaces import TaskSpec, TaskType


def test_dispatcher_tool_enhancement():
    async def run():
        dispatcher = EnhancedTaskDispatcher('redis://localhost')
        task = TaskSpec(
            task_id=f"t-{uuid.uuid4().hex[:8]}",
            task_type=TaskType.CODE,
            description="print hello",
            expected_tools=["auto"],
            constraints={},
            max_steps=3,
            priority=1,
        )
        enhanced = await dispatcher._enhance_task_with_tools(task)
        assert enhanced.expected_tools == ["python_executor"]
    asyncio.run(run())

