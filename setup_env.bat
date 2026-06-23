@echo off
REM ====================================================================
REM ClustroView - first-time environment setup (Windows)
REM
REM Creates the `clustroview` conda env (Python 3.12) and installs
REM front/requirements.txt into it. Safe to re-run.
REM
REM Usage:  setup_env.bat
REM ====================================================================
setlocal EnableDelayedExpansion

set "ENV_NAME=clustroview"
set "PY_VERSION=3.12"

echo === ClustroView first-time setup ===
echo.

REM Check conda
where conda >nul 2>&1
if errorlevel 1 (
    echo ERROR: 'conda' is not on PATH. Install Anaconda / Miniconda first.
    exit /b 1
)

REM Create env if it does not exist
conda info --envs | findstr /B /I "%ENV_NAME%" >nul 2>&1
if errorlevel 1 (
    echo Creating conda env "%ENV_NAME%" with Python %PY_VERSION% ...
    call conda create -n %ENV_NAME% python=%PY_VERSION% -y
    if errorlevel 1 (
        echo ERROR: failed to create conda env.
        exit /b 1
    )
) else (
    echo Conda env "%ENV_NAME%" already exists - skipping create.
)

REM Activate env and install requirements
echo.
echo Activating %ENV_NAME% and installing dependencies ...
call conda activate %ENV_NAME%
if errorlevel 1 (
    echo ERROR: failed to activate env.
    exit /b 1
)

REM The 'python>=3.10' line in requirements.txt is a metadata directive,
REM not a real pip package. Filter it out before installing.
set "REQ_FILE=%~dp0front\requirements.txt"
set "TMP_FILE=%TEMP%\clustroview_requirements.tmp.txt"
> "%TMP_FILE%" (for /f "usebackq tokens=*" %%L in ("%REQ_FILE%") do (
    set "LINE=%%L"
    if /I not "!LINE:~0,6!"=="python" echo !LINE!
))

python -m pip install --upgrade pip
python -m pip install -r "%TMP_FILE%"
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed.
    del "%TMP_FILE%" >nul 2>&1
    exit /b 1
)
del "%TMP_FILE%" >nul 2>&1

echo.
echo === Setup complete ===
echo Run run.bat to start the GUI.
endlocal
