@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%" || exit /b 1

if "%PYTHON%"=="" set "PYTHON=python"
if "%STORE_ROOT%"=="" set "STORE_ROOT=store"
if "%MONTHLY_ROOT%"=="" set "MONTHLY_ROOT=monthly"
if "%CHUNKS_ROOT%"=="" set "CHUNKS_ROOT=llm_chunks"
set "MONTH_ARG=%~1"
if "%MONTH_ARG%"=="" set "MONTH_ARG=%MONTH%"
if "%OVERWRITE_CHUNKS%"=="" set "OVERWRITE_CHUNKS=1"

echo Stage 3-4: build merged monthly context and LLM chunks
if "%MONTH_ARG%"=="" (
  echo month=all
) else (
  echo month=%MONTH_ARG%
)
echo store_root=%STORE_ROOT%
echo monthly_root=%MONTHLY_ROOT%
echo chunks_root=%CHUNKS_ROOT%

"%PYTHON%" scripts\validate_enriched_images.py --store-root "%STORE_ROOT%" --summary
if errorlevel 1 exit /b %ERRORLEVEL%

if "%MONTH_ARG%"=="" (
  "%PYTHON%" scripts\merge_monthly.py --store-root "%STORE_ROOT%" --monthly-root "%MONTHLY_ROOT%"
) else (
  "%PYTHON%" scripts\merge_monthly.py --store-root "%STORE_ROOT%" --monthly-root "%MONTHLY_ROOT%" --month "%MONTH_ARG%"
)
if errorlevel 1 exit /b %ERRORLEVEL%

if "%MONTH_ARG%"=="" (
  "%PYTHON%" scripts\validate_monthly.py --store-root "%STORE_ROOT%" --monthly-root "%MONTHLY_ROOT%" --summary
) else (
  "%PYTHON%" scripts\validate_monthly.py --store-root "%STORE_ROOT%" --monthly-root "%MONTHLY_ROOT%" --month "%MONTH_ARG%" --summary
)
if errorlevel 1 exit /b %ERRORLEVEL%

if "%OVERWRITE_CHUNKS%"=="1" (
  if "%MONTH_ARG%"=="" (
    "%PYTHON%" scripts\build_chunks.py --monthly-root "%MONTHLY_ROOT%" --chunks-root "%CHUNKS_ROOT%" --overwrite
  ) else (
    "%PYTHON%" scripts\build_chunks.py --monthly-root "%MONTHLY_ROOT%" --chunks-root "%CHUNKS_ROOT%" --month "%MONTH_ARG%" --overwrite
  )
) else (
  if "%MONTH_ARG%"=="" (
    "%PYTHON%" scripts\build_chunks.py --monthly-root "%MONTHLY_ROOT%" --chunks-root "%CHUNKS_ROOT%"
  ) else (
    "%PYTHON%" scripts\build_chunks.py --monthly-root "%MONTHLY_ROOT%" --chunks-root "%CHUNKS_ROOT%" --month "%MONTH_ARG%"
  )
)
if errorlevel 1 exit /b %ERRORLEVEL%

if "%MONTH_ARG%"=="" (
  "%PYTHON%" scripts\validate_chunks.py --monthly-root "%MONTHLY_ROOT%" --chunks-root "%CHUNKS_ROOT%" --summary
) else (
  "%PYTHON%" scripts\validate_chunks.py --monthly-root "%MONTHLY_ROOT%" --chunks-root "%CHUNKS_ROOT%" --month "%MONTH_ARG%" --summary
)
if errorlevel 1 exit /b %ERRORLEVEL%

if "%MONTH_ARG%"=="" (
  echo Ready for external LLM input: %CHUNKS_ROOT%\YYYY-MM\*.json
) else (
  echo Ready for external LLM input: %CHUNKS_ROOT%\%MONTH_ARG%\*.json
)
exit /b 0
