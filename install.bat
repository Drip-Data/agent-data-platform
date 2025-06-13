@echo off
echo ===============================================
echo    Agent Data Platform 安装脚本 (Windows)
echo ===============================================
echo.

echo [1/5] 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

echo [2/5] 检查Chocolatey...
choco --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 警告: 未找到Chocolatey，将跳过Redis自动安装
    echo 请手动安装Redis或参考README安装说明
    set SKIP_REDIS=1
) else (
    echo Chocolatey已安装，将自动安装Redis
)

echo [3/5] 安装Python依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 错误: Python依赖安装失败
    pause
    exit /b 1
)

if not defined SKIP_REDIS (
    echo [4/5] 安装Redis服务...
    choco install memurai-developer -y
    if %errorlevel% neq 0 (
        echo 警告: Redis安装失败，系统将使用内存模式
    ) else (
        echo Redis安装成功，启动服务...
        net start memurai
    )
) else (
    echo [4/5] 跳过Redis安装
)

echo [5/5] 创建环境变量模板...
if not exist .env (
    copy .env.example .env
    echo 已创建.env文件，请编辑添加您的API密钥
)

echo.
echo ===============================================
echo           安装完成！
echo ===============================================
echo.
echo 接下来的步骤：
echo 1. 编辑 .env 文件，添加您的API密钥
echo 2. 运行: python main.py
echo.
echo 服务地址：
echo - 主要服务: http://localhost:8000
echo - 监控面板: http://localhost:8082
echo - WebSocket: ws://localhost:8081
echo.
pause
