@echo off
chcp 936 >nul
setlocal
title 员工工资申报转换工具
cd /d "%~dp0"

if /i "%~1"=="help" goto :help

rem 自动找 dist 里最新的、带版本号的 exe（跳过 .old 备份）
set "EXE="
for /f "delims=" %%f in ('dir /b /a-d /o-d "%~dp0dist\员工工资申报转换工具*.exe" 2^>nul ^| findstr /i /v "\.old\."') do (
    if not defined EXE set "EXE=%~dp0dist\%%f"
)

if defined EXE (
    echo 正在启动：%EXE%
    start "" "%EXE%"
    goto :done
)

set "PYW="
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not defined PYW if exist "%~dp0.buildenv\Scripts\pythonw.exe" set "PYW=%~dp0.buildenv\Scripts\pythonw.exe"
if not defined PYW if exist "%~dp0.venv\Scripts\python.exe" set "PYW=%~dp0.venv\Scripts\python.exe"
if not defined PYW if exist "%~dp0.buildenv\Scripts\python.exe" set "PYW=%~dp0.buildenv\Scripts\python.exe"

if not defined PYW (
    echo [错误] dist 里没找到打包好的 exe，也没找到 Python 运行环境。
    echo.
    echo   办法一：先双击「打包exe.bat」生成独立程序
    echo   办法二：在本目录依次执行下面两行
    echo        python -m venv .venv
    echo        .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    goto :done
)

echo 正在启动（源码模式）...
start "" "%PYW%" "%~dp0main.py"
goto :done

:help
echo 员工工资申报转换工具
echo.
echo   启动工具.bat          直接打开工具
echo   启动工具.bat help     显示本说明
echo   打包exe.bat           打包成独立 exe
echo   生成更新包.bat         生成要传到服务器的更新包
echo.
pause

:done
endlocal
