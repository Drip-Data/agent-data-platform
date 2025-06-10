#!/usr/bin/env python3
"""
简单的图像生成MCP服务器
提供基本的图像生成和操作功能
"""

import json
import sys
import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from PIL import Image, ImageDraw, ImageFont
import io
import base64

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleImageMCPServer:
    """简单的图像生成MCP服务器"""
    
    def __init__(self):
        self.name = "Simple Image Generator"
        self.version = "1.0.0"
    
    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理初始化请求"""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": True
                },
                "resources": {}
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version
            }
        }
    
    async def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出可用工具"""
        return {
            "tools": [
                {
                    "name": "generate_simple_image",
                    "description": "生成简单的彩色图像，带有自定义文字",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "要在图像上显示的文字"
                            },
                            "background_color": {
                                "type": "string",
                                "description": "背景颜色 (如: red, blue, green, orange)",
                                "default": "lightblue"
                            },
                            "text_color": {
                                "type": "string", 
                                "description": "文字颜色",
                                "default": "black"
                            },
                            "width": {
                                "type": "integer",
                                "description": "图像宽度",
                                "default": 400
                            },
                            "height": {
                                "type": "integer",
                                "description": "图像高度", 
                                "default": 300
                            }
                        },
                        "required": ["text"]
                    }
                },
                {
                    "name": "create_pattern_image",
                    "description": "创建带有图案的装饰性图像",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "图案类型: circles, squares, stripes",
                                "default": "circles"
                            },
                            "color1": {
                                "type": "string",
                                "description": "主要颜色",
                                "default": "blue"
                            },
                            "color2": {
                                "type": "string",
                                "description": "次要颜色", 
                                "default": "white"
                            }
                        }
                    }
                }
            ]
        }
    
    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "generate_simple_image":
                return await self._generate_simple_image(arguments)
            elif tool_name == "create_pattern_image":
                return await self._create_pattern_image(arguments)
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"未知工具: {tool_name}"
                        }
                    ],
                    "isError": True
                }
        except Exception as e:
            logger.error(f"工具调用错误: {e}")
            return {
                "content": [
                    {
                        "type": "text", 
                        "text": f"工具执行失败: {str(e)}"
                    }
                ],
                "isError": True
            }
    
    async def _generate_simple_image(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """生成简单图像"""
        text = args.get("text", "Hello World")
        bg_color = args.get("background_color", "lightblue")
        text_color = args.get("text_color", "black")
        width = args.get("width", 400)
        height = args.get("height", 300)
        
        # 创建图像
        image = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(image)
        
        # 尝试加载字体，失败则使用默认字体
        try:
            font_size = min(width, height) // 10
            font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # 计算文字位置（居中）
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # 绘制文字
        draw.text((x, y), text, fill=text_color, font=font)
        
        # 添加装饰元素
        draw.rectangle([10, 10, width-10, height-10], outline="darkblue", width=3)
        
        # 转换为base64
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"✅ 成功生成图像: {width}x{height}像素，背景色{bg_color}，显示文字「{text}」"
                },
                {
                    "type": "image",
                    "data": f"data:image/png;base64,{img_base64}",
                    "mimeType": "image/png"
                }
            ]
        }
    
    async def _create_pattern_image(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """创建图案图像"""
        pattern = args.get("pattern", "circles")
        color1 = args.get("color1", "blue")
        color2 = args.get("color2", "white")
        width, height = 400, 300
        
        # 创建图像
        image = Image.new("RGB", (width, height), color2)
        draw = ImageDraw.Draw(image)
        
        if pattern == "circles":
            # 绘制圆形图案
            for x in range(0, width, 60):
                for y in range(0, height, 60):
                    draw.ellipse([x+10, y+10, x+50, y+50], fill=color1)
        elif pattern == "squares":
            # 绘制方形图案
            for x in range(0, width, 60):
                for y in range(0, height, 60):
                    draw.rectangle([x+10, y+10, x+50, y+50], fill=color1)
        elif pattern == "stripes":
            # 绘制条纹图案
            for x in range(0, width, 40):
                draw.rectangle([x, 0, x+20, height], fill=color1)
        
        # 转换为base64
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"✅ 成功创建{pattern}图案，使用颜色{color1}和{color2}"
                },
                {
                    "type": "image",
                    "data": f"data:image/png;base64,{img_base64}",
                    "mimeType": "image/png"
                }
            ]
        }
    
    async def run_stdio(self):
        """运行stdio模式的MCP服务器"""
        logger.info(f"启动 {self.name} v{self.version}")
        
        while True:
            try:
                # 读取JSON-RPC消息
                line = input()
                if not line.strip():
                    continue
                
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # 处理消息
                response = await self.handle_message(message)
                if response:
                    print(json.dumps(response))
                    sys.stdout.flush()
                    
            except EOFError:
                break
            except Exception as e:
                logger.error(f"处理消息时发生错误: {e}")
    
    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理JSON-RPC消息"""
        method = message.get("method")
        params = message.get("params", {})
        request_id = message.get("id")
        
        result = None
        error = None
        
        try:
            if method == "initialize":
                result = await self.handle_initialize(params)
            elif method == "tools/list":
                result = await self.handle_tools_list(params)
            elif method == "tools/call":
                result = await self.handle_tools_call(params)
            else:
                error = {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
        except Exception as e:
            logger.error(f"处理方法 {method} 时发生错误: {e}")
            error = {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        
        if request_id is not None:
            response = {
                "jsonrpc": "2.0",
                "id": request_id
            }
            if error:
                response["error"] = error
            else:
                response["result"] = result
            return response
        
        return None


async def main():
    """主函数"""
    server = SimpleImageMCPServer()
    
    # 检查是否在Docker容器中
    if os.getenv("DOCKER_CONTAINER"):
        logger.info("在Docker容器中运行，启动HTTP服务器模式")
        
        # 简单的HTTP健康检查服务器
        import http.server
        import socketserver
        import threading
        
        class HealthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "healthy",
                        "server": "Simple Image MCP Server",
                        "timestamp": datetime.now().isoformat()
                    }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
        
        port = int(os.getenv("MCP_SERVER_PORT", 8080))
        httpd = socketserver.TCPServer(("", port), HealthHandler)
        
        # 在后台运行HTTP服务器
        http_thread = threading.Thread(target=httpd.serve_forever)
        http_thread.daemon = True
        http_thread.start()
        
        logger.info(f"HTTP健康检查服务器运行在端口 {port}")
        logger.info("主要MCP服务器运行在stdio模式")
    
    # 运行主要的MCP服务器
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main()) 