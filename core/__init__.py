# Agent Data Platform Core Module

# Interfaces
from .interfaces.task_interfaces import TaskType, TaskSpec, ExecutionStep, TrajectoryResult
from .interfaces.runtime_interfaces import RuntimeInterface
from .interfaces.llm_interfaces import LLMInteraction
from .interfaces.common_interfaces import ActionType, ErrorType

# Utilities
from .utils.common import (
    generate_task_id,
    hash_content,
    RateLimiter,
    CircuitBreaker
)
from .utils.json_utils import (
    safe_json_loads,
    safe_json_dumps
)
# from .utils.async_utils import ... # Currently empty, no exports

# Task Management
from core.task_management.task_manager import TaskManager
from core.task_management.dispatcher_enhanced import EnhancedTaskDispatcher
from core.task_management.router import IntelligentRouter
from core.task_management.task_api import app as task_api_app

# LLM
from .llm.llm_client import LLMClient, LLMProvider

# Metrics
from .metrics.metrics import EnhancedMetrics

# Cache
from .cache.cache import TemplateCache

# Browser
from .browser.browser_state_manager import BrowserStateManager, state_manager

# Redis
from .redis.redis_manager import RedisManager

# Toolscore Interfaces
# Toolscore Interfaces
# Note: Toolscore interfaces are kept separate to avoid circular dependencies and maintain modularity.
# They are imported directly where needed within the toolscore module.
# from .toolscore.interfaces.interfaces import (
#     ToolType as ToolscoreToolType, # Alias to avoid conflict with core.interfaces.TaskType
#     ErrorType as ToolscoreErrorType, # Alias to avoid conflict with core.interfaces.ErrorType
#     ExecutionResult,
#     ToolCapability,
#     ToolSpec,
#     FunctionToolSpec,
#     MCPServerSpec,
#     BaseToolAdapter,
#     ToolDiscoveryInterface,
#     ToolExecutionInterface,
#     RegistrationResult,
#     InstallationResult
# )

# Toolscore Managers
from .toolscore.managers.cache_manager import CacheManager
from .toolscore.managers.core_manager import CoreManager
from .toolscore.managers.dynamic_mcp_manager import DynamicMCPManager
from .toolscore.managers.tool_registry import ToolRegistry
from .toolscore.managers.unified_tool_library import UnifiedToolLibrary

# Toolscore API
from .toolscore.api.monitoring_api import ToolScoreMonitoringAPI

# Toolscore MCP
from .toolscore.mcp.mcp_client import MCPToolClient
from .toolscore.mcp.mcp_connector import MCPServerConnector
from .toolscore.mcp.mcp_server import MCPServer

# Toolscore Detection
from .toolscore.detection.mcp_search_tool import MCPSearchTool
from .toolscore.detection.tool_gap_detector import ToolGapDetector

# Toolscore WebSocket
from .toolscore.websocket.websocket_manager import WebSocketManager