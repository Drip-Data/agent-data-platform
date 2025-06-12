import json
import sys

def clean_embeddings_thoroughly():
    """彻底删除JSON文件中的所有embedding字段"""
    
    input_file = '/Users/muz1lee/Downloads/mcp_tools_with_embedding.json'
    output_file = 'mcp_tools.json'
    
    try:
        # 读取原始文件
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"读取原始文件，包含 {len(data)} 个条目")
        
        # 彻底清理embedding
        cleaned_data = []
        total_embeddings_removed = 0
        
        for item in data:
            cleaned_item = {}
            
            # 复制非embedding字段
            for key, value in item.items():
                if 'embedding' not in key.lower():
                    cleaned_item[key] = value
                else:
                    total_embeddings_removed += 1
                    print(f"删除顶层embedding字段: {key}")
            
            # 特别处理tools数组
            if 'tools' in cleaned_item:
                cleaned_tools = []
                for tool in cleaned_item['tools']:
                    cleaned_tool = {}
                    tool_embeddings_removed = 0
                    
                    # 复制非embedding字段
                    for key, value in tool.items():
                        if 'embedding' not in key.lower():
                            cleaned_tool[key] = value
                        else:
                            tool_embeddings_removed += 1
                            total_embeddings_removed += 1
                    
                    if tool_embeddings_removed > 0:
                        print(f"  删除工具embedding字段: {tool_embeddings_removed} 个")
                    
                    cleaned_tools.append(cleaned_tool)
                
                cleaned_item['tools'] = cleaned_tools
            
            cleaned_data.append(cleaned_item)
        
        # 保存清理后的文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        
        print(f'\n✅ 清理完成!')
        print(f'📊 处理了 {len(cleaned_data)} 个MCP服务器条目')
        print(f'🗑️  删除了 {total_embeddings_removed} 个embedding字段')
        
        # 显示文件大小对比
        import os
        original_size = os.path.getsize(input_file)
        new_size = os.path.getsize(output_file)
        print(f'📁 原始文件大小: {original_size / (1024*1024):.1f} MB')
        print(f'📁 新文件大小: {new_size / (1024*1024):.1f} MB')
        print(f'💾 节省空间: {(original_size - new_size) / (1024*1024):.1f} MB')
        
        # 验证清理结果
        print(f'\n🔍 验证清理结果...')
        with open(output_file, 'r', encoding='utf-8') as f:
            verification_data = json.load(f)
        
        # 检查是否还有embedding字段
        embedding_found = False
        for item in verification_data:
            # 检查顶层
            for key in item.keys():
                if 'embedding' in key.lower():
                    print(f"❌ 发现残留的顶层embedding: {key}")
                    embedding_found = True
            
            # 检查tools中的embedding
            if 'tools' in item:
                for tool in item['tools']:
                    for key in tool.keys():
                        if 'embedding' in key.lower():
                            print(f"❌ 发现残留的工具embedding: {key}")
                            embedding_found = True
        
        if not embedding_found:
            print("✅ 验证通过：未发现任何embedding字段")
        
        return True
        
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        return False

if __name__ == "__main__":
    clean_embeddings_thoroughly() 