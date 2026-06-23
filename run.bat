@echo off
REM ====================================================================
REM ClustroView - one-click launcher (Windows)
REM
REM Activates the `clustroview` conda env and starts the GUI.
REM Run from any directory. Does NOT modify your PATH permanently.
REM
REM First-time setup: run setup_env.bat
REM ====================================================================
setlocal EnableDelayedExpansion

set "ENV_NAME=clustroview"
set "SCRIPT_DIR=%~dp0"
REM Strip trailing backslash for cleaner paths
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Activate the conda env unless we are already inside it
if /I not "%CONDA_DEFAULT_ENV%"=="%ENV_NAME%" (
    echo Activating conda env: %ENV_NAME%
    call conda activate %ENV_NAME%
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to activate "%ENV_NAME%". Run setup_env.bat first.
        exit /b 1
    )
)

REM Launch the GUI
echo Starting ClustroView from %SCRIPT_DIR%\front ...
cd /d "%SCRIPT_DIR%\front"
python main.py %*
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
