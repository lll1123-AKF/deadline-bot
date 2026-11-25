@echo off
cd /d "%~dp0"
echo ======================================================
echo  DeadlineBot - push to GitHub
echo ======================================================
echo.

set REPO_URL=https://github.com/lll1123-AKF/deadline-bot.git
if not "%~1"=="" set REPO_URL=%~1

echo [1/5] Enable Git Credential Manager
git config --global credential.helper manager
echo       OK

echo [2/5] Init local repo
if not exist ".git" (
  git init -q
  git branch -M main
  echo       created (main)
) else (
  echo       already exists
)

echo [3/5] Commit files
git add -A
git commit -q -m "feat: deadline-bot - notification-to-task agent skill for nanobot" 2>nul
echo       done

echo [4/5] Set remote
git remote remove origin 2>nul
git remote add origin %REPO_URL%
echo       %REPO_URL%

echo [5/5] Push
echo       If a login window appears, choose "Sign in with your browser".
echo.
git push -u origin main
set PUSH_RESULT=%errorlevel%

echo.
if "%PUSH_RESULT%"=="0" (
  echo ======================================================
  echo   SUCCESS
  echo   Repo: %REPO_URL:.git=%
  echo ======================================================
) else (
  echo ======================================================
  echo   FAILED - please screenshot this window.
  echo ======================================================
)
echo.
pause
