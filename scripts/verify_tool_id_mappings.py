#!/usr/bin/env python3
"""
Tool ID Mapping Verification Script
Verifies that all tool ID mappings are correctly updated throughout the system.
"""

import os
import sys
import json
import yaml
import asyncio
import aiohttp
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Tool ID mappings
OLD_TO_NEW_TOOL_IDS = {
    'mcp-deepsearch': 'deepsearch',
    'microsandbox-mcp-server': 'microsandbox',
    'browser-use-mcp-server': 'browser_use',
    'mcp-search-tool': 'mcp-search-tool'  # This one doesn't change
}

NEW_TOOL_IDS = ['deepsearch', 'microsandbox', 'browser_use', 'mcp-search-tool']
OLD_TOOL_IDS = ['mcp-deepsearch', 'microsandbox-mcp-server', 'browser-use-mcp-server', 'mcp-search-tool']

def check_file_for_old_tool_ids(file_path: Path, ignore_patterns=None):
    """Check a file for old tool ID references."""
    if ignore_patterns is None:
        ignore_patterns = []
    
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        for line_num, line in enumerate(content.split('\n'), 1):
            # Skip lines that match ignore patterns
            if any(pattern in line for pattern in ignore_patterns):
                continue
                
            for old_id in OLD_TOOL_IDS:
                if old_id in line and old_id != 'mcp-search-tool':
                    issues.append({
                        'file': str(file_path),
                        'line': line_num,
                        'old_id': old_id,
                        'new_id': OLD_TO_NEW_TOOL_IDS[old_id],
                        'content': line.strip()
                    })
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        
    return issues

async def test_toolscore_api():
    """Test the ToolScore API to see what tool IDs it returns."""
    try:
        async with aiohttp.ClientSession() as session:
            # Test the available tools endpoint
            async with session.get('http://localhost:8091/api/v1/tools/available') as response:
                if response.status == 200:
                    data = await response.json()
                    tools = data.get('available_tools', [])
                    
                    print("🔍 ToolScore API Response:")
                    print(f"   Status: {response.status}")
                    print(f"   Tools returned: {len(tools)}")
                    
                    tool_ids = []
                    for tool in tools:
                        if isinstance(tool, dict):
                            tool_id = tool.get('tool_id', tool.get('server_id', 'unknown'))
                            tool_ids.append(tool_id)
                            print(f"   - {tool_id}: {tool.get('name', 'No name')}")
                        else:
                            tool_ids.append(str(tool))
                            print(f"   - {tool}")
                    
                    # Check if we have old tool IDs
                    old_ids_found = [tid for tid in tool_ids if tid in OLD_TOOL_IDS and tid != 'mcp-search-tool']
                    new_ids_found = [tid for tid in tool_ids if tid in NEW_TOOL_IDS]
                    
                    print(f"\n📊 Analysis:")
                    print(f"   Old tool IDs found: {old_ids_found}")
                    print(f"   New tool IDs found: {new_ids_found}")
                    
                    if old_ids_found:
                        print("❌ ISSUE: ToolScore is still returning old tool IDs!")
                        return False
                    elif new_ids_found:
                        print("✅ SUCCESS: ToolScore is returning new tool IDs!")
                        return True
                    else:
                        print("⚠️  WARNING: No expected tool IDs found")
                        return False
                else:
                    print(f"❌ ToolScore API error: HTTP {response.status}")
                    return False
                    
    except Exception as e:
        print(f"❌ ToolScore API test failed: {e}")
        return False

def main():
    """Main verification function."""
    print("🔍 Verifying Tool ID Mappings")
    print("=" * 50)
    
    # Files to check for old tool ID references
    files_to_check = [
        project_root / "core" / "toolscore" / "parameter_validator.py",
        project_root / "config" / "tool_aliases.yaml",
        project_root / "runtimes" / "reasoning" / "enhanced_runtime.py",
        project_root / "core" / "toolscore" / "monitoring_api.py",
        project_root / "runtimes" / "reasoning" / "toolscore_client.py",
        project_root / "runtimes" / "reasoning" / "real_time_tool_client.py",
    ]
    
    # Patterns to ignore (comments, documentation, etc.)
    ignore_patterns = [
        '# ',  # Comments
        '"""',  # Docstrings
        "'''",  # Docstrings
        'logger.',  # Log messages
        'print(',  # Debug prints
    ]
    
    all_issues = []
    
    print("📁 Checking files for old tool ID references...")
    for file_path in files_to_check:
        if file_path.exists():
            issues = check_file_for_old_tool_ids(file_path, ignore_patterns)
            all_issues.extend(issues)
            
            if issues:
                print(f"   ❌ {file_path.name}: {len(issues)} issues")
            else:
                print(f"   ✅ {file_path.name}: Clean")
        else:
            print(f"   ⚠️  {file_path.name}: File not found")
    
    # Print detailed issues
    if all_issues:
        print("\n🚨 Issues Found:")
        for issue in all_issues:
            print(f"   File: {issue['file']}")
            print(f"   Line {issue['line']}: {issue['content']}")
            print(f"   Should change '{issue['old_id']}' to '{issue['new_id']}'")
            print()
    
    # Check configuration files
    print("\n📋 Checking configuration consistency...")
    
    # Check tool_aliases.yaml
    tool_aliases_path = project_root / "config" / "tool_aliases.yaml"
    if tool_aliases_path.exists():
        try:
            with open(tool_aliases_path, 'r', encoding='utf-8') as f:
                aliases_config = yaml.safe_load(f)
            
            # Check parameter_aliases section
            param_aliases = aliases_config.get('parameter_aliases', {})
            expected_new_tools = ['deepsearch', 'microsandbox', 'browser_use', 'mcp-search-tool']
            found_new_tools = [tool for tool in expected_new_tools if tool in param_aliases]
            
            print(f"   ✅ tool_aliases.yaml: Found {len(found_new_tools)}/{len(expected_new_tools)} new tool IDs")
            
        except Exception as e:
            print(f"   ❌ tool_aliases.yaml: Error reading file - {e}")
    else:
        print(f"   ⚠️  tool_aliases.yaml: File not found")
    
    # Summary
    print("\n📊 Summary:")
    print(f"   Files checked: {len(files_to_check)}")
    print(f"   Issues found: {len(all_issues)}")
    
    if all_issues:
        print("\n❌ Verification FAILED - Issues need to be fixed")
        return False
    else:
        print("\n✅ Verification PASSED - All files clean")
        return True

async def async_main():
    """Async main function to test APIs."""
    print("🔍 Verifying Tool ID Mappings")
    print("=" * 50)
    
    # Run file verification
    file_check_passed = main()
    
    # Test ToolScore API if available
    print("\n🌐 Testing ToolScore API...")
    api_check_passed = await test_toolscore_api()
    
    print("\n" + "=" * 50)
    print("🎯 Final Results:")
    print(f"   File verification: {'✅ PASSED' if file_check_passed else '❌ FAILED'}")
    print(f"   API verification: {'✅ PASSED' if api_check_passed else '❌ FAILED'}")
    
    overall_success = file_check_passed and api_check_passed
    print(f"   Overall: {'✅ SUCCESS' if overall_success else '❌ NEEDS ATTENTION'}")
    
    return overall_success

if __name__ == "__main__":
    try:
        result = asyncio.run(async_main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Verification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Verification failed with error: {e}")
        sys.exit(1)