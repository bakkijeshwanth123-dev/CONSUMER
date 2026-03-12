@echo off
:: =============================================================================
::  OSN Serpent-Secure System — Windows EXE Builder
::  Double-click this file or run from command prompt inside the project folder
:: =============================================================================

echo =========================================
echo  OSN Serpent-Secure :: EXE Build Script
echo =========================================
echo.

:: Step 1: Check Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

:: Step 2: Install / upgrade PyInstaller
echo [1/4] Installing PyInstaller...
pip install pyinstaller --quiet --upgrade

:: Step 3: Install project dependencies
echo [2/4] Installing project requirements...
pip install -r requirements.txt --quiet

:: Step 4: Clean old build artifacts
echo [3/4] Cleaning previous build...
if exist "dist\OSN-Serpent-Secure.exe" del /f /q "dist\OSN-Serpent-Secure.exe"
if exist "build" rmdir /s /q "build"

:: Step 5: Run PyInstaller with our spec
echo [4/4] Building EXE (this may take 3-5 minutes)...
pyinstaller serpent_secure.spec

echo.
IF EXIST "dist\OSN-Serpent-Secure.exe" (
    echo [SUCCESS] EXE created at:
    echo   dist\OSN-Serpent-Secure.exe
    echo.
    echo Double-click the EXE to launch the system.
    explorer dist
) ELSE (
    echo [ERROR] Build failed. Check the output above for errors.
)

echo.
pause
