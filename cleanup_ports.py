#!/usr/bin/env python3
"""
快速清理端口脚本
"""

import subprocess
import sys

def cleanup_ports():
    """清理所有相关端口"""
    ports = [8088, 8089, 8100, 8081, 8082, 8080]
    
    print("🧹 开始清理端口...")
    
    for port in ports:
        try:
            # 查找占用端口的进程
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, text=True, timeout=3
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                print(f"🔍 端口 {port} 被进程占用: {pids}")
                
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], timeout=2)
                        print(f"   ✅ 已终止进程 {pid}")
                    except Exception as e:
                        print(f"   ❌ 终止进程 {pid} 失败: {e}")
            else:
                print(f"✅ 端口 {port} 未被占用")
                
        except Exception as e:
            print(f"❌ 检查端口 {port} 失败: {e}")
    
    print("🎉 端口清理完成")

if __name__ == "__main__":
    cleanup_ports()