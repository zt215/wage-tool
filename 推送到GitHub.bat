@echo off
chcp 936 >nul
setlocal
title 推送到 GitHub - 员工工资申报转换工具
cd /d "%~dp0"

set "REPO=https://github.com/zt215/wage-tool.git"
set "BRANCH=main"

where git >nul 2>nul
if errorlevel 1 (
    echo [错误] 没找到 git 命令，请先安装 Git for Windows。
    pause
    exit /b 1
)

echo ============================================================
echo  推送源码到  https://github.com/zt215/wage-tool
echo ============================================================
echo.
echo  说明：这个只是把源码传上去（顺便让仓库有内容，
echo        因为 GitHub 的空仓库建不了 Release）。
echo        含员工姓名/身份证号的 Excel 已经被 .gitignore 挡住，
echo        不会上传，可以放心。
echo.

if not exist ".git" (
    echo 初始化本地仓库...
    git init -q
    git branch -M %BRANCH% 2>nul
)

echo 暂存改动...
git add -A

git diff --cached --quiet
if errorlevel 1 (
    echo 提交改动...
    git commit -q -m "同步更新 (%DATE%)"
) else (
    echo 没有新改动需要提交。
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
    git remote add origin %REPO%
) else (
    git remote set-url origin %REPO%
)

echo.
echo 开始推送（第一次会弹出 GitHub 登录，登录一次以后就记住了）...
echo.
git push -u origin %BRANCH%
if errorlevel 1 (
    echo.
    echo [失败] 推送没成功，看上面的报错。
    echo.
    echo   提示：如果提示 authentication failed，
    echo         在弹窗里用浏览器登录 GitHub 账号即可；
    echo         或者用 Personal Access Token 当密码。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  推送完成！仓库里有内容了，现在可以去发 Release：
echo      https://github.com/zt215/wage-tool/releases
echo ============================================================
echo.
pause
endlocal
