@echo off
chcp 65001 >nul
echo ========================================
echo   GameAuto Daily - 一键打包脚本
echo ========================================
echo.

REM 优先用 py 启动器（始终在 PATH），其次 python
set PY_CMD=python
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py
) else (
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python
        pause
        exit /b 1
    )
)

:: 安装依赖
echo [1/3] 安装依赖...
%PY_CMD% -m pip install -r requirements.txt --quiet

:: 清理旧构建
echo [2/3] 清理旧构建...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

:: PyInstaller 打包
echo [3/3] 开始打包（可能需要几分钟）...
echo.
pyinstaller build.spec

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   打包完成！
    echo   输出文件: dist\GameAutoDaily.exe
    echo ========================================
) else (
    echo.
    echo [错误] 打包失败，请检查上方输出
)

pause
