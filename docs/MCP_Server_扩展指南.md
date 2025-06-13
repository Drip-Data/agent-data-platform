# MCP Server 扩展指南

## 🔧 如何添加新的MCP Server

您的Agent Data Platform基于标准MCP协议，支持无限扩展各种工具服务器。

### 📋 当前已注册的MCP Servers

1. **Python Executor Server** (端口: 8083)
   - 功能: Python代码执行、数据分析、可视化
   - 能力: `python_execute`, `python_analyze`, `python_visualize`

2. **ToolScore MCP Server** (端口: 8081) 
   - 功能: 工具管理和调度
   - 能力: 工具注册、状态监控、调用路由

### 🆕 添加新MCP Server的步骤

#### 步骤1: 创建新的MCP Server

```python
# 示例: mcp_servers/web_scraper_server/main.py
import asyncio
import logging
from typing import Dict, Any, List
from core.toolscore.interfaces import ToolCapability, ToolType
from core.toolscore.mcp_server import MCPServer

class WebScraperMCPServer:
    def __init__(self):
        self.server_name = "web_scraper_server" 
        self.server_id = "web-scraper-mcp-server"
        self.endpoint = "ws://0.0.0.0:8084/mcp"  # 新端口
        
    def get_capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name="scrape_url",
                description="抓取网页内容",
                parameters={
                    "url": {"type": "string", "required": True},
                    "selector": {"type": "string", "required": False}
                }
            ),
            ToolCapability(
                name="extract_links", 
                description="提取页面链接",
                parameters={
                    "url": {"type": "string", "required": True}
                }
            )
        ]
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]):
        if action == "scrape_url":
            # 实现网页抓取逻辑
            return await self.scrape_webpage(parameters)
        elif action == "extract_links":
            # 实现链接提取逻辑  
            return await self.extract_page_links(parameters)
    
    # 实现具体的工具方法...
```

#### 步骤2: 在main.py中注册新Server

```python
# main.py 中添加
async def start_web_scraper_server():
    """启动Web Scraper MCP Server"""
    try:
        from mcp_servers.web_scraper_server.main import WebScraperMCPServer
        web_scraper = WebScraperMCPServer()
        await web_scraper.run()
        logger.info("✅ Web Scraper MCP Server启动 (端口: 8084)")
    except Exception as e:
        logger.error(f"Web Scraper MCP Server启动失败: {e}")

# 在main函数中添加
asyncio.create_task(start_web_scraper_server())
```

#### 步骤3: 更新监控API以支持新工具

```python
# core/toolscore/monitoring_api.py 中添加
DIRECT_CALL_SERVERS = {
    "python-executor-mcp-server": python_executor_instance,
    "web-scraper-mcp-server": web_scraper_instance,  # 新增
    # 可以继续添加更多...
}
```

### 🛠️ 常见MCP Server类型示例

#### 1. 文件操作Server
```python
# 能力: 文件读写、目录管理、文档处理
capabilities = ["read_file", "write_file", "list_directory", "parse_pdf"]
```

#### 2. 数据库Server  
```python
# 能力: SQL查询、数据插入、表管理
capabilities = ["execute_sql", "insert_data", "create_table", "backup_db"]
```

#### 3. 图像处理Server
```python 
# 能力: 图像编辑、格式转换、AI识别
capabilities = ["resize_image", "convert_format", "detect_objects", "generate_image"]
```

#### 4. 网络请求Server
```python
# 能力: HTTP请求、API调用、数据获取  
capabilities = ["http_get", "http_post", "api_call", "download_file"]
```

### 📊 MCP Server管理最佳实践

#### 1. 端口管理
```python
# config/mcp_servers.yaml
mcp_servers:
  python_executor:
    port: 8083
    auto_start: true
  web_scraper:
    port: 8084  
    auto_start: true
  file_manager:
    port: 8085
    auto_start: false  # 按需启动
```

#### 2. 健康检查
```python
async def check_mcp_servers_health():
    servers = [
        ("python-executor", "http://localhost:8083/health"),
        ("web-scraper", "http://localhost:8084/health"), 
    ]
    
    for name, url in servers:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ {name} MCP Server健康")
                    else:
                        logger.warning(f"⚠️ {name} MCP Server异常")
        except Exception as e:
            logger.error(f"❌ {name} MCP Server连接失败: {e}")
```

#### 3. 动态注册机制
```python
async def register_mcp_server(server_config: Dict):
    """动态注册新的MCP Server"""
    server_class = import_server_class(server_config["module"])
    server_instance = server_class(server_config)
    
    # 启动服务器
    asyncio.create_task(server_instance.run())
    
    # 注册到工具库
    await toolscore.register_server(server_instance)
    
    logger.info(f"✅ 动态注册MCP Server: {server_config['name']}")
```

### 🔌 第三方MCP Server集成

您还可以集成现有的第三方MCP Servers：

```bash
# 安装第三方MCP Server  
npm install @anthropic/mcp-server-filesystem
npm install @anthropic/mcp-server-git

# 通过配置文件集成
# config/external_mcp_servers.json
{
  "filesystem": {
    "command": "npx @anthropic/mcp-server-filesystem",
    "args": ["/path/to/workspace"],
    "port": 8086
  },
  "git": {
    "command": "npx @anthropic/mcp-server-git", 
    "args": ["--repository", "/path/to/repo"],
    "port": 8087
  }
}
```

通过这种方式，您的平台可以支持:**无限扩展各种专业工具服务器**！ 