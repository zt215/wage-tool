@echo off
chcp 936 >nul
setlocal
title 打包 - 员工工资申报转换工具
cd /d "%~dp0"

set "PY=%~dp0.buildenv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [错误] 没找到可用的 Python 环境。
    echo.
    echo   请先在本目录依次执行：
    echo        python -m venv .buildenv
    echo        .buildenv\Scripts\pip install PySide6-Essentials openpyxl pyinstaller
    echo.
    pause
    exit /b 1
)

echo [1/3] 检查打包依赖...
"%PY%" -c "import PySide6, openpyxl, PyInstaller" 1>nul 2>nul
if errorlevel 1 (
    echo        缺少依赖，正在安装...
    "%PY%" -m pip install PySide6-Essentials openpyxl pyinstaller
)

echo [2/3] 开始打包（第一次约 1-3 分钟，请耐心等待）...
"%PY%" -m PyInstaller --noconfirm --clean build.spec
if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请把上面的报错内容发出来。
    pause
    exit /b 1
)

rem 找出刚打出来的、带版本号的 exe（跳过 .old 备份）
set "APP="
for /f "delims=" %%f in ('dir /b /a-d /o-d "%~dp0dist\员工工资申报转换工具*.exe" 2^>nul ^| findstr /i /v "\.old\."') do (
    if not defined APP set "APP=%~dp0dist\%%f"
)

echo [3/3] 自检打包结果...
if defined APP (
    del "%~dp0dist\自检结果.txt" >nul 2>nul
    start /wait "" "%APP%" --selftest
    if exist "%~dp0dist\自检结果.txt" type "%~dp0dist\自检结果.txt"
) else (
    echo        [警告] dist 里没找到 exe。
)

echo.
echo 打包完成，程序位置：
echo    %APP%
echo 以后双击「启动工具.bat」即可运行；
echo 要发布给别人的话，双击「生成更新包.bat」。
echo.
pause
endlocal
