@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%" || exit /b 1

if "%PYTHON%"=="" set "PYTHON=python"
if "%STORE_ROOT%"=="" set "STORE_ROOT=store"
if "%RETRY_ROUNDS%"=="" set "RETRY_ROUNDS=3"
if "%ENRICH_WORKERS%"=="" set "ENRICH_WORKERS=1"
if "%FLOMO_VLM_BASE_URL%"=="" set "FLOMO_VLM_BASE_URL=http://127.0.0.1:1234/v1"

set "MONTH_ARG=%~1"
if "%MONTH_ARG%"=="" set "MONTH_ARG=%MONTH%"

@REM if "%FLOMO_VLM_MODEL%"=="" (
@REM   echo Missing FLOMO_VLM_MODEL.
@REM   echo PowerShell: $env:FLOMO_VLM_MODEL="google/gemma-4-e2b"
@REM   echo CMD: set FLOMO_VLM_MODEL=google/gemma-4-e2b
@REM   exit /b 2
@REM )

if "%FLOMO_VLM_MODEL%"=="" set "FLOMO_VLM_MODEL=google/gemma-4-e4b"

echo Retry failed image enrich via LM Studio
if "%MONTH_ARG%"=="" (
  echo month=all
) else (
  echo month=%MONTH_ARG%
)
echo store_root=%STORE_ROOT%
echo retry_rounds=%RETRY_ROUNDS%
echo workers=%ENRICH_WORKERS%
echo vlm_model=%FLOMO_VLM_MODEL%

if "%MONTH_ARG%"=="" (
  "%PYTHON%" scripts\retry_failed_images.py --store-root "%STORE_ROOT%" --provider lmstudio --rounds "%RETRY_ROUNDS%" --workers "%ENRICH_WORKERS%"
) else (
  "%PYTHON%" scripts\retry_failed_images.py --store-root "%STORE_ROOT%" --provider lmstudio --month "%MONTH_ARG%" --rounds "%RETRY_ROUNDS%" --workers "%ENRICH_WORKERS%"
)
exit /b %ERRORLEVEL%
