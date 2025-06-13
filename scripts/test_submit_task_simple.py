#!/usr/bin/env python3
"""简化的任务提交测试脚本"""
import requests
import json
import time
import sys

def test_task_submission():
    task_api_url = "http://localhost:8000"
    
    # 提交任务
    payload = {
        "task_type": "code",
        "input": "请用 python 计算 6*20 并输出结果"
    }
    
    print("📤 提交任务...")
    try:
        r = requests.post(f"{task_api_url}/api/v1/tasks", json=payload, timeout=10)
        print(f"状态码: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            task_id = data["task_id"]
            print(f"✅ 任务已提交: {task_id}")
            
            # 轮询状态
            for i in range(30):  # 轮询30次
                time.sleep(2)
                try:
                    resp = requests.get(f"{task_api_url}/api/v1/tasks/{task_id}", timeout=5)
                    if resp.status_code == 200:
                        status_info = resp.json()
                        status = status_info.get("status")
                        print(f"⏳ [{i+1}/30] status={status}")
                        if status == "completed":
                            print("🎉 任务完成!")
                            result = status_info.get("result")
                            if result:
                                print("结果:", json.dumps(result, ensure_ascii=False, indent=2))
                            return
                        elif status == "failed":
                            print("❌ 任务失败")
                            print("详情:", status_info)
                            return
                except Exception as e:
                    print(f"查询失败: {e}")
            
            print("⚠️ 轮询超时")
        else:
            print(f"❌ 提交失败: {r.status_code}")
            print("响应:", r.text)
    except Exception as e:
        print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    test_task_submission() 