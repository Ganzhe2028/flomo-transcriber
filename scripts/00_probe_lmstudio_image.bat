@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%" || exit /b 1

if "%PYTHON%"=="" set "PYTHON=python"
set "IMAGE_PATH=%~1"
if "%IMAGE_PATH%"=="" set "IMAGE_PATH=%IMAGE%"

if "%IMAGE_PATH%"=="" (
  echo Usage: %~nx0 ^<image-path^>
  echo Or: set IMAGE=^<image-path^> ^&^& %~nx0
  exit /b 2
)

if "%FLOMO_VLM_BASE_URL%"=="" (
  echo Missing FLOMO_VLM_BASE_URL, for example: http://127.0.0.1:1234/v1
  echo PowerShell: $env:FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
  echo CMD: set FLOMO_VLM_BASE_URL=http://127.0.0.1:1234/v1
  exit /b 2
)

if "%FLOMO_VLM_MODEL%"=="" (
  echo Missing FLOMO_VLM_MODEL, for example: google/gemma-4-e2b
  echo PowerShell: $env:FLOMO_VLM_MODEL="google/gemma-4-e2b"
  echo CMD: set FLOMO_VLM_MODEL=google/gemma-4-e2b
  exit /b 2
)

if "%FLOMO_VLM_TIMEOUT_SECONDS%"=="" set "FLOMO_VLM_TIMEOUT_SECONDS=180"
if "%FLOMO_VLM_MAX_TOKENS%"=="" set "FLOMO_VLM_MAX_TOKENS=4096"

"%PYTHON%" scripts\probe_lmstudio_vlm.py --image "%IMAGE_PATH%"
exit /b %ERRORLEVEL%
