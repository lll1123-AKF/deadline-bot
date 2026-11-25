@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   DeadlineBot - Agent Runtime local server
echo ==================================================
echo.

where python >nul 2>nul
if not errorlevel 1 goto USE_PYTHON
where py >nul 2>nul
if not errorlevel 1 goto USE_PY
goto NO_PYTHON

:USE_PYTHON
set "PY=python"
goto RUN

:USE_PY
set "PY=py -3"
goto RUN

:NO_PYTHON
echo [ERROR] Python not found on this computer.
echo.
echo Install Python 3.11 or newer:
echo   https://www.python.org/downloads/
echo During setup, CHECK the box "Add python.exe to PATH".
echo Then double-click this file again.
echo.
pause
exit /b 1

:RUN
echo [OK] Python found. Starting server...
echo.
echo   Open this address in your browser:
echo   http://127.0.0.1:8765/
echo.
echo   Keep this window OPEN while using the page.
echo   Press Ctrl+C (or close the window) to stop.
echo.
echo   If the browser says "can't connect", wait 2 seconds and press F5.
echo.
start "" http://127.0.0.1:8765/
%PY% server.py --prefer-rule
echo.
echo Server stopped.
pause
