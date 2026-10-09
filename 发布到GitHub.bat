@echo off
chcp 936 >nul
setlocal
title 发布到 GitHub - 员工工资申报转换工具
cd /d "%~dp0"

set "PY=%~dp0.buildenv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"

if /i "%~1"=="clear-token" (
    if not exist "%PY%" (
        echo [错误] 没找到 Python 环境。
        pause
        exit /b 1
    )
    "%PY%" "%~dp0tools\publish_github.py" --clear-token
    pause
    exit /b 0
)

if not exist "%PY%" (
    echo [错误] 没找到 Python 环境，请先执行「打包exe.bat」。
    pause
    exit /b 1
)

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

echo.
echo ============================================================
echo  发布到 GitHub Releases   仓库：zt215/wage-tool
echo ============================================================
echo.
echo  如果提示要 Token，注意：Token 不是仓库网址！
echo.
echo    Token 长的样子： ghp_AbCdEfGhIjKlMnOp...   （一长串乱码）
echo    仓库网址的样子： https://github.com/zt215/wage-tool
echo                    这个是网址，填进去会被拒绝
echo.
echo  拿 Token 的步骤：
echo    1. 打开  https://github.com/settings/tokens
echo    2. 点 Fine-grained tokens - Generate new token
echo       仓库访问选 Only select repositories - 勾上 wage-tool
echo       Permissions - Repository permissions - Contents 选 Read and write
echo       （或者用 Tokens (classic)，勾上 repo 那一项）
echo    3. 生成的字符串复制过来粘贴
echo.
echo  Token 只存在本机 tools\github_token.txt，不会上传。
echo  想换 Token：双击「发布到GitHub.bat clear-token」先清掉旧的。
echo ============================================================
echo.

"%PY%" "%~dp0tools\publish_github.py" %*
if errorlevel 1 (
    echo.
    echo [失败] 发布没有完成，看上面的提示。
    pause
    exit /b 1
)

echo.
pause
endlocal
