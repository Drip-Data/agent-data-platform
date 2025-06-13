import pytest
import os
import asyncio
from core.persistence_service import PersistenceService

def test_persistence_file_storage(tmp_path):
    # 配置文件存储路径
    os.environ["STORAGE_STORAGE_TYPE"] = "file"
    os.environ["STORAGE_STORAGE_PATH"] = str(tmp_path)
    persistence = PersistenceService()
    data = {"task_id": "t1", "result": "ok"}
    loop = asyncio.get_event_loop()
    loop.run_until_complete(persistence.save_trajectory(data))
    loaded = loop.run_until_complete(persistence.load_trajectory("t1"))
    assert loaded["result"] == "ok"
    loop.run_until_complete(persistence.close())

