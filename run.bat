@echo off
chcp 65001 >nul
title AI Presentation Agent

:start
echo ========================================
echo   AI Presentation Agent 启动器
echo ========================================
echo.
echo 正在启动 Streamlit Web 界面...
echo.

:: 启动 Streamlit（在后台运行）
start "Streamlit Server" /min cmd /c "streamlit run app.py --server.headless true"

:: 等待服务器启动
timeout /t 3 /nobreak >nul

:: 自动打开浏览器
start http://localhost:8501

echo ✓ Web 界面已启动！
echo.
echo ========================================
echo   控制台命令：
echo   1 = 重启服务
echo   q = 退出
echo ========================================
echo.

:loop
set /p input="请输入命令: "

if "%input%"=="1" (
    echo.
    echo 正在重启服务...
    :: 关闭所有 streamlit 进程
    taskkill /f /im streamlit.exe >nul 2>&1
    taskkill /f /fi "WINDOWTITLE eq Streamlit Server" >nul 2>&1
    :: 强制关闭占用8501端口的进程
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501 ^| findstr LISTENING') do (
        taskkill /f /pid %%a >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
    echo.
    goto start
)

if /i "%input%"=="q" (
    echo.
    echo 正在关闭服务...
    taskkill /f /im streamlit.exe >nul 2>&1
    taskkill /f /fi "WINDOWTITLE eq Streamlit Server" >nul 2>&1
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501 ^| findstr LISTENING') do (
        taskkill /f /pid %%a >nul 2>&1
    )
    echo 已退出。
    exit /b 0
)

if /i "%input%"=="exit" (
    goto :eof
)

echo 未知命令，请输入 1 重启或 q 退出
goto loop