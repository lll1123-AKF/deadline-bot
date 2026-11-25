@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo  DeadlineBot - 配置并推送到 GitHub
echo ======================================================
echo.

set REPO_URL=https://github.com/lll1123-AKF/deadline-bot.git
if not "%~1"=="" set REPO_URL=%~1

echo [1/5] 启用 Git Credential Manager（浏览器登录）
git config --global credential.helper manager
echo       OK

echo [2/5] 初始化本地仓库
if not exist ".git" (
  git init -q
  git branch -M main
  echo       已初始化，主分支 main
) else (
  echo       已存在，跳过
)

echo [3/5] 提交文件
git add -A
git commit -q -m "feat: deadline-bot - notification-to-task agent skill for nanobot" 2>nul
echo       完成

echo [4/5] 设置远程仓库
git remote remove origin 2>nul
git remote add origin %REPO_URL%
echo       远程：%REPO_URL%

echo [5/5] 推送（如弹出登录窗口，请选择浏览器登录并授权）
echo.
git push -u origin main
set PUSH_RESULT=%errorlevel%

echo.
if "%PUSH_RESULT%"=="0" (
  echo ======================================================
  echo  推送成功！仓库地址：%REPO_URL:.git=%
  echo ======================================================
) else (
  echo 推送未成功，请查看上方报错，或阅读 PUSH_GUIDE.md
)
pause
