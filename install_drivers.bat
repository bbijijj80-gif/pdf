@echo off
echo ============================================
echo HP LaserJet MFP Scanner - Installer
echo ============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed!
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Python found!
echo.

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip --quiet

echo.
echo Installing required libraries...
echo.

REM Install python-twain for TWAIN scanner support
echo Installing python-twain...
pip install python-twain --quiet
if %errorlevel% neq 0 (
    echo WARNING: python-twain installation had issues, trying alternative...
    pip install twain --quiet
)

REM Install Pillow for image processing
echo Installing Pillow...
pip install Pillow --quiet

REM Install PyPDF2 for PDF creation (backup)
echo Installing PyPDF2...
pip install PyPDF2 --quiet

echo.
echo ============================================
echo Installation Complete!
echo ============================================
echo.
echo IMPORTANT: Before running the scanner:
echo 1. Make sure your HP LaserJet M28w is powered on
echo 2. Connect via USB OR ensure it's on the same network
echo 3. Install HP Full Feature Drivers from:
echo    https://support.hp.com/drivers
echo 4. Make sure TWAIN driver is installed
echo.
echo To run the scanner, execute:
echo   python scanner.py
echo.
echo Or double-click run_scanner.bat
echo.
pause
