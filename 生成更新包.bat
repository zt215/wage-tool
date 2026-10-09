@echo off
chcp 936 >nul
setlocal
title 生成更新包 - 员工工资申报转换工具
cd /d "%~dp0"

set "HAVE="
for /f "delims=" %%f in ('dir /b /a-d "%~dp0dist\员工工资申报转换工具*.exe" 2^>nul ^| findstr /i /v "\.old\."') do set "HAVE=%%f"

if not defined HAVE (
    echo [提示] dist 里还没有打包好的 exe，先执行打包...
    call "%~dp0打包exe.bat"
    for /f "delims=" %%f in ('dir /b /a-d "%~dp0dist\员工工资申报转换工具*.exe" 2^>nul ^| findstr /i /v "\.old\."') do set "HAVE=%%f"
    if not defined HAVE (
        echo [失败] 打包没成功，先解决打包问题。
        pause
        exit /b 1
    )
)

set "PY=%~dp0.buildenv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [错误] 没找到 Python 环境，请先执行「打包exe.bat」。
    pause
    exit /b 1
)

echo 正在生成更新包...
"%PY%" "%~dp0tools\make_package.py" %*
if errorlevel 1 (
    echo.
    echo [失败] 生成更新包出错。
    pause
    exit /b 1
)

echo.
echo 更新包已生成，把里面的 exe 和 version.json 传到服务器即可，
echo 具体见「上传说明.txt」。
echo.
pause
endlocal
