@echo off
chcp 936 >nul
setlocal
title 获取 GitHub Token
cd /d "%~dp0"

echo ============================================================
echo  获取 GitHub Token
echo ============================================================
echo.
echo  马上会打开 GitHub 的「新建 Token」页面（要先用浏览器登录 GitHub）。
echo.
echo  ── 推荐用经典 Token，页面上只要 3 步 ──
echo.
echo    1. Note 填个名字，比如  wage-tool
echo       Expiration 选有效期（建议 90 days；嫌麻烦选 No expiration）
echo.
echo    2. 权限列表里勾上第一项  repo
echo       （勾上 repo 之后，它下面的子项会自动跟着全选，不用管）
echo.
echo    3. 拉到最底下点绿色的  Generate token
echo       页面上会出现一串  ghp_ 开头 的字符，复制它
echo.
echo  [!] 这串字符只在生成时显示一次，关掉页面就看不到了，
echo      所以务必马上复制。丢了只能重新生成一个。
echo.
echo  ── 复制好之后 ──
echo.
echo    双击  「发布到GitHub.bat」 ，把它粘贴进去就完事了。
echo    程序会记住，下次不用再填。
echo.
echo ============================================================
echo.

start "" "https://github.com/settings/tokens/new"

echo  已经打开浏览器。如果没反应，手动复制这个网址：
echo      https://github.com/settings/tokens/new
echo.
echo  （细粒度 Token 的地址是：
echo      https://github.com/settings/personal-access-tokens/new ）
echo.
pause
endlocal
