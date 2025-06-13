import sys
import types


def install():
    """Install lightweight stub modules for offline environments."""
    # prometheus_client stub
    if 'prometheus_client' not in sys.modules:
        prom_pkg = types.ModuleType('prometheus_client')
        class _Counter:
            def __init__(self, *a, **k):
                pass
            def labels(self, *a, **k):
                return self
            def inc(self, *a, **k):
                pass
            def set(self, *a, **k):
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
        sys.modules['prometheus_client'] = prom_pkg

    # redis.asyncio stub
    if 'redis.asyncio' not in sys.modules:
        redis_pkg = types.ModuleType('redis')
        redis_asyncio = types.ModuleType('redis.asyncio')
        class FakeRedis:
            async def ping(self):
                pass
            async def setex(self, *a, **k):
                pass
            async def get(self, *a, **k):
                return None
            async def publish(self, *a, **k):
                pass
            async def hset(self, *a, **k):
                pass
            async def hgetall(self, *a, **k):
                return {}
            async def xadd(self, *a, **k):
                pass
            async def xlen(self, *a, **k):
                return 0
            async def xpending_range(self, *a, **k):
                return []
            async def xgroup_create(self, *a, **k):
                pass
            async def xreadgroup(self, *a, **k):
                return []
            async def expire(self, *a, **k):
                pass
            async def close(self):
                pass
        redis_asyncio.Redis = FakeRedis
        redis_asyncio.from_url = lambda url: FakeRedis()
        redis_pkg.asyncio = redis_asyncio
        sys.modules['redis'] = redis_pkg
        sys.modules['redis.asyncio'] = redis_asyncio

    # websockets stub
    if 'websockets' not in sys.modules:
        websockets_mod = types.ModuleType('websockets')
        class WebSocketClientProtocol:
            pass
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
        websockets_mod.WebSocketClientProtocol = WebSocketClientProtocol
        websockets_mod.connect = connect
        sys.modules['websockets'] = websockets_mod

    # httpx stub
    if 'httpx' not in sys.modules:
        httpx_mod = types.ModuleType('httpx')
        class DummyResponse:
            def __init__(self, data=None, status_code=200):
                self._data = data or {}
                self.status_code = status_code
            def json(self):
                return self._data
        class AsyncClient:
            def __init__(self, *a, **k):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                pass
            async def post(self, url, json=None):
                data = {
                    "recommended_tools": ["python_executor"],
                    "confidence": 0.5,
                    "strategy": "stub",
                }
                return DummyResponse(data)
        class Limits:
            def __init__(self, *a, **k):
                pass
        httpx_mod.AsyncClient = AsyncClient
        httpx_mod.Limits = Limits
        sys.modules['httpx'] = httpx_mod
