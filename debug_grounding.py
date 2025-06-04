#!/usr/bin/env python3
"""
Gemini 2.0 grounding_metadata结构调试脚本
"""

import os
import asyncio
import logging
from google.genai import Client
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_grounding_structure():
    """调试grounding_metadata的实际结构"""
    try:
        # 硬编码API密钥用于调试
        api_key = "AIzaSyDbiXNxcSvPEK2UnObGjHFkY3g3xuA-lTs"
        logger.info("✅ 使用硬编码API密钥")
        
        # 创建客户端
        client = Client(api_key=api_key)
        
        # 使用Google Search工具进行搜索
        logger.info("🔍 执行搜索以调试grounding_metadata结构...")
        google_search_tool = Tool(google_search=GoogleSearch())
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents="请搜索AAPL股票的最新市值信息",
            config=GenerateContentConfig(
                tools=[google_search_tool],
                response_modalities=["TEXT"],
                temperature=0,
            ),
        )
        
        logger.info("✅ 搜索API调用成功")
        
        # 详细分析响应结构
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            logger.info(f"📊 Candidate类型: {type(candidate)}")
            logger.info(f"📊 Candidate可用属性: {[attr for attr in dir(candidate) if not attr.startswith('_')]}")
            
            # 检查grounding_metadata
            if hasattr(candidate, 'grounding_metadata'):
                grounding_metadata = candidate.grounding_metadata
                logger.info(f"📊 grounding_metadata存在: {grounding_metadata is not None}")
                
                if grounding_metadata:
                    logger.info(f"📊 grounding_metadata类型: {type(grounding_metadata)}")
                    logger.info(f"📊 grounding_metadata属性: {[attr for attr in dir(grounding_metadata) if not attr.startswith('_')]}")
                    
                    # 检查search_entry_point（官方示例中的方式）
                    if hasattr(grounding_metadata, 'search_entry_point'):
                        search_entry = grounding_metadata.search_entry_point
                        logger.info(f"📊 search_entry_point: {search_entry is not None}")
                        
                        if search_entry:
                            logger.info(f"📊 search_entry类型: {type(search_entry)}")
                            logger.info(f"📊 search_entry属性: {[attr for attr in dir(search_entry) if not attr.startswith('_')]}")
                            
                            # 检查rendered_content
                            if hasattr(search_entry, 'rendered_content'):
                                rendered_content = search_entry.rendered_content
                                logger.info(f"📊 rendered_content长度: {len(rendered_content) if rendered_content else 0}")
                                if rendered_content:
                                    logger.info(f"📊 rendered_content前200字符: {rendered_content[:200]}...")
                                    return True
                    
                    # 检查grounding_chunks（旧方式）
                    if hasattr(grounding_metadata, 'grounding_chunks'):
                        grounding_chunks = grounding_metadata.grounding_chunks
                        logger.info(f"📊 grounding_chunks: {grounding_chunks is not None}")
                        if grounding_chunks:
                            logger.info(f"📊 grounding_chunks长度: {len(grounding_chunks)}")
                            logger.info(f"📊 grounding_chunks类型: {type(grounding_chunks)}")
                            if len(grounding_chunks) > 0:
                                logger.info(f"📊 第一个chunk属性: {[attr for attr in dir(grounding_chunks[0]) if not attr.startswith('_')]}")
                                return True
                    
                    # 列出所有可能的属性
                    logger.info("📊 grounding_metadata的所有非私有属性:")
                    for attr in dir(grounding_metadata):
                        if not attr.startswith('_'):
                            value = getattr(grounding_metadata, attr, None)
                            logger.info(f"   {attr}: {type(value)} = {value}")
                else:
                    logger.warning("⚠️ grounding_metadata为空")
            else:
                logger.warning("⚠️ 没有grounding_metadata属性")
        else:
            logger.error("❌ 没有candidates")
            
        return False
            
    except Exception as e:
        logger.error(f"❌ 调试失败: {str(e)}")
        import traceback
        logger.error(f"❌ 完整错误: {traceback.format_exc()}")
        return False

async def main():
    """主函数"""
    logger.info("🎯 开始Gemini 2.0 grounding_metadata结构调试")
    logger.info("=" * 70)
    
    success = await debug_grounding_structure()
    
    logger.info("=" * 70)
    if success:
        logger.info("🎉 找到搜索结果！grounding结构正常")
    else:
        logger.info("💡 可能的原因:")
        logger.info("   1. API密钥没有Google Search权限")
        logger.info("   2. grounding_metadata结构与预期不同")
        logger.info("   3. 搜索结果暂时不可用")

if __name__ == "__main__":
    asyncio.run(main())