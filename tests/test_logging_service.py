from core.logging_service import setup_logging, LoggingService
import logging
import os

def test_logging_service_console_and_file(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    service = setup_logging(log_level="DEBUG", log_dir=str(log_dir), app_name="test-app", use_json_format=False)
    logger = service.get_logger("test")
    logger.info("test info")
    logger.error("test error")
    # 检查日志文件是否生成
    log_file = log_dir / "test-app.log"
    assert log_file.exists()
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "test info" in content
        assert "test error" in content
