@echo off
setlocal

echo ============================================================
echo  Brave Frontier Installer -- EXE Builder
echo ============================================================
echo.

:: Verify Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Download it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: Install / upgrade PyInstaller
echo [1/3] Installing PyInstaller...
python -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

:: Build the exe
echo [2/3] Building BFInstaller.exe ...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "BFInstaller" ^
    --clean ^
    setup_bravefrontier.py
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See output above for details.
    pause
    exit /b 1
)

:: Done
echo.
echo [3/3] Done!
echo.
echo Output: %~dp0dist\BFInstaller.exe
echo.
echo You can distribute that single file -- no Python required.
pause
endlocal
