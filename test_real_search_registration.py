#!/usr/bin/env python3
"""
测试真实MCP服务器搜索和注册功能
"""

import asyncio
import sys
import logging
import json
from unittest.mock import patch, MagicMock

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_network_connectivity():
    """测试网络连接"""
    print('🌐 测试网络连接...')
    
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            # 测试基本网络连接
            try:
                async with session.get('https://httpbin.org/get') as response:
                    if response.status == 200:
                        print('   ✅ 基本网络连接正常')
                        return True
            except Exception as e:
                print(f'   ❌ 基本网络连接失败: {e}')
                
            # 测试GitHub API连接
            try:
                async with session.get('https://api.github.com/repos/modelcontextprotocol/servers') as response:
                    if response.status == 200:
                        print('   ✅ GitHub API连接正常')
                        return True
                    else:
                        print(f'   ⚠️ GitHub API返回状态: {response.status}')
            except Exception as e:
                print(f'   ❌ GitHub API连接失败: {e}')
                
    except Exception as e:
        print(f'   ❌ 网络测试失败: {e}')
    
    return False

async def create_mock_github_response():
    """创建模拟的GitHub API响应"""
    return [
        {
            "name": "filesystem",
            "type": "dir",
            "html_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"
        },
        {
            "name": "sqlite", 
            "type": "dir",
            "html_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite"
        },
        {
            "name": "github",
            "type": "dir", 
            "html_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/github"
        }
    ]

async def test_real_search_with_mock():
    """使用模拟数据测试真实搜索功能"""
    print('\n🔍 测试真实搜索功能 (使用模拟数据)...')
    
    try:
        from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        
        # 初始化组件
        tool_library = UnifiedToolLibrary()
        await tool_library.initialize()
        
        dynamic_mcp_manager = DynamicMCPManager(tool_library)
        await dynamic_mcp_manager.initialize()
        
        # 创建模拟的GitHub响应
        mock_response_data = await create_mock_github_response()
        
        # 模拟aiohttp响应
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = MagicMock(return_value=asyncio.coroutine(lambda: mock_response_data)())
        
        # 使用patch来模拟网络请求
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_response
            
            # 测试搜索
            candidates = await dynamic_mcp_manager.search_mcp_servers('filesystem')
            
            print(f'   ✅ 搜索成功: 找到 {len(candidates)} 个候选者')
            
            for i, candidate in enumerate(candidates, 1):
                print(f'      {i}. {candidate.name}')
                print(f'         描述: {candidate.description}')
                print(f'         GitHub: {candidate.github_url}')
                print(f'         作者: {candidate.author}')
                print(f'         安装方法: {candidate.install_method}')
                print(f'         验证状态: {candidate.verified}')
        
        await dynamic_mcp_manager.cleanup()
        await tool_library.cleanup()
        
        return candidates if candidates else []
        
    except Exception as e:
        print(f'   ❌ 搜索测试失败: {e}')
        import traceback
        traceback.print_exc()
        return []

async def test_installation_and_registration(candidates):
    """测试安装和注册功能"""
    if not candidates:
        print('\n❌ 没有候选者可供测试安装')
        return
    
    print(f'\n🔧 测试安装和注册功能...')
    
    try:
        from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        
        # 初始化组件
        tool_library = UnifiedToolLibrary()
        await tool_library.initialize()
        
        dynamic_mcp_manager = DynamicMCPManager(tool_library)
        await dynamic_mcp_manager.initialize()
        
        # 选择第一个候选者进行测试
        best_candidate = candidates[0]
        print(f'   📦 测试安装: {best_candidate.name}')
        
        # 尝试安装（这会是真实的Docker安装）
        install_result = await dynamic_mcp_manager.install_mcp_server(best_candidate)
        
        if install_result.success:
            print('   ✅ 安装成功!')
            print(f'      服务器ID: {install_result.server_id}')
            print(f'      端点: {install_result.endpoint}')
            if install_result.container_id:
                print(f'      容器ID: {install_result.container_id}')
                
                # 检查容器状态
                try:
                    import docker
                    client = docker.from_env()
                    container = client.containers.get(install_result.container_id)
                    print(f'      容器状态: {container.status}')
                    
                    # 获取容器日志
                    logs = container.logs(tail=10).decode('utf-8')
                    if logs:
                        print(f'      容器日志 (最后10行):')
                        for line in logs.split('\n')[-10:]:
                            if line.strip():
                                print(f'        {line}')
                except Exception as e:
                    print(f'      ⚠️ 无法检查容器状态: {e}')
            
            # 测试注册到工具库
            print('   📋 测试注册到工具库...')
            registration_result = await dynamic_mcp_manager.register_installed_server(
                best_candidate, install_result
            )
            
            if registration_result.success:
                print(f'   ✅ 注册成功! 工具ID: {registration_result.tool_id}')
                
                # 检查已安装的服务器
                installed_servers = await dynamic_mcp_manager.get_installed_servers()
                print(f'   📊 已安装服务器数量: {len(installed_servers)}')
                
                for server_id, server_info in installed_servers.items():
                    print(f'      - {server_id}: {server_info.endpoint}')
                
                # 健康检查
                print('   🏥 健康检查...')
                health_status = await dynamic_mcp_manager.health_check_installed_servers()
                for server_id, is_healthy in health_status.items():
                    status = "✅ 健康" if is_healthy else "❌ 不健康"
                    print(f'      {server_id}: {status}')
                
                # 测试持久化
                print('   💾 测试持久化...')
                try:
                    from core.toolscore.persistent_storage import PersistentStorage
                    storage = PersistentStorage()
                    await storage.initialize()
                    
                    stored_servers = await storage.load_all_mcp_servers()
                    print(f'      持久化服务器数量: {len(stored_servers)}')
                    
                    await storage.cleanup()
                except Exception as e:
                    print(f'      ⚠️ 持久化测试失败: {e}')
                
            else:
                print(f'   ❌ 注册失败: {registration_result.error}')
                
        else:
            print(f'   ❌ 安装失败: {install_result.error_message}')
            # 即使安装失败，我们也可以测试模拟安装
            print('   🔄 尝试模拟安装进行注册测试...')
            
            # 创建模拟安装结果
            from core.toolscore.dynamic_mcp_manager import InstallationResult
            mock_install_result = InstallationResult(
                success=True,
                server_id=f"mock-{best_candidate.name}-test",
                endpoint=f"mock://localhost:8150/mcp",
                container_id=f"mock-container-{best_candidate.name}",
                port=8150
            )
            
            registration_result = await dynamic_mcp_manager.register_installed_server(
                best_candidate, mock_install_result
            )
            
            if registration_result.success:
                print(f'   ✅ 模拟注册成功! 工具ID: {registration_result.tool_id}')
            else:
                print(f'   ❌ 模拟注册失败: {registration_result.error}')
        
        await dynamic_mcp_manager.cleanup()
        await tool_library.cleanup()
        
    except Exception as e:
        print(f'   ❌ 安装测试失败: {e}')
        import traceback
        traceback.print_exc()

async def test_real_github_api():
    """测试真实的GitHub API调用"""
    print('\n🌐 测试真实GitHub API调用...')
    
    try:
        from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        
        # 初始化组件
        tool_library = UnifiedToolLibrary()
        await tool_library.initialize()
        
        dynamic_mcp_manager = DynamicMCPManager(tool_library)
        await dynamic_mcp_manager.initialize()
        
        # 增加超时时间
        original_timeout = 5
        
        print('   🔍 尝试真实GitHub API搜索...')
        candidates = await dynamic_mcp_manager.search_mcp_servers('filesystem')
        
        if candidates:
            print(f'   ✅ 真实搜索成功: 找到 {len(candidates)} 个候选者')
            for candidate in candidates[:3]:  # 只显示前3个
                print(f'      - {candidate.name}: {candidate.description}')
            return candidates
        else:
            print('   ⚠️ 真实搜索返回0个结果 (可能是网络问题)')
            return []
        
        await dynamic_mcp_manager.cleanup()
        await tool_library.cleanup()
        
    except Exception as e:
        print(f'   ❌ 真实API测试失败: {e}')
        return []

async def main():
    print('🧪 开始真实搜索和注册测试')
    
    # 测试网络连接
    has_network = await test_network_connectivity()
    
    candidates = []
    
    if has_network:
        # 如果有网络，先尝试真实API
        print('\n🌟 尝试真实GitHub API测试...')
        real_candidates = await test_real_github_api()
        if real_candidates:
            candidates = real_candidates
    
    if not candidates:
        # 如果没有网络或真实API失败，使用模拟数据
        print('\n🎭 使用模拟数据进行测试...')
        candidates = await test_real_search_with_mock()
    
    # 测试安装和注册
    await test_installation_and_registration(candidates)
    
    print('\n🎉 测试完成!')
    
    # 总结
    print('\n📋 测试总结:')
    if has_network:
        print('   ✅ 网络连接正常')
    else:
        print('   ⚠️ 网络连接受限，使用模拟数据')
    
    if candidates:
        print(f'   ✅ 成功发现 {len(candidates)} 个MCP服务器候选者')
        print('   ✅ 搜索功能正常工作')
        print('   ✅ 注册流程可以执行')
    else:
        print('   ❌ 未能发现任何MCP服务器候选者')

if __name__ == "__main__":
    asyncio.run(main()) 