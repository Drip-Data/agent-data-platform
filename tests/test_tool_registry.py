import asyncio
import types
import sys
import uuid
import os

# Allow importing from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Stub redis and websockets to satisfy imports
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
    async def close(self):
        pass
redis_asyncio.from_url = lambda url: FakeRedis()
redis_pkg.asyncio = redis_asyncio
sys.modules.setdefault('redis', redis_pkg)
sys.modules.setdefault('redis.asyncio', redis_asyncio)

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

from core.toolscore.tool_registry import ToolRegistry
from core.toolscore.interfaces import MCPServerSpec, ToolType, ToolCapability
from core.toolscore.unified_tool_library import UnifiedToolLibrary


def test_tool_registry_register_and_get():
    async def run():
        registry = ToolRegistry()
        await registry.initialize()
        spec = MCPServerSpec(
            tool_id=f"test-{uuid.uuid4().hex[:8]}",
            name="Test Server",
            description="desc",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[
                ToolCapability(
                    name="cap", description="c", parameters={}, examples=[])
            ],
            endpoint="ws://localhost:1"
        )
        result = await registry.register_mcp_server(spec)
        assert result.success
        retrieved = await registry.get_tool_spec(spec.tool_id)
        assert retrieved is not None
        assert retrieved.name == spec.name
    asyncio.run(run())


def test_unified_tool_library_register_external():
    async def run():
        utl = UnifiedToolLibrary()
        # bypass heavy initialization
        await utl.tool_registry.initialize()
        spec = MCPServerSpec(
            tool_id=f"ext-{uuid.uuid4().hex[:8]}",
            name="External Server",
            description="ext",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[],
            endpoint="ws://localhost:2"
        )
        result = await utl.register_external_mcp_server(spec)
        assert result.success
        retrieved = await utl.get_tool_by_id(spec.tool_id)
        assert retrieved is not None
        assert retrieved.endpoint == spec.endpoint
    asyncio.run(run())
