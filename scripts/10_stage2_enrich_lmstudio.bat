@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%" || exit /b 1

if "%PYTHON%"=="" set "PYTHON=python"
if "%STORE_ROOT%"=="" set "STORE_ROOT=store"
set "MONTH_ARG=%~1"
if "%MONTH_ARG%"=="" set "MONTH_ARG=%MONTH%"
if "%MONTH_ARG%"=="" set "MONTH_ARG=2025-12"
if "%OVERWRITE_ENRICH%"=="" set "OVERWRITE_ENRICH=0"

if "%FLOMO_VLM_BASE_URL%"=="" (
  echo Missing FLOMO_VLM_BASE_URL, for example: http://127.0.0.1:1234/v1
  exit /b 2
)

if "%FLOMO_VLM_MODEL%"=="" (
  echo Missing FLOMO_VLM_MODEL, for example: google/gemma-4-e4b:2
  exit /b 2
)

if "%FLOMO_VLM_TIMEOUT_SECONDS%"=="" set "FLOMO_VLM_TIMEOUT_SECONDS=180"

echo Stage 2: image enrich via LM Studio
echo month=%MONTH_ARG%
echo store_root=%STORE_ROOT%

if "%OVERWRITE_ENRICH%"=="1" (
  "%PYTHON%" scripts\enrich_images.py --store-root "%STORE_ROOT%" --provider lmstudio --month "%MONTH_ARG%" --overwrite
) else (
  "%PYTHON%" scripts\enrich_images.py --store-root "%STORE_ROOT%" --provider lmstudio --month "%MONTH_ARG%"
)
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON%" scripts\validate_enriched_images.py --store-root "%STORE_ROOT%" --summary
exit /b %ERRORLEVEL%
