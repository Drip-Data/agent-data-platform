#!/usr/bin/env python3
"""提交测试任务到 Task API 并轮询结果"""
import httpx, asyncio, json, time, sys

def usage():
    print("Usage: python test_submit_task.py '任务描述'")
    sys.exit(1)

if len(sys.argv) < 2:
    usage()

description = sys.argv[1]

TASK_API_URL = "http://localhost:8000"

async def submit_and_watch():
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 提交任务
        payload = {
            "task_type": "code",
            "input": description
        }
        print("📤 提交任务…")
        r = await client.post(f"{TASK_API_URL}/api/v1/tasks", json=payload)
        r.raise_for_status()
        data = r.json()
        task_id = data["task_id"]
        print("✅ 任务已提交: ", task_id)

        # 轮询状态
        for _ in range(60):  # 最多轮询 60 次（~2 分钟）
            await asyncio.sleep(2)
            resp = await client.get(f"{TASK_API_URL}/api/v1/tasks/{task_id}")
            if resp.status_code != 200:
                continue
            status_info = resp.json()
            status = status_info.get("status")
            print(f"⏳ status={status}")
            if status == "completed":
                print("🎉 任务完成! 输出轨迹摘要: ")
                print(json.dumps(status_info.get("result"), ensure_ascii=False, indent=2))
                return
            if status == "failed":
                print("❌ 任务失败")
                print(status_info)
                return
        print("⚠️ 任务超时未完成")

if __name__ == "__main__":
    asyncio.run(submit_and_watch()) 