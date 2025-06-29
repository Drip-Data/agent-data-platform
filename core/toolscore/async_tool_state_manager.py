"""
Asynchronous Tool State Manager
Replaces blocking wait_for_tools_ready() with background health checks
"""

import asyncio
import logging
import time
from typing import Dict, Set, Optional, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ToolState(Enum):
    """Tool availability states"""
    INITIALIZING = "initializing"
    READY = "ready"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"

@dataclass
class ToolHealthInfo:
    """Tool health information"""
    state: ToolState
    last_check: datetime
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    error_message: Optional[str] = None

class AsyncToolStateManager:
    """
    Non-blocking tool state manager that maintains tool health in background
    
    This replaces the synchronous wait_for_tools_ready() approach with:
    1. Background health checks running continuously
    2. Instant state queries via is_ready()
    3. State change notifications
    """
    
    def __init__(self, toolscore_client, essential_tools: Optional[Set[str]] = None):
        self.toolscore_client = toolscore_client
        self.essential_tools = essential_tools or {
            'deepsearch', 'microsandbox', 'browser_use', 'mcp-search-tool'
        }
        
        # State management
        self.tool_states: Dict[str, ToolHealthInfo] = {}
        self.state_change_callbacks: List[Callable] = []
        
        # Background task management
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._check_interval = 5.0  # seconds
        self._failure_threshold = 3
        
        # Initialize states
        for tool in self.essential_tools:
            self.tool_states[tool] = ToolHealthInfo(
                state=ToolState.INITIALIZING,
                last_check=datetime.now()
            )
        
        logger.info(f"AsyncToolStateManager initialized with {len(self.essential_tools)} essential tools")
    
    async def start_background_monitoring(self):
        """Start background health monitoring (non-blocking)"""
        if self._running:
            logger.warning("Background monitoring already running")
            return
        
        self._running = True
        self._health_check_task = asyncio.create_task(self._background_health_loop())
        logger.info("Started background tool health monitoring")
    
    async def stop_background_monitoring(self):
        """Stop background monitoring gracefully"""
        if not self._running:
            return
        
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped background tool health monitoring")
    
    def is_ready(self, tool_name: str) -> bool:
        """
        Instant, non-blocking check if tool is ready
        
        This replaces wait_for_tools_ready() calls
        """
        if tool_name not in self.tool_states:
            return False
        
        return self.tool_states[tool_name].state == ToolState.READY
    
    def get_tool_state(self, tool_name: str) -> ToolState:
        """Get current tool state"""
        if tool_name not in self.tool_states:
            return ToolState.UNAVAILABLE
        
        return self.tool_states[tool_name].state
    
    def get_all_ready_tools(self) -> Set[str]:
        """Get set of all currently ready tools"""
        return {
            tool for tool, info in self.tool_states.items()
            if info.state == ToolState.READY
        }
    
    def get_health_summary(self) -> Dict[str, str]:
        """Get health summary for all tools"""
        return {
            tool: info.state.value 
            for tool, info in self.tool_states.items()
        }
    
    def are_essential_tools_ready(self) -> bool:
        """Check if all essential tools are ready"""
        ready_tools = self.get_all_ready_tools()
        return self.essential_tools.issubset(ready_tools)
    
    def register_state_change_callback(self, callback: Callable[[str, ToolState, ToolState], None]):
        """Register callback for state changes: callback(tool_name, old_state, new_state)"""
        self.state_change_callbacks.append(callback)
    
    async def _background_health_loop(self):
        """Background loop that continuously monitors tool health"""
        logger.info("Starting background tool health monitoring loop")
        
        while self._running:
            try:
                await self._check_all_tool_health()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background health check: {e}")
                await asyncio.sleep(self._check_interval)
        
        logger.info("Background health monitoring loop stopped")
    
    async def _check_all_tool_health(self):
        """Check health of all monitored tools"""
        try:
            # Get available tools from toolscore
            available_tools = await self.toolscore_client.get_available_tools()
            available_tool_names = set()
            
            # Handle both list and dict responses from get_available_tools()
            if isinstance(available_tools, list):
                # New format: list of tool names like ['server.tool_name']
                for tool_full_name in available_tools:
                    if '.' in tool_full_name:
                        # Extract just the server name (first part before dot)
                        server_name = tool_full_name.split('.')[0]
                        available_tool_names.add(server_name)
                    else:
                        available_tool_names.add(tool_full_name)
            elif isinstance(available_tools, dict) and available_tools.get('success'):
                # Legacy format: dict with success flag and tools data
                tools_data = available_tools.get('tools', {})
                if isinstance(tools_data, dict):
                    available_tool_names = set(tools_data.keys())
                elif isinstance(tools_data, list):
                    available_tool_names = set(tools_data)
            
            # Update states for all monitored tools
            for tool_name in self.tool_states:
                await self._update_tool_state(tool_name, available_tool_names)
                
        except Exception as e:
            logger.error(f"Failed to check tool health: {e}")
            # Mark all tools as unhealthy on check failure
            for tool_name in self.tool_states:
                await self._mark_tool_unhealthy(tool_name, str(e))
    
    async def _update_tool_state(self, tool_name: str, available_tools: Set[str]):
        """Update state for a specific tool"""
        current_info = self.tool_states[tool_name]
        old_state = current_info.state
        new_state = old_state
        
        now = datetime.now()
        current_info.last_check = now
        
        if tool_name in available_tools:
            # Tool is available
            new_state = ToolState.READY
            current_info.consecutive_failures = 0
            current_info.last_success = now
            current_info.error_message = None
        else:
            # Tool is not available
            current_info.consecutive_failures += 1
            
            if current_info.consecutive_failures >= self._failure_threshold:
                new_state = ToolState.UNHEALTHY
                current_info.error_message = f"Tool unavailable for {current_info.consecutive_failures} consecutive checks"
            else:
                # Still in grace period
                new_state = ToolState.INITIALIZING if old_state == ToolState.INITIALIZING else ToolState.UNHEALTHY
        
        # Update state and notify if changed
        if new_state != old_state:
            current_info.state = new_state
            logger.info(f"Tool {tool_name} state changed: {old_state.value} -> {new_state.value}")
            
            # Notify callbacks
            for callback in self.state_change_callbacks:
                try:
                    callback(tool_name, old_state, new_state)
                except Exception as e:
                    logger.error(f"Error in state change callback: {e}")
    
    async def _mark_tool_unhealthy(self, tool_name: str, error_message: str):
        """Mark a tool as unhealthy"""
        if tool_name not in self.tool_states:
            return
        
        current_info = self.tool_states[tool_name]
        old_state = current_info.state
        
        current_info.state = ToolState.UNHEALTHY
        current_info.consecutive_failures += 1
        current_info.error_message = error_message
        current_info.last_check = datetime.now()
        
        if old_state != ToolState.UNHEALTHY:
            logger.warning(f"Tool {tool_name} marked as unhealthy: {error_message}")
            
            # Notify callbacks
            for callback in self.state_change_callbacks:
                try:
                    callback(tool_name, old_state, ToolState.UNHEALTHY)
                except Exception as e:
                    logger.error(f"Error in state change callback: {e}")