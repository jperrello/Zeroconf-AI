@echo off
setlocal enabledelayedexpansion

echo ======================================
echo   VLC ZeroConf AI Chat Installer
echo ======================================
echo.

tasklist /FI "IMAGENAME eq vlc.exe" 2>NUL | find /I /N "vlc.exe">NUL
if "!ERRORLEVEL!"=="0" (
    echo [WARNING] VLC is currently running!
    echo.
    echo Please close VLC completely before continuing.
    echo Press Ctrl+C to cancel or...
    pause
    echo.
    echo Checking again...
    tasklist /FI "IMAGENAME eq vlc.exe" 2>NUL | find /I /N "vlc.exe">NUL
    if "!ERRORLEVEL!"=="0" (
        echo [ERROR] VLC is still running. Please close it first.
        pause
        exit /b 1
    )
)

set VLC_FOUND=0
set PYTHON_CMD=

echo Checking for VLC installation...

reg query "HKLM\SOFTWARE\VideoLAN\VLC" /v InstallDir >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\VideoLAN\VLC" /v InstallDir 2^>nul') do (
        set VLC_PATH=%%b
        if exist "!VLC_PATH!\vlc.exe" (
            echo [OK] Found VLC in registry: !VLC_PATH!
            set VLC_FOUND=1
            goto :vlc_found
        )
    )
)

reg query "HKLM\SOFTWARE\Wow6432Node\VideoLAN\VLC" /v InstallDir >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\Wow6432Node\VideoLAN\VLC" /v InstallDir 2^>nul') do (
        set VLC_PATH=%%b
        if exist "!VLC_PATH!\vlc.exe" (
            echo [OK] Found VLC in 32-bit registry: !VLC_PATH!
            set VLC_FOUND=1
            goto :vlc_found
        )
    )
)

if exist "%ProgramFiles%\VideoLAN\VLC\vlc.exe" (
    echo [OK] Found VLC in Program Files
    set VLC_FOUND=1
    goto :vlc_found
)

if exist "%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe" (
    echo [OK] Found VLC in Program Files (x86)
    set VLC_FOUND=1
    goto :vlc_found
)

where vlc.exe >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] Found VLC in PATH
    set VLC_FOUND=1
    goto :vlc_found
)

:vlc_found
if !VLC_FOUND! EQU 0 (
    echo.
    echo [ERROR] VLC not found on this system.
    echo.
    echo Please install VLC from one of these sources:
    echo   - Official website: https://www.videolan.org/vlc/
    echo   - Microsoft Store: search for 'VLC'
    echo   - Chocolatey: choco install vlc
    echo   - Winget: winget install VideoLAN.VLC
    echo.
    pause
    exit /b 1
)

echo.
echo Checking for Python 3...

python --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=2" %%a in ('python --version 2^>^&1') do (
        echo [OK] Found Python: %%a
        set PYTHON_CMD=python
        goto :python_found
    )
)

python3 --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=2" %%a in ('python3 --version 2^>^&1') do (
        echo [OK] Found Python: %%a
        set PYTHON_CMD=python3
        goto :python_found
    )
)

py --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=2" %%a in ('py --version 2^>^&1') do (
        echo [OK] Found Python: %%a
        set PYTHON_CMD=py
        goto :python_found
    )
)

echo.
echo [ERROR] Python 3 not found.
echo.
echo Please install Python 3 from:
echo   - Official website: https://www.python.org/downloads/
echo   - Microsoft Store: search for 'Python'
echo   - Chocolatey: choco install python
echo   - Winget: winget install Python.Python.3
echo.
pause
exit /b 1

:python_found

echo.
echo Installing Python dependencies...
%PYTHON_CMD% -m pip install --user fastapi uvicorn requests zeroconf pydantic >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] Python dependencies installed
) else (
    echo [WARNING] Some dependencies may not have installed correctly
    echo You can install them manually with:
    echo   %PYTHON_CMD% -m pip install --user fastapi uvicorn requests zeroconf pydantic
)

echo.
echo Installing VLC extension...

set EXTENSIONS_DIR=%APPDATA%\vlc\lua\extensions
if not exist "%EXTENSIONS_DIR%" (
    mkdir "%EXTENSIONS_DIR%"
    echo [INFO] Created extensions directory: %EXTENSIONS_DIR%
)

if exist "%~dp0zeroconf_ai_chat.lua" (
    set SOURCE_FILE=%~dp0zeroconf_ai_chat.lua
    echo [INFO] Using: zeroconf_ai_chat.lua
) else (
    echo [ERROR] Extension file not found in %~dp0
    echo Looking for:  zeroconf_ai_chat.lua
    pause
    exit /b 1
)

if exist "%EXTENSIONS_DIR%\zeroconf_ai_chat.lua" (
    echo [INFO] Removing old extension...
    del /F /Q "%EXTENSIONS_DIR%\zeroconf_ai_chat.lua"
)

copy /Y "!SOURCE_FILE!" "%EXTENSIONS_DIR%\zeroconf_ai_chat.lua" >nul
if !ERRORLEVEL! EQU 0 (
    echo [OK] Extension installed to: %EXTENSIONS_DIR%\zeroconf_ai_chat.lua
) else (
    echo [ERROR] Failed to copy extension file
    pause
    exit /b 1
)

echo.
echo Installing discovery bridge...

set BRIDGE_DIR=%USERPROFILE%\.vlc
if not exist "%BRIDGE_DIR%" (
    mkdir "%BRIDGE_DIR%"
)

if exist "%~dp0vlc_discovery_bridge.py" (
    copy /Y "%~dp0vlc_discovery_bridge.py" "%BRIDGE_DIR%\" >nul
    echo [OK] Bridge installed to: %BRIDGE_DIR%
    
    echo.
    echo Creating launcher scripts...
    
    (
        echo @echo off
        echo set BRIDGE_DIR=%%~dp0
        echo set PID_FILE=%%BRIDGE_DIR%%bridge.pid
        echo.
        echo if exist "%%PID_FILE%%" ^(
        echo     set /p OLD_PID=^<"%%PID_FILE%%"
        echo     tasklist /FI "PID eq %%OLD_PID%%" 2^>NUL ^| find "%%OLD_PID%%" ^>NUL
        echo     if %%ERRORLEVEL%% EQU 0 ^(
        echo         echo Bridge already running ^(PID: %%OLD_PID%%^)
        echo         exit /b 0
        echo     ^)
        echo ^)
        echo.
        echo start /B %PYTHON_CMD% "%%BRIDGE_DIR%%vlc_discovery_bridge.py" ^> "%%BRIDGE_DIR%%bridge.log" 2^>^&1
        echo echo Bridge started
        echo echo Logs: %%BRIDGE_DIR%%bridge.log
    ) > "%BRIDGE_DIR%\start_bridge.bat"
    
    (
        echo @echo off
        echo set BRIDGE_DIR=%%~dp0
        echo set PID_FILE=%%BRIDGE_DIR%%bridge.pid
        echo.
        echo if exist "%%PID_FILE%%" ^(
        echo     set /p PID=^<"%%PID_FILE%%"
        echo     tasklist /FI "PID eq %%PID%%" 2^>NUL ^| find "%%PID%%" ^>NUL
        echo     if %%ERRORLEVEL%% EQU 0 ^(
        echo         taskkill /PID %%PID%% /F ^>NUL 2^>^&1
        echo         echo Bridge stopped ^(PID: %%PID%%^)
        echo     ^) else ^(
        echo         echo Bridge not running
        echo     ^)
        echo     del "%%PID_FILE%%"
        echo ^) else ^(
        echo     echo No PID file found
        echo ^)
    ) > "%BRIDGE_DIR%\stop_bridge.bat"
    
    echo [OK] Launcher scripts created
    
    set BRIDGE_INSTALLED=1
) else (
    echo [WARNING] vlc_discovery_bridge.py not found in %~dp0
    echo [INFO] Skipping bridge installation
    set BRIDGE_INSTALLED=0
)

echo.
echo ======================================
echo   Installation Complete!
echo ======================================
echo.

if !BRIDGE_INSTALLED! EQU 1 (
    echo Next steps:
    echo.
    echo 1. Start the discovery bridge:
    echo    %BRIDGE_DIR%\start_bridge.bat
    echo.
    echo 2. Open VLC and play any media
    echo.
    echo 3. Go to: View -^> ZeroConf AI Chat
    echo.
    echo 4. The extension will discover AI services on your network
    echo.
    echo Additional commands:
    echo   Stop bridge:  %BRIDGE_DIR%\stop_bridge.bat
    echo   View logs:    %BRIDGE_DIR%\bridge.log
    echo.
) else (
    echo Extension installed. To use it:
    echo.
    echo 1. Make sure you have the discovery bridge running
    echo.
    echo 2. Open VLC and play any media
    echo.
    echo 3. Go to: View -^> ZeroConf AI Chat
    echo.
)

echo IMPORTANT: If the extension does not appear in the View menu:
echo   1. Completely close VLC and reopen it
echo   2. Check Tools -^> Plugins and extensions -^> Active Extensions
echo   3. Click "Reload extensions" if needed
echo.
echo Make sure you have ZeroConf AI services running!
echo.
pause