@echo off
chcp 65001 >nul
echo ========================================
echo   GameAuto Daily - 游戏日常自动化工具
echo ========================================
echo.
echo 正在检查 Python 环境...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo [信息] Python 已就绪
echo.
echo 正在检查依赖...

pip install -r requirements.txt --quiet

echo.
echo 启动程序...
python main.py
pause
