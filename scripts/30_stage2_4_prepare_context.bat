@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%" || exit /b 1

set "MONTH_ARG=%~1"
if "%MONTH_ARG%"=="" set "MONTH_ARG=%MONTH%"

call scripts\10_stage2_enrich_lmstudio.bat "%MONTH_ARG%"
if errorlevel 1 exit /b %ERRORLEVEL%

call scripts\20_stage3_4_build_context.bat "%MONTH_ARG%"
exit /b %ERRORLEVEL%
