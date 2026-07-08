@echo off
chcp 65001 >nul
echo ========================================
echo   GameAuto Daily - 游戏日常自动化工具
echo ========================================
echo.
echo 正在检查 Python 环境...

REM 优先用 py 启动器（始终在 PATH），其次 python
set PY_CMD=python
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py
) else (
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python，请先安装 Python 3.8+
        echo   提示：如果已安装 Python，请确保安装时勾选 "Add Python to PATH"
        pause
        exit /b 1
    )
)

echo [信息] Python 已就绪
echo.

echo 正在检查依赖...
%PY_CMD% -m pip install -r requirements.txt --quiet

echo.
echo 启动程序...
%PY_CMD% main.py
pause
