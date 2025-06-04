#!/usr/bin/env python3
"""
Web Runtime网络连接测试脚本
"""

import asyncio
import logging
import socket
import subprocess
import urllib.request
import ssl
from typing import List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_dns_resolution(domains: List[str]) -> List[Tuple[str, bool, str]]:
    """测试DNS解析"""
    results = []
    for domain in domains:
        try:
            ip = socket.gethostbyname(domain)
            results.append((domain, True, ip))
            logger.info(f"✅ DNS解析成功: {domain} -> {ip}")
        except Exception as e:
            results.append((domain, False, str(e)))
            logger.error(f"❌ DNS解析失败: {domain} -> {e}")
    return results

async def test_http_connectivity(urls: List[str]) -> List[Tuple[str, bool, str]]:
    """测试HTTP连接"""
    results = []
    for url in urls:
        try:
            # 创建SSL上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # 测试连接
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                status = response.status
                results.append((url, True, f"HTTP {status}"))
                logger.info(f"✅ HTTP连接成功: {url} -> {status}")
        except Exception as e:
            results.append((url, False, str(e)))
            logger.error(f"❌ HTTP连接失败: {url} -> {e}")
    return results

async def test_network_tools():
    """测试网络工具可用性"""
    tools = ['ping', 'nslookup', 'curl', 'wget']
    available_tools = []
    
    for tool in tools:
        try:
            result = subprocess.run([tool, '--version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                available_tools.append(tool)
                logger.info(f"✅ 网络工具可用: {tool}")
            else:
                logger.warning(f"⚠️ 网络工具不可用: {tool}")
        except Exception as e:
            logger.warning(f"⚠️ 网络工具测试失败: {tool} -> {e}")
    
    return available_tools

async def test_ping_connectivity(hosts: List[str]) -> List[Tuple[str, bool, str]]:
    """测试ping连通性"""
    results = []
    for host in hosts:
        try:
            result = subprocess.run(['ping', '-c', '3', host], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=15)
            if result.returncode == 0:
                results.append((host, True, "ping successful"))
                logger.info(f"✅ Ping成功: {host}")
            else:
                results.append((host, False, result.stderr))
                logger.error(f"❌ Ping失败: {host} -> {result.stderr}")
        except Exception as e:
            results.append((host, False, str(e)))
            logger.error(f"❌ Ping异常: {host} -> {e}")
    return results

async def main():
    """主测试函数"""
    logger.info("🎯 开始Web Runtime网络连接诊断")
    logger.info("=" * 70)
    
    # 测试域名列表
    test_domains = [
        'google.com',
        'github.com',
        'python.org',
        'stackoverflow.com'
    ]
    
    # 测试URL列表
    test_urls = [
        'https://www.google.com',
        'https://github.com',
        'https://httpbin.org/get'
    ]
    
    # 测试ping目标
    ping_hosts = [
        '8.8.8.8',        # Google DNS
        '1.1.1.1',        # Cloudflare DNS
        'google.com'
    ]
    
    try:
        # 1. 测试网络工具
        logger.info("\n🔧 测试网络工具...")
        available_tools = await test_network_tools()
        
        # 2. 测试DNS解析
        logger.info("\n🔍 测试DNS解析...")
        dns_results = await test_dns_resolution(test_domains)
        
        # 3. 测试ping连通性
        if 'ping' in available_tools:
            logger.info("\n📡 测试ping连通性...")
            ping_results = await test_ping_connectivity(ping_hosts)
        else:
            logger.warning("\n⚠️ ping工具不可用，跳过ping测试")
            ping_results = []
        
        # 4. 测试HTTP连接
        logger.info("\n🌐 测试HTTP连接...")
        http_results = await test_http_connectivity(test_urls)
        
        # 5. 总结报告
        logger.info("\n" + "=" * 70)
        logger.info("📊 网络诊断总结")
        logger.info("=" * 70)
        
        dns_success = sum(1 for _, success, _ in dns_results if success)
        ping_success = sum(1 for _, success, _ in ping_results if success)
        http_success = sum(1 for _, success, _ in http_results if success)
        
        logger.info(f"DNS解析: {dns_success}/{len(dns_results)} 成功")
        logger.info(f"Ping连通: {ping_success}/{len(ping_results)} 成功")
        logger.info(f"HTTP连接: {http_success}/{len(http_results)} 成功")
        
        # 6. 问题诊断和建议
        if dns_success == 0:
            logger.error("🚨 DNS解析完全失败 - 可能是DNS配置问题")
            logger.info("💡 建议: 检查docker-compose.yml中的dns配置")
        elif http_success == 0:
            logger.error("🚨 HTTP连接完全失败 - 可能是防火墙或代理问题")
            logger.info("💡 建议: 检查企业网络代理设置")
        elif http_success < len(http_results):
            logger.warning("⚠️ 部分HTTP连接失败 - 可能是特定网站被阻止")
        else:
            logger.info("🎉 网络连接正常！Web Runtime应该能正常工作")
            
    except Exception as e:
        logger.error(f"❌ 网络诊断过程中发生错误: {e}")
        import traceback
        logger.error(f"完整错误信息: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(main())