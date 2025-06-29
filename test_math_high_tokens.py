#!/usr/bin/env python3

import asyncio
import sys
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config_manager import ConfigManager
from core.llm_client import LLMClient  
from core.toolscore.toolscore_client import ToolScoreClient
from runtimes.reasoning.simple_runtime import SimpleReasoningRuntime
from core.interfaces import TaskSpec, TaskType

async def test_complex_math():
    """Test complex math problem with increased token limit"""
    
    # Initialize components
    config_manager = ConfigManager("config")
    
    # Create LLM client with increased max_tokens
    llm_client = LLMClient(config_manager.get_llm_config())
    
    # Create ToolScore client
    toolscore_client = ToolScoreClient(config_manager)
    
    # Create simple runtime with XML streaming
    runtime = SimpleReasoningRuntime(
        config_manager=config_manager,
        llm_client=llm_client, 
        toolscore_client=toolscore_client,
        xml_streaming_mode=True
    )
    
    # Create task
    task = TaskSpec(
        task_id="math-polynomial-high-tokens-test",
        description="""Solve the following very hard math problem using your in-built knowledge of the literature. You MUST use python code to solve some technical calculations during your analysis: Construct a degree 19 polynomial p(x) in C[x] such that X := {p(x) = p(y)} subset P^1 times P^1 has at least 3 (but not all linear) irreducible components over C. Choose p(x) to be odd, monic, have real coefficients and linear coefficient (-19) and calculate p(19)""",
        task_type=TaskType.REASONING
    )
    
    print(f"🧮 Starting complex math test with increased token limit...")
    print(f"📝 Task ID: {task.task_id}")
    
    try:
        # Execute task
        result = await runtime.execute(task)
        
        print(f"✅ Task completed successfully!")
        print(f"🎯 Success: {result.success}")
        print(f"📊 Duration: {result.total_duration:.2f}s")
        
        if result.success:
            print(f"🔍 Final result: {result.final_result}")
            
            # Check trajectory file
            trajectory_file = f"output/trajectories/{task.task_id}_raw.txt"
            if Path(trajectory_file).exists():
                print(f"📄 Raw trajectory saved to: {trajectory_file}")
                
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
                else:
                    print("⚠️ No tool calls detected")
                    
                # Check if response was truncated
                if content.endswith("--------------------------------------------------\n最终结果: 任务执行完成，已输出原始XML轨迹格式\n"):
                    print("✅ Response completed normally")
                else:
                    print("⚠️ Response may have been truncated")
            else:
                print(f"❌ Trajectory file not found: {trajectory_file}")
        else:
            print(f"❌ Task failed: {result.error_message}")
            
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_complex_math())