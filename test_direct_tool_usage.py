#!/usr/bin/env python3

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config_manager import ConfigManager
from core.llm_client import LLMClient  
from core.toolscore.toolscore_client import ToolScoreClient
from runtimes.reasoning.simple_runtime import SimpleReasoningRuntime
from core.interfaces import TaskSpec, TaskType

async def test_direct_tool_usage():
    """Test with more direct tool usage instructions"""
    
    # Initialize components
    config_manager = ConfigManager("config")
    llm_client = LLMClient(config_manager.get_llm_config())
    toolscore_client = ToolScoreClient(config_manager)
    
    # Create simple runtime with XML streaming and daily grouped storage
    runtime = SimpleReasoningRuntime(
        config_manager=config_manager,
        llm_client=llm_client, 
        toolscore_client=toolscore_client,
        xml_streaming_mode=True,
        trajectory_storage_mode="daily_grouped"
    )
    
    # Create task with very direct instructions
    task = TaskSpec(
        task_id="direct-tool-usage-test",
        description="""First use Python to verify that 2+2=4, then solve this math problem: Calculate the value of the polynomial p(x) = x^19 - 19x when x=19. Start by using Python to calculate this immediately before doing any theoretical analysis.""",
        task_type=TaskType.REASONING
    )
    
    print(f"🔧 Testing direct tool usage...")
    print(f"📝 Task ID: {task.task_id}")
    
    try:
        # Execute task
        result = await runtime.execute(task)
        
        print(f"✅ Task completed!")
        print(f"🎯 Success: {result.success}")
        print(f"📊 Duration: {result.total_duration:.2f}s")
        
        if result.success:
            # Check trajectory file
            trajectory_file = f"output/trajectories/{task.task_id}_raw.txt"
            if Path(trajectory_file).exists():
                print(f"📄 Trajectory saved to: {trajectory_file}")
                
                # Read and analyze trajectory
                with open(trajectory_file, 'r') as f:
                    content = f.read()
                    
                print(f"📏 Trajectory length: {len(content)} characters")
                
                # Check for tool usage
                tool_calls = []
                if '<microsandbox>' in content:
                    tool_calls.append('microsandbox')
                if '<deepsearch>' in content:
                    tool_calls.append('deepsearch')
                if '<browser>' in content:
                    tool_calls.append('browser')
                    
                if tool_calls:
                    print(f"🔧 Tools used: {tool_calls}")
                    print("✅ SUCCESS: Tools were called as expected!")
                else:
                    print("❌ FAILURE: No tool calls detected despite direct instructions")
                    
                # Show first part of trajectory
                lines = content.split('\n')
                print("📖 First 20 lines of trajectory:")
                for i, line in enumerate(lines[:20]):
                    print(f"   {i+1:2}: {line}")
                    
        else:
            print(f"❌ Task failed: {result.error_message}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_tool_usage())