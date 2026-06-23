@echo off
echo [1/4] pip install -e .[dev,gui]
pip install -e .[dev,gui]
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo [2/4] npm install
cd gui
cmd /c npm install
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo [3/4] build sidecar
cmd /c npm run sidecar
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo [4/4] build NSIS installer
cmd /c npm run tauri:build:nsis
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo Done. Installer:
dir /b ..\flomo-transcriber_*_x64-setup.exe 2>nul
