@echo off

REM 获取脚本所在目录的父目录（项目根目录）
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%.."

echo 🚀 Agent Data Platform 快速启动脚本
echo ==================================
echo 📁 工作目录: %CD%

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未找到，请先安装Python
    pause
    exit /b 1
)

echo ✅ 环境检查完成
echo.

echo 请选择运行模式:
echo 1^) 交互式模式 ^(启动服务 + 交互式命令^)
echo 2^) 批处理模式 ^(启动服务 + 自动注入测试任务^)
echo 3^) 仅启动服务
echo 4^) 仅注入任务 ^(需要服务已运行^)
echo 5^) 运行基础测试

set /p choice="请输入选择 (1-5): "

if "%choice%"=="1" (
    echo 🎮 启动交互式模式...
    python scripts/run_system.py --mode interactive
) else if "%choice%"=="2" (
    echo 🔄 启动批处理模式...
    python scripts/run_system.py --mode batch --tasks-file data/test_tasks.jsonl
) else if "%choice%"=="3" (
    echo ⚙️ 启动服务...
    python main.py
) else if "%choice%"=="4" (
    echo 📋 注入测试任务...
    python scripts/run_system.py --no-start --mode batch --tasks-file data/test_tasks.jsonl
) else if "%choice%"=="5" (
    echo 🧪 运行基础测试...
    python -m pytest tests/test_mcp_server_startup.py -v
) else (
    echo ❌ 无效选择
    pause
    exit /b 1
)

pause