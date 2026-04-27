@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%" || exit /b 1

if "%PYTHON%"=="" set "PYTHON=python"
if "%RAW_ROOT%"=="" set "RAW_ROOT=raw"
if "%STORE_ROOT%"=="" set "STORE_ROOT=store"
if "%FLOMO_VLM_BASE_URL%"=="" set "FLOMO_VLM_BASE_URL=http://127.0.0.1:1234/v1"
if "%FLOMO_VLM_MODEL%"=="" set "FLOMO_VLM_MODEL=google/gemma-4-e4b"

set "MONTH_ARG=%~1"
if "%MONTH_ARG%"=="" set "MONTH_ARG=%MONTH%"

echo Stage 1: extract raw export
echo raw_root=%RAW_ROOT%
echo store_root=%STORE_ROOT%
"%PYTHON%" scripts\extract_raw.py --raw-root "%RAW_ROOT%" --store-root "%STORE_ROOT%"
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON%" scripts\validate_store.py --raw-root "%RAW_ROOT%" --store-root "%STORE_ROOT%" --summary
if errorlevel 1 exit /b %ERRORLEVEL%

call scripts\10_stage2_enrich_lmstudio.bat "%MONTH_ARG%"
if errorlevel 1 exit /b %ERRORLEVEL%

call scripts\20_stage3_4_build_context.bat "%MONTH_ARG%"
exit /b %ERRORLEVEL%
